"""Tests for admin impersonation API endpoints.

Covers:
- POST /api/admin/impersonate/<user_id> — start impersonation
- POST /api/admin/unimpersonate — stop impersonation
- Read-only enforcement: submit, save response, open rating all blocked
- Access control: participant cannot impersonate, cannot impersonate admin
"""

import pytest

from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import get_default_rating_schema
from tests.helpers import login_admin, login_participant


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def eval_study(db):
    """Create an active study with schema and images for impersonation tests."""
    study = Study(
        name='Impersonation Test Study',
        description='Study for impersonation tests',
        status='active',
        rating_schema=get_default_rating_schema(),
        uncertainty_enabled=True,
    )
    db.session.add(study)
    db.session.flush()

    for i in range(1, 4):
        img = DatasetImage(
            study_id=study.id,
            image_path=f'impersonate_dataset/image_{i}.png',
            attributes={'synthetic': (i % 2 == 0), 'mpp_value': 0.5},
            sequence_number=i,
        )
        db.session.add(img)

    db.session.commit()
    return study


@pytest.fixture()
def participant(db, eval_study):
    """Create a participant assigned to the eval_study."""
    user = User(
        first_name='Impersonated',
        last_name='Participant',
        email='impersonated@example.com',
        institution='Test Hospital',
        role='participant',
        is_test_user=False,
    )
    user.set_password('partpass')
    db.session.add(user)
    db.session.flush()

    sp = StudyParticipant(
        study_id=eval_study.id,
        user_id=user.id,
        random_seed=42,
    )
    db.session.add(sp)
    db.session.commit()
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestImpersonation:

    def test_admin_can_impersonate_participant(self, client, admin_user, participant):
        """POST /api/admin/impersonate/<user_id> returns 200 with participant data and impersonating=True."""
        login_admin(client)

        resp = client.post(f'/api/admin/impersonate/{participant.id}')
        assert resp.status_code == 200

        data = resp.get_json()
        assert data['id'] == participant.id
        assert data['email'] == 'impersonated@example.com'
        assert data['impersonating'] is True

    def test_impersonating_user_sees_me_as_participant(self, client, admin_user, participant):
        """GET /api/auth/me returns the impersonated user data."""
        login_admin(client)
        client.post(f'/api/admin/impersonate/{participant.id}')

        resp = client.get('/api/auth/me')
        assert resp.status_code == 200

        data = resp.get_json()
        assert data['id'] == participant.id
        assert data['role'] == 'participant'
        assert data['impersonating'] is True

    def test_impersonating_cannot_submit(self, client, admin_user, participant, eval_study):
        """POST /api/studies/<id>/submit returns 403 when impersonating."""
        login_admin(client)
        imp_resp = client.post(f'/api/admin/impersonate/{participant.id}')
        assert imp_resp.status_code == 200

        resp = client.post(f'/api/studies/{eval_study.id}/submit')
        assert resp.status_code == 403

    def test_impersonating_cannot_save_response(self, client, admin_user, participant, eval_study, db):
        """PUT /api/ratings/<id>/response returns 403 when impersonating."""
        # Create a rating directly for the participant
        images = DatasetImage.query.filter_by(study_id=eval_study.id).all()
        rating = Rating(
            user_id=participant.id,
            dataset_image_id=images[0].id,
            study_id=eval_study.id,
            responses={},
        )
        db.session.add(rating)
        db.session.commit()

        login_admin(client)
        client.post(f'/api/admin/impersonate/{participant.id}')

        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 2,
        })
        assert resp.status_code == 403

    def test_impersonating_cannot_open_rating(self, client, admin_user, participant, eval_study):
        """POST /api/ratings/open returns 403 when impersonating."""
        login_admin(client)
        client.post(f'/api/admin/impersonate/{participant.id}')

        images = DatasetImage.query.filter_by(study_id=eval_study.id).all()
        resp = client.post('/api/ratings/open', json={
            'study_id': eval_study.id,
            'dataset_image_id': images[0].id,
        })
        assert resp.status_code == 403

    def test_unimpersonate_restores_admin(self, client, admin_user, participant):
        """POST /api/admin/unimpersonate returns the admin user."""
        login_admin(client)
        client.post(f'/api/admin/impersonate/{participant.id}')

        resp = client.post('/api/admin/unimpersonate')
        assert resp.status_code == 200

        data = resp.get_json()
        assert data['id'] == admin_user.id
        assert data['role'] == 'admin'
        assert 'impersonating' not in data

    def test_logout_while_impersonating_clears_impersonation_state(self, client, admin_user, participant):
        """POST /api/auth/logout removes both auth and impersonation session state."""
        login_admin(client)
        client.post(f'/api/admin/impersonate/{participant.id}')

        with client.session_transaction() as sess:
            assert sess.get('_impersonator_id') == admin_user.id

        resp = client.post('/api/auth/logout')
        assert resp.status_code == 204

        with client.session_transaction() as sess:
            assert '_impersonator_id' not in sess

        me_resp = client.get('/api/auth/me')
        assert me_resp.status_code == 401

    def test_participant_cannot_impersonate(self, client, admin_user, participant, db):
        """A participant cannot use the impersonate endpoint (403)."""
        # Create another participant to try to impersonate
        other = User(
            first_name='Other',
            last_name='User',
            email='other@example.com',
            role='participant',
        )
        other.set_password('otherpass')
        db.session.add(other)
        db.session.commit()

        # Login as participant
        login_participant(client, 'impersonated@example.com', 'partpass')

        resp = client.post(f'/api/admin/impersonate/{other.id}')
        assert resp.status_code == 403

    def test_cannot_impersonate_admin(self, client, admin_user):
        """POST /api/admin/impersonate/<admin_id> returns 400 (can only impersonate participants)."""
        login_admin(client)

        resp = client.post(f'/api/admin/impersonate/{admin_user.id}')
        assert resp.status_code == 400
        assert 'participant' in resp.get_json()['error'].lower()

    def test_cannot_impersonate_nonexistent(self, client, admin_user):
        """POST /api/admin/impersonate/9999 returns 404."""
        login_admin(client)

        resp = client.post('/api/admin/impersonate/9999')
        assert resp.status_code == 404

    def test_unimpersonate_when_not_impersonating(self, client, admin_user):
        """POST /api/admin/unimpersonate returns 400 when not impersonating."""
        login_admin(client)

        resp = client.post('/api/admin/unimpersonate')
        assert resp.status_code == 400
        assert 'not impersonating' in resp.get_json()['error'].lower()
