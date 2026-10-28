"""Tests for the participant studies API endpoint: GET /api/studies.

Covers:
- Visibility: active vs draft studies
- Completion info structure
- Draft study asset access guards
- Resume position reporting
- Test user sees all studies
- Auth: unauthenticated returns 401, admin returns 403
"""

import random

import pytest

from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import get_default_rating_schema
from tests.helpers import login_admin, login_participant


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def participant(db):
    """Create a participant user."""
    user = User(
        first_name='Study',
        last_name='Participant',
        email='study_part@example.com',
        institution='Test Hospital',
        role='participant',
        is_test_user=False,
    )
    user.set_password('studypass')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def active_study(db):
    """Create an active study with images."""
    study = Study(
        name='Active Study',
        description='An active study',
        status='active',
        rating_schema=get_default_rating_schema(),
    )
    db.session.add(study)
    db.session.flush()

    for i in range(1, 4):
        img = DatasetImage(
            study_id=study.id,
            image_path=f'study_ds/img_{i}.png',
            attributes={'synthetic': False},
            sequence_number=i,
        )
        db.session.add(img)

    db.session.commit()
    return study


@pytest.fixture()
def draft_study(db):
    """Create a draft study."""
    study = Study(
        name='Draft Study',
        description='A draft study',
        status='draft',
        rating_schema=get_default_rating_schema(),
    )
    db.session.add(study)
    db.session.commit()
    return study


