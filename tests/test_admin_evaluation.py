"""Tests for admin evaluation API: status, filter-options, data, PDF upload/download, image serving."""

import io
import json
import os

import pytest

from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import get_default_rating_schema
from tests.helpers import (
    create_full_study,
    create_study_with_images,
    login_admin,
    login_participant,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def eval_study(db):
    """Create a fully configured study with participants and some ratings."""
    study, participants = create_full_study(db, n_images=4, n_participants=2)
    return study, participants


@pytest.fixture()
def eval_study_with_ratings(db):
    """Create a study with two participants, one of whom has ratings."""
    study, participants = create_full_study(db, n_images=4, n_participants=2)

    img = DatasetImage.query.filter_by(study_id=study.id).first()
    rating = Rating(
        user_id=participants[0].id,
        dataset_image_id=img.id,
        study_id=study.id,
        responses={'F1': 2, 'F2': 1},
    )
    db.session.add(rating)
    db.session.commit()
    return study, participants


@pytest.fixture()
def eval_study_submitted(db):
    """Create a study with one submitted and one not-started participant."""
    study, participants = create_full_study(db, n_images=4, n_participants=2)

    from datetime import datetime, timezone

    sp = StudyParticipant.query.filter_by(
        study_id=study.id, user_id=participants[0].id,
    ).first()
    sp.submitted = True
    sp.submitted_at = datetime.now(timezone.utc)
    db.session.commit()
    return study, participants


# ===========================================================================
# Test: GET /api/admin/studies/:id/evaluation/status
# ===========================================================================

class TestEvaluationStatus:

    def test_status_no_participants(self, client, admin_user, db):
        """Empty study returns zero counts."""
        study = create_study_with_images(db, n=2)
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total_users'] == 0
        assert data['submitted'] == 0
        assert data['in_progress'] == 0
        assert data['not_started'] == 0

    def test_status_with_ratings(self, client, admin_user, eval_study_with_ratings):
        """Correct in_progress / not_started counts."""
        study, participants = eval_study_with_ratings
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total_users'] == 2
        assert data['in_progress'] == 1
        assert data['not_started'] == 1

    def test_status_excludes_test_users(self, client, admin_user, db):
        """Test users are not counted in status."""
        study = create_study_with_images(db, n=2)

        test_user = User(
            first_name='Tester', last_name='Bot', email='tbot@test.com',
            institution='Test', role='participant', is_test_user=True,
        )
        test_user.set_password('testpass')
        db.session.add(test_user)
        db.session.flush()

        sp = StudyParticipant(study_id=study.id, user_id=test_user.id, random_seed=42)
        db.session.add(sp)
        db.session.commit()

        login_admin(client)
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total_users'] == 0

    def test_status_submitted_user(self, client, admin_user, eval_study_submitted):
        """Submitted user counted correctly."""
        study, participants = eval_study_submitted
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['submitted'] == 1
        assert data['not_started'] == 1

    def test_status_unauthenticated(self, client, db):
        """401 without login."""
        study = create_study_with_images(db, n=2)
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/status')
        assert resp.status_code == 401


# ===========================================================================
# Test: GET /api/admin/studies/:id/evaluation/filter-options
# ===========================================================================

class TestEvaluationFilterOptions:

    def test_filter_options_empty_dataset(self, client, admin_user, db):
        """Returns empty arrays for study with no images."""
        study = Study(
            name='Empty Study', status='draft',
            rating_schema=get_default_rating_schema(),
        )
        db.session.add(study)
        db.session.commit()

        login_admin(client)
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/filter-options')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['attributes'] == []
        assert data['users'] == []

    def test_filter_options_with_images(self, client, admin_user, db):
        """Returns distinct attribute values."""
        study = create_study_with_images(db, n=4)
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/filter-options')
        assert resp.status_code == 200
        data = resp.get_json()
        attr_names = [a['name'] for a in data['attributes']]
        assert 'mpp_value' in attr_names
        assert 'tissue_type' in attr_names
        assert 'synthetic' in attr_names

    def test_filter_options_returns_users(self, client, admin_user, eval_study):
        """Returns non-test users assigned to the study."""
        study, participants = eval_study
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/filter-options')
        assert resp.status_code == 200
        data = resp.get_json()
        user_ids = [u['id'] for u in data['users']]
        for p in participants:
            assert p.id in user_ids

    def test_filter_options_excludes_test_users(self, client, admin_user, db):
        """Test users not in users list."""
        study = create_study_with_images(db, n=2)

        test_user = User(
            first_name='Tester', last_name='Bot', email='filterbot@test.com',
            institution='Test', role='participant', is_test_user=True,
        )
        test_user.set_password('testpass')
        db.session.add(test_user)
        db.session.flush()

        sp = StudyParticipant(study_id=study.id, user_id=test_user.id, random_seed=42)
        db.session.add(sp)
        db.session.commit()

        login_admin(client)
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/filter-options')
        assert resp.status_code == 200
        data = resp.get_json()
        user_ids = [u['id'] for u in data['users']]
        assert test_user.id not in user_ids

    def test_filter_options_as_participant(self, client, test_user, db):
        """403 for non-admin."""
        study = create_study_with_images(db, n=2)
        login_participant(client)
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/filter-options')
        assert resp.status_code == 403


# ===========================================================================
# Test: GET /api/admin/studies/:id/evaluation/data
# ===========================================================================

class TestEvaluationData:

    @pytest.mark.parametrize('vary_total', [False, True])
    def test_constant_scores_return_valid_json(self, client, admin_user, db, vary_total):
        study, participants = create_full_study(db, n_images=4, n_participants=2)
        images = DatasetImage.query.filter_by(study_id=study.id).order_by(DatasetImage.id).all()
        for participant in participants:
            for index, image in enumerate(images):
                responses = {f'F{i}': 2 for i in range(1, 7)}
                if vary_total:
                    responses['F2'] = 1 + index % 2
                db.session.add(Rating(
                    user_id=participant.id, study_id=study.id,
                    dataset_image_id=image.id, responses=responses,
                ))
        db.session.commit()
        login_admin(client)
        response = client.get(f'/api/admin/studies/{study.id}/evaluation/data?submitted_only=0')
        assert response.status_code == 200

        def reject_nonfinite(value):
            raise AssertionError(f'Invalid JSON number: {value}')

        data = json.loads(response.data, parse_constant=reject_nonfinite)
        assert data['question_agreement']['F1']['value'] is None
        if vary_total:
            assert data['icc']['value'] == pytest.approx(1)
        else:
            assert data['icc']['value'] is None

    def test_data_no_ratings(self, client, admin_user, db):
        """Returns result even with no ratings."""
        study = create_study_with_images(db, n=2)
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/data')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)

    def test_data_with_ratings(self, client, admin_user, eval_study_with_ratings):
        """Returns computed statistics from ratings."""
        study, participants = eval_study_with_ratings
        login_admin(client)
        # submitted_only=0 since no one has submitted
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/data?submitted_only=0')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)

    def test_data_submitted_only_filter(self, client, admin_user, eval_study_submitted):
        """submitted_only=1 filters to only submitted users."""
        study, _ = eval_study_submitted
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/data?submitted_only=1')
        assert resp.status_code == 200

    def test_data_attribute_filter(self, client, admin_user, db):
        """Attribute filter (synthetic=true) works."""
        study = create_study_with_images(db, n=4)
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/data?synthetic=true&submitted_only=0')
        assert resp.status_code == 200

    def test_data_user_ids_filter(self, client, admin_user, eval_study_with_ratings):
        """user_ids param filters to specific users."""
        study, participants = eval_study_with_ratings
        login_admin(client)
        uid = participants[0].id
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/data?user_ids={uid}&submitted_only=0')
        assert resp.status_code == 200

    def test_data_as_participant(self, client, test_user, db):
        """403 for non-admin."""
        study = create_study_with_images(db, n=2)
        login_participant(client)
        resp = client.get(f'/api/admin/studies/{study.id}/evaluation/data')
        assert resp.status_code == 403


# ===========================================================================
# Test: PDF Upload / Download
# ===========================================================================

class TestPDFUploadDownload:

    def test_upload_pdf(self, client, admin_user, db, tmp_path):
        """Multipart upload saves file and sets protocol_pdf on study."""
        study = create_study_with_images(db, n=2)

        with client.application.app_context():
            client.application.config['UPLOADS_DIR'] = str(tmp_path)

        login_admin(client)
        pdf_data = b'%PDF-1.4 test content'
        resp = client.post(
            f'/api/admin/studies/{study.id}/upload-pdf',
            data={'protocol_pdf': (io.BytesIO(pdf_data), 'protocol.pdf')},
            content_type='multipart/form-data',
        )
        assert resp.status_code == 200
        assert 'path' in resp.get_json()

        db.session.refresh(study)
        assert study.protocol_pdf_path is not None
        assert os.path.exists(study.protocol_pdf_path)

    def test_upload_non_pdf_rejected(self, client, admin_user, db, tmp_path):
        """Non-.pdf extension returns 400."""
        study = create_study_with_images(db, n=2)

        with client.application.app_context():
            client.application.config['UPLOADS_DIR'] = str(tmp_path)

        login_admin(client)
        resp = client.post(
            f'/api/admin/studies/{study.id}/upload-pdf',
            data={'protocol_pdf': (io.BytesIO(b'not a pdf'), 'document.txt')},
            content_type='multipart/form-data',
        )
        assert resp.status_code == 400

    def test_upload_replaces_existing(self, client, admin_user, db, tmp_path):
        """Old PDF deleted, new one saved."""
        study = create_study_with_images(db, n=2)

        with client.application.app_context():
            client.application.config['UPLOADS_DIR'] = str(tmp_path)

        login_admin(client)

        # Upload first PDF
        resp1 = client.post(
            f'/api/admin/studies/{study.id}/upload-pdf',
            data={'protocol_pdf': (io.BytesIO(b'%PDF first'), 'first.pdf')},
            content_type='multipart/form-data',
        )
        assert resp1.status_code == 200
        first_path = resp1.get_json()['path']

        # Upload second PDF
        resp2 = client.post(
            f'/api/admin/studies/{study.id}/upload-pdf',
            data={'protocol_pdf': (io.BytesIO(b'%PDF second'), 'second.pdf')},
            content_type='multipart/form-data',
        )
        assert resp2.status_code == 200
        second_path = resp2.get_json()['path']

        assert second_path != first_path
        assert not os.path.exists(first_path)
        assert os.path.exists(second_path)

    def test_download_pdf(self, client, admin_user, db, tmp_path):
        """Returns file with correct content-type."""
        study = create_study_with_images(db, n=2)

        with client.application.app_context():
            client.application.config['UPLOADS_DIR'] = str(tmp_path)

        login_admin(client)

        # Upload first
        pdf_content = b'%PDF-1.4 download test'
        client.post(
            f'/api/admin/studies/{study.id}/upload-pdf',
            data={'protocol_pdf': (io.BytesIO(pdf_content), 'download.pdf')},
            content_type='multipart/form-data',
        )

        # Download
        resp = client.get(f'/api/admin/studies/{study.id}/download-pdf')
        assert resp.status_code == 200
        assert resp.data == pdf_content

    def test_download_no_pdf(self, client, admin_user, db):
        """404 when no PDF uploaded."""
        study = create_study_with_images(db, n=2)
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{study.id}/download-pdf')
        assert resp.status_code == 404

    def test_upload_as_participant(self, client, test_user, db, tmp_path):
        """403 for non-admin."""
        study = create_study_with_images(db, n=2)

        with client.application.app_context():
            client.application.config['UPLOADS_DIR'] = str(tmp_path)

        login_participant(client)
        resp = client.post(
            f'/api/admin/studies/{study.id}/upload-pdf',
            data={'protocol_pdf': (io.BytesIO(b'%PDF test'), 'file.pdf')},
            content_type='multipart/form-data',
        )
        assert resp.status_code == 403


# ===========================================================================
# Test: Image Serving
# ===========================================================================

class TestImageServing:

    @pytest.fixture()
    def datasets_dir_with_image(self, tmp_path):
        """Create a datasets directory with a large PNG file."""
        from PIL import Image as PILImage

        model_dir = tmp_path / 'test_model' / 'mpp_0.5' / '0001'
        model_dir.mkdir(parents=True)
        img_path = model_dir / 'input.png'
        img = PILImage.new('RGB', (1024, 768), color='red')
        img.save(str(img_path))
        return tmp_path

    def test_admin_serve_image(self, client, admin_user, datasets_dir_with_image):
        """Returns image file with correct content-type."""
        with client.application.app_context():
            client.application.config['DATASETS_DIR'] = str(datasets_dir_with_image)

        login_admin(client)
        resp = client.get('/api/admin/images/serve/test_model/mpp_0.5/0001/input.png')
        assert resp.status_code == 200
        assert 'image' in resp.content_type

    def test_admin_serve_nonexistent(self, client, admin_user, datasets_dir_with_image):
        """404 for missing file."""
        with client.application.app_context():
            client.application.config['DATASETS_DIR'] = str(datasets_dir_with_image)

        login_admin(client)
        resp = client.get('/api/admin/images/serve/nonexistent/path.png')
        assert resp.status_code == 404

    def test_admin_serve_thumbnail(self, client, admin_user, datasets_dir_with_image):
        """Thumbnail endpoint returns a cached image scaled to 512px max."""
        from PIL import Image as PILImage

        with client.application.app_context():
            client.application.config['DATASETS_DIR'] = str(datasets_dir_with_image)

        login_admin(client)
        resp = client.get('/api/admin/images/thumb/test_model/mpp_0.5/0001/input.png')
        assert resp.status_code == 200
        assert 'image' in resp.content_type
        assert 'max-age=3600' in (resp.headers.get('Cache-Control') or '')

        with PILImage.open(io.BytesIO(resp.data)) as image:
            assert image.width <= 512
            assert image.height <= 512
            assert image.size == (512, 384)

    def test_admin_serve_thumbnail_nonexistent(self, client, admin_user, datasets_dir_with_image):
        """Thumbnail endpoint returns 404 for missing source images."""
        with client.application.app_context():
            client.application.config['DATASETS_DIR'] = str(datasets_dir_with_image)

        login_admin(client)
        resp = client.get('/api/admin/images/thumb/nonexistent/path.png')
        assert resp.status_code == 404

    def test_participant_serve_image(self, client, db, test_user, datasets_dir_with_image):
        """Participant can access images via participant endpoint when assigned."""
        from app.models import Study, DatasetImage, StudyParticipant
        with client.application.app_context():
            client.application.config['DATASETS_DIR'] = str(datasets_dir_with_image)
            # Create a study with this image assigned, and assign the participant
            study = Study(name='Img Test', status='active', rating_schema={'questions': []})
            db.session.add(study)
            db.session.flush()
            di = DatasetImage(
                study_id=study.id,
                image_path='test_model/mpp_0.5/0001/input.png',
                attributes={},
                sequence_number=1,
            )
            db.session.add(di)
            sp = StudyParticipant(study_id=study.id, user_id=test_user.id, random_seed=42)
            db.session.add(sp)
            db.session.commit()

        login_participant(client)
        resp = client.get('/api/studies/images/test_model/mpp_0.5/0001/input.png')
        assert resp.status_code == 200
        assert 'image' in resp.content_type

    def test_participant_serve_nonexistent(self, client, db, test_user, datasets_dir_with_image):
        """404 for nonexistent image via participant endpoint (when authorized)."""
        from app.models import Study, DatasetImage, StudyParticipant
        with client.application.app_context():
            client.application.config['DATASETS_DIR'] = str(datasets_dir_with_image)
            # Create a study with this image path assigned, and assign the participant
            study = Study(name='Img Test', status='active', rating_schema={'questions': []})
            db.session.add(study)
            db.session.flush()
            di = DatasetImage(
                study_id=study.id,
                image_path='nonexistent/path.png',
                attributes={},
                sequence_number=1,
            )
            db.session.add(di)
            sp = StudyParticipant(study_id=study.id, user_id=test_user.id, random_seed=42)
            db.session.add(sp)
            db.session.commit()

        login_participant(client)
        resp = client.get('/api/studies/images/nonexistent/path.png')
        assert resp.status_code == 404
