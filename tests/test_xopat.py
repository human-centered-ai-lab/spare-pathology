"""Tests for XOpat slide metadata and authenticated Deep Zoom endpoints."""

import csv

import pytest
from PIL import Image as PILImage

from app.models import DatasetImage, Study, StudyParticipant, User
from app.services.xopat import RasterDeepZoomGenerator, get_deepzoom_generator
from tests.helpers import login_admin, login_participant


@pytest.fixture()
def xopat_datasets_dir(tmp_path):
    dataset_dir = tmp_path / 'xopat_dataset'
    dataset_dir.mkdir()

    image_path = dataset_dir / 'img_001.png'
    PILImage.new('RGB', (512, 512), color='red').save(image_path)

    with open(dataset_dir / 'metadata.csv', 'w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['image_name', 'mpp_value', 'synthetic'])
        writer.writeheader()
        writer.writerow({
            'image_name': 'img_001.png',
            'mpp_value': '0.5',
            'synthetic': 'false',
        })

    return tmp_path


@pytest.fixture()
def xopat_participant(app, db, xopat_datasets_dir):
    with app.app_context():
        app.config['DATASETS_DIR'] = str(xopat_datasets_dir)

    participant = User(
        first_name='Xopat',
        last_name='Participant',
        email='xopat_participant@example.com',
        institution='Test Hospital',
        role='participant',
        is_test_user=False,
    )
    participant.set_password('xopatpass')
    db.session.add(participant)

    study = Study(
        name='XOpat Study',
        status='active',
        rating_schema={'questions': []},
        dataset_name='xopat_dataset',
    )
    db.session.add(study)
    db.session.flush()

    image = DatasetImage(
        study_id=study.id,
        image_path='xopat_dataset/img_001.png',
        attributes={'mpp_value': 0.5, 'synthetic': False},
        sequence_number=1,
    )
    db.session.add(image)
    db.session.flush()

    assignment = StudyParticipant(
        study_id=study.id,
        user_id=participant.id,
        random_seed=42,
    )
    db.session.add(assignment)
    db.session.commit()

    return participant, study, image


class TestAdminXopatDatasetBrowse:

    def test_plain_raster_images_use_raster_deepzoom_generator(self, app, xopat_datasets_dir):
        with app.app_context():
            app.config['DATASETS_DIR'] = str(xopat_datasets_dir)

        generator = get_deepzoom_generator(
            'plain-raster-slide',
            str(xopat_datasets_dir / 'xopat_dataset' / 'img_001.png'),
        )

        assert isinstance(generator._generator, RasterDeepZoomGenerator)

    def test_browse_returns_xopat_slide_metadata(self, client, admin_user, app, xopat_datasets_dir):
        with app.app_context():
            app.config['DATASETS_DIR'] = str(xopat_datasets_dir)

        login_admin(client)
        resp = client.get('/api/admin/datasets/xopat_dataset/images?all=true')
        assert resp.status_code == 200

        data = resp.get_json()
        assert data['total'] == 1
        item = data['items'][0]
        assert item['xopat_slide_id']
        assert item['xopat_microns'] == 0.5

    def test_admin_can_fetch_dzi_and_tile(self, client, admin_user, app, xopat_datasets_dir):
        with app.app_context():
            app.config['DATASETS_DIR'] = str(xopat_datasets_dir)

        login_admin(client)
        browse_resp = client.get('/api/admin/datasets/xopat_dataset/images?all=true')
        slide_id = browse_resp.get_json()['items'][0]['xopat_slide_id']

        dzi_resp = client.get(f'/api/xopat/slides/{slide_id}.dzi')
        assert dzi_resp.status_code == 200
        assert b'Image' in dzi_resp.data
        assert b'Format="png"' in dzi_resp.data

        tile_resp = client.get(f'/api/xopat/slides/{slide_id}_files/0/0_0.png')
        assert tile_resp.status_code == 200
        assert tile_resp.mimetype == 'image/png'


class TestParticipantXopatStudyAccess:

    def test_image_data_includes_xopat_metadata(self, client, app, db, xopat_participant):
        participant, study, _image = xopat_participant

        login_participant(client, participant.email, 'xopatpass')
        resp = client.get(f'/api/studies/{study.id}/image/1')
        assert resp.status_code == 200

        data = resp.get_json()
        assert data['xopat_slide_id']
        assert data['xopat_microns'] == 0.5

    def test_assigned_participant_can_fetch_study_dzi_and_tile(self, client, app, db, xopat_participant):
        participant, study, _image = xopat_participant

        login_participant(client, participant.email, 'xopatpass')
        image_resp = client.get(f'/api/studies/{study.id}/image/1')
        slide_id = image_resp.get_json()['xopat_slide_id']

        dzi_resp = client.get(f'/api/xopat/slides/{slide_id}.dzi')
        assert dzi_resp.status_code == 200
        assert b'Format="png"' in dzi_resp.data

        tile_resp = client.get(f'/api/xopat/slides/{slide_id}_files/0/0_0.png')
        assert tile_resp.status_code == 200
        assert tile_resp.mimetype == 'image/png'

    def test_unassigned_participant_cannot_fetch_study_slide(self, client, app, db, xopat_participant):
        owner, study, _image = xopat_participant

        other = User(
            first_name='Other',
            last_name='Participant',
            email='other_xopat@example.com',
            institution='Elsewhere',
            role='participant',
            is_test_user=False,
        )
        other.set_password('otherpass')
        db.session.add(other)
        db.session.commit()

        login_participant(client, other.email, 'otherpass')

        image_data_resp = client.get(f'/api/studies/{study.id}/image/1')
        assert image_data_resp.status_code == 403

        # Even if the slide id is guessed from a valid study/image pair, tile access stays blocked.
        client.post('/api/auth/logout')
        login_participant(client, owner.email, 'xopatpass')
        owner_image_resp = client.get(f'/api/studies/{study.id}/image/1')
        slide_id = owner_image_resp.get_json()['xopat_slide_id']

        client.post('/api/auth/logout')
        login_participant(client, other.email, 'otherpass')
        dzi_resp = client.get(f'/api/xopat/slides/{slide_id}.dzi')
        assert dzi_resp.status_code == 403