def _assign(db, study, user):
    """Assign user to study."""
    sp = StudyParticipant(
        study_id=study.id,
        user_id=user.id,
        random_seed=42,
    )
    db.session.add(sp)
    db.session.commit()
    return sp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestListStudies:

    def test_participant_sees_assigned_active_studies(
        self, client, participant, active_study, db
    ):
        """Participant sees active studies they are assigned to."""
        _assign(db, active_study, participant)
        login_participant(client, 'study_part@example.com', 'studypass')

        resp = client.get('/api/studies')
        assert resp.status_code == 200

        data = resp.get_json()
        assert len(data) == 1
        assert data[0]['name'] == 'Active Study'
        assert data[0]['status'] == 'active'
        assert data[0]['default_image_viewer'] == 'native'

    def test_participant_does_not_see_draft_studies(
        self, client, participant, draft_study, db
    ):
        """Participant does not see draft studies even when assigned."""
        _assign(db, draft_study, participant)
        login_participant(client, 'study_part@example.com', 'studypass')

        resp = client.get('/api/studies')
        assert resp.status_code == 200

        data = resp.get_json()
        assert len(data) == 0

    def test_completion_info_correct(
        self, client, participant, active_study, db
    ):
        """Completion info has total, completed, pct fields."""
        _assign(db, active_study, participant)
        login_participant(client, 'study_part@example.com', 'studypass')

        resp = client.get('/api/studies')
        data = resp.get_json()

        completion = data[0]['completion']
        assert 'total' in completion
        assert 'completed' in completion
        assert 'pct' in completion
        assert completion['total'] == 3  # 3 images
        assert completion['completed'] == 0
        assert completion['pct'] == 0

    def test_completion_with_rated_images(
        self, client, participant, active_study, db
    ):
        """Completion counts images with all ordinal questions answered."""
        _assign(db, active_study, participant)

        images = DatasetImage.query.filter_by(study_id=active_study.id).all()
        # Rate the first image with all F1-F6
        rating = Rating(
            user_id=participant.id,
            dataset_image_id=images[0].id,
            study_id=active_study.id,
            responses={'F1': 2, 'F2': 1, 'F3': 2, 'F4': 1, 'F5': 2, 'F6': 1},
        )
        db.session.add(rating)
        db.session.commit()

        login_participant(client, 'study_part@example.com', 'studypass')
        resp = client.get('/api/studies')
        data = resp.get_json()

        completion = data[0]['completion']
        assert completion['completed'] == 1
        assert completion['total'] == 3
        assert completion['pct'] == 33  # 1/3 = 33%

    def test_resume_position_included(
        self, client, participant, active_study, db
    ):
        """Study list includes the participant's last viewed shuffled position."""
        sp = _assign(db, active_study, participant)
        images = DatasetImage.query.filter_by(study_id=active_study.id).order_by(DatasetImage.id).all()
        shuffled_ids = [img.id for img in images]
        random.Random(sp.random_seed).shuffle(shuffled_ids)
        sp.last_viewed_image_id = shuffled_ids[1]
        db.session.commit()

        login_participant(client, 'study_part@example.com', 'studypass')
        resp = client.get('/api/studies')
        data = resp.get_json()

        assert data[0]['last_viewed_position'] == 2

    def test_free_text_only_study_reports_complete(
        self, client, participant, db
    ):
        """Studies without ordinal questions report completion consistently."""
        study = Study(
            name='Free Text Study',
            description='Only free text',
            status='active',
            rating_schema={
                'questions': [
                    {'id': 'notes', 'type': 'free_text', 'name': 'Notes'},
                ],
            },
        )
        db.session.add(study)
        db.session.flush()

        for i in range(1, 3):
            db.session.add(DatasetImage(
                study_id=study.id,
                image_path=f'freetext_only/img_{i}.png',
                attributes={},
                sequence_number=i,
            ))

        _assign(db, study, participant)
        db.session.commit()

        login_participant(client, 'study_part@example.com', 'studypass')
        resp = client.get('/api/studies')
        data = resp.get_json()
        free_text_study = next(item for item in data if item['id'] == study.id)

        assert free_text_study['completion']['completed'] == 2
        assert free_text_study['completion']['pct'] == 100

    def test_test_user_sees_all_studies(
        self, client, active_study, draft_study, db
    ):
        """Test user (is_test_user=True) sees all studies regardless of status."""
        test_u = User(
            first_name='Test',
            last_name='Bot',
            email='testbot@example.com',
            institution='Test Lab',
            role='participant',
            is_test_user=True,
        )
        test_u.set_password('testpass')
        db.session.add(test_u)
        db.session.commit()

        login_participant(client, 'testbot@example.com', 'testpass')

        resp = client.get('/api/studies')
        assert resp.status_code == 200

        data = resp.get_json()
        names = {s['name'] for s in data}
        assert 'Active Study' in names
        assert 'Draft Study' in names

    def test_unauthenticated_returns_401(self, client, db):
        """Unauthenticated request to /api/studies returns 401."""
        resp = client.get('/api/studies')
        assert resp.status_code == 401

    def test_participant_sees_finished_studies(
        self, client, participant, active_study, db
    ):
        """Participant sees finished studies they are assigned to."""
        active_study.status = 'finished'
        db.session.commit()

        _assign(db, active_study, participant)
        login_participant(client, 'study_part@example.com', 'studypass')

        resp = client.get('/api/studies')
        assert resp.status_code == 200

        data = resp.get_json()
        assert len(data) == 1
        assert data[0]['status'] == 'finished'

    def test_admin_returns_403(self, client, admin_user, db):
        """Admin user gets 403 on participant-only endpoint."""
        login_admin(client)

        resp = client.get('/api/studies')
        assert resp.status_code == 403

    def test_participant_cannot_access_draft_protocol_pdf(
        self, client, participant, draft_study, db, tmp_path
    ):
        """Direct protocol download stays blocked while a study is in draft."""
        _assign(db, draft_study, participant)
        pdf_path = tmp_path / 'draft_protocol.pdf'
        pdf_path.write_bytes(b'%PDF-1.4\n')
        draft_study.protocol_pdf_path = str(pdf_path)
        db.session.commit()

        login_participant(client, 'study_part@example.com', 'studypass')
        resp = client.get(f'/api/studies/{draft_study.id}/protocol-pdf')
        assert resp.status_code == 403

    def test_participant_cannot_access_draft_image_asset(
        self, client, participant, draft_study, db
    ):
        """Direct image asset fetch stays blocked while a study is in draft."""
        _assign(db, draft_study, participant)
        db.session.add(DatasetImage(
            study_id=draft_study.id,
            image_path='draft_ds/img_1.png',
            attributes={},
            sequence_number=1,
        ))
        db.session.commit()

        login_participant(client, 'study_part@example.com', 'studypass')
        resp = client.get('/api/studies/images/draft_ds/img_1.png')
        assert resp.status_code == 403
