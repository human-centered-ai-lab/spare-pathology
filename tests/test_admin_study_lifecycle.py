"""Tests for admin study lifecycle API: CRUD, settings, schema, activate/reopen, auto-finish."""

import pytest

from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import get_default_rating_schema
from tests.helpers import (
    create_study_with_images,
    create_full_study,
    login_admin,
    login_participant,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ready_study(db, test_user):
    """Create a study that passes all readiness checks (schema + images + participant + stratification)."""
    study = create_study_with_images(db, n=4)
    study.status = 'draft'

    sp = StudyParticipant(study_id=study.id, user_id=test_user.id, random_seed=42)
    db.session.add(sp)
    db.session.commit()
    return study


@pytest.fixture()
def active_study_with_ratings(db, test_user):
    """Create an active study (structurally frozen — schema/dataset edits are blocked)."""
    study = create_study_with_images(db, n=2)
    study.status = 'active'
    db.session.commit()
    return study


# ===========================================================================
# Test: Study CRUD
# ===========================================================================

class TestStudyCRUD:

    def test_create_study(self, client, admin_user, db):
        """POST /api/admin/studies creates a new study with default schema."""
        login_admin(client)
        resp = client.post('/api/admin/studies', json={'name': 'My New Study'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == 'My New Study'
        assert data['status'] == 'draft'
        assert len(data['rating_schema']['questions']) == 6

    def test_create_study_auto_assigns_test_users(self, client, admin_user, db):
        """Creating a study auto-assigns the seeded test user."""
        login_admin(client)
        resp = client.post('/api/admin/studies', json={'name': 'Auto Assign Test'})
        assert resp.status_code == 201
        study_id = resp.get_json()['id']

        # Check that the seeded test user (email='test') is assigned
        test_user = User.query.filter_by(email='test').first()
        sp = StudyParticipant.query.filter_by(study_id=study_id, user_id=test_user.id).first()
        assert sp is not None

    def test_list_studies(self, client, admin_user, study_with_schema):
        """GET /api/admin/studies returns list of studies."""
        login_admin(client)
        resp = client.get('/api/admin/studies')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 1
        names = [p['name'] for p in data]
        assert 'Test Study With Schema' in names

    def test_get_study_detail(self, client, admin_user, study_with_schema):
        """GET /api/admin/studies/:id returns full study detail."""
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{study_with_schema.id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['name'] == 'Test Study With Schema'
        assert 'rating_schema' in data
        assert 'dataset_name' in data
        assert data['default_image_viewer'] == 'native'

    def test_delete_study_cascades(self, client, admin_user, study_with_images, db):
        """DELETE /api/admin/studies/:id cascades to images."""
        login_admin(client)
        sid = study_with_images.id
        image_count = DatasetImage.query.filter_by(study_id=sid).count()
        assert image_count == 10

        resp = client.delete(f'/api/admin/studies/{sid}')
        assert resp.status_code == 204

        assert db.session.get(Study, sid) is None
        assert DatasetImage.query.filter_by(study_id=sid).count() == 0


# ===========================================================================
# Test: Settings
# ===========================================================================

class TestStudySettings:

    def test_update_settings_name_description(self, client, admin_user, study_with_schema, db):
        """PUT /api/admin/studies/:id/settings updates name and description."""
        login_admin(client)
        resp = client.put(f'/api/admin/studies/{study_with_schema.id}/settings', json={
            'name': 'Renamed Study',
            'description': 'New description',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['name'] == 'Renamed Study'
        assert data['description'] == 'New description'

    def test_update_settings_uncertainty_instruction(self, client, admin_user, study_with_schema, db):
        """PUT /api/admin/studies/:id/settings updates uncertainty and instruction."""
        login_admin(client)
        resp = client.put(f'/api/admin/studies/{study_with_schema.id}/settings', json={
            'name': 'Test Study With Schema',
            'uncertainty_enabled': True,
            'session_instruction': '<p>Please rate carefully.</p>',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['uncertainty_enabled'] is True
        assert data['session_instruction'] == '<p>Please rate carefully.</p>'

    def test_update_settings_default_image_viewer(self, client, admin_user, study_with_schema, db):
        """PUT /api/admin/studies/:id/settings updates the participant viewer mode."""
        login_admin(client)
        resp = client.put(f'/api/admin/studies/{study_with_schema.id}/settings', json={
            'name': 'Test Study With Schema',
            'default_image_viewer': 'xopat',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['default_image_viewer'] == 'xopat'


# ===========================================================================
# Test: Schema
# ===========================================================================

class TestStudySchema:

    def test_save_schema_valid(self, client, admin_user, study_with_schema, db):
        """PUT /api/admin/studies/:id/schema saves a valid schema."""
        login_admin(client)
        schema = get_default_rating_schema()
        # Add a new question
        schema['questions'].append({
            'id': 'F7',
            'type': 'ordinal',
            'name': 'Extra Question',
            'min': 0,
            'max': 2,
            'labels': {'0': 'Bad', '1': 'OK', '2': 'Good'},
        })
        resp = client.put(f'/api/admin/studies/{study_with_schema.id}/schema', json={
            'schema': schema,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        question_ids = [q['id'] for q in data['rating_schema']['questions']]
        assert 'F7' in question_ids

    def test_save_schema_invalid_returns_400(self, client, admin_user, study_with_schema):
        """PUT /api/admin/studies/:id/schema returns 400 for invalid schema."""
        login_admin(client)
        resp = client.put(f'/api/admin/studies/{study_with_schema.id}/schema', json={
            'schema': {'questions': [{'id': '', 'type': 'ordinal'}]},
        })
        assert resp.status_code == 400
        assert 'errors' in resp.get_json()

    def test_save_schema_cascade_deletes_responses(self, client, admin_user, db):
        """Removing a question from schema removes that key from existing ratings."""
        study = create_study_with_images(db, n=2)
        # study starts as 'draft' — schema edits are allowed

        user = User(
            first_name='Cascade', last_name='Test', email='cascade@test.com',
            institution='Test', role='participant', is_test_user=True,
        )
        user.set_password('testpass')
        db.session.add(user)
        db.session.flush()

        sp = StudyParticipant(study_id=study.id, user_id=user.id, random_seed=42)
        db.session.add(sp)

        img = DatasetImage.query.filter_by(study_id=study.id).first()
        rating = Rating(
            user_id=user.id, dataset_image_id=img.id,
            study_id=study.id, responses={'F1': 2, 'F2': 1, 'F3': 0},
        )
        db.session.add(rating)
        db.session.commit()

        # Remove F3 from schema
        login_admin(client)
        schema = get_default_rating_schema()
        schema['questions'] = [q for q in schema['questions'] if q['id'] != 'F3']

        resp = client.put(f'/api/admin/studies/{study.id}/schema', json={
            'schema': schema,
        })
        assert resp.status_code == 200

        db.session.refresh(rating)
        assert 'F1' in rating.responses
        assert 'F2' in rating.responses
        assert 'F3' not in rating.responses

    def test_reset_schema_to_defaults(self, client, admin_user, study_with_schema, db):
        """POST /api/admin/studies/:id/schema/reset resets to default schema."""
        login_admin(client)
        # First modify the schema
        schema = {'questions': [{'id': 'Q1', 'type': 'ordinal', 'name': 'Custom', 'min': 0, 'max': 1, 'labels': {'0': 'No', '1': 'Yes'}}]}
        study_with_schema.rating_schema = schema
        db.session.commit()

        resp = client.post(f'/api/admin/studies/{study_with_schema.id}/schema/reset')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['rating_schema']['questions']) == 6

    def test_reset_schema_on_active_study_forbidden(self, client, admin_user, active_study_with_ratings):
        """POST /api/admin/studies/:id/schema/reset returns 403 when study is active."""
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{active_study_with_ratings.id}/schema/reset')
        assert resp.status_code == 403


# ===========================================================================
# Test: Readiness & Lifecycle
# ===========================================================================

class TestStudyLifecycle:

    def test_get_readiness_checklist(self, client, admin_user, ready_study):
        """GET /api/admin/studies/:id/readiness returns checklist items."""
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{ready_study.id}/readiness')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'checklist' in data
        assert len(data['checklist']) == 4

    def test_activate_study_ready(self, client, admin_user, ready_study, db):
        """POST /api/admin/studies/:id/activate succeeds when all requirements met."""
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{ready_study.id}/activate')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'active'

        db.session.refresh(ready_study)
        assert ready_study.status == 'active'

    def test_activate_study_not_ready(self, client, admin_user, study_with_schema):
        """POST /api/admin/studies/:id/activate returns 400 when not ready (no images/participants)."""
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{study_with_schema.id}/activate')
        assert resp.status_code == 400
        assert 'checklist' in resp.get_json()

    def test_activate_active_study_returns_400(self, client, admin_user, ready_study, db):
        """POST /api/admin/studies/:id/activate returns 400 when already active."""
        login_admin(client)
        ready_study.status = 'active'
        db.session.commit()

        resp = client.post(f'/api/admin/studies/{ready_study.id}/activate')
        assert resp.status_code == 400
        assert 'draft' in resp.get_json()['error'].lower()

    def test_reopen_study_full_rollback(self, client, admin_user, db, test_user):
        """POST /api/admin/studies/:id/reopen deletes ratings and resets participant state."""
        login_admin(client)
        study = create_study_with_images(db, n=3)
        study.status = 'active'

        sp = StudyParticipant(study_id=study.id, user_id=test_user.id, random_seed=42,
                         submitted=True)
        db.session.add(sp)
        db.session.flush()

        images = DatasetImage.query.filter_by(study_id=study.id).all()
        sp.last_viewed_image_id = images[0].id

        for img in images:
            r = Rating(user_id=test_user.id, dataset_image_id=img.id,
                       study_id=study.id, responses={'F1': 2})
            db.session.add(r)
        db.session.commit()

        assert Rating.query.filter_by(study_id=study.id).count() == 3

        resp = client.post(f'/api/admin/studies/{study.id}/reopen')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'draft'
        assert data['deleted_ratings'] == 3

        db.session.refresh(study)
        assert study.status == 'draft'
        assert Rating.query.filter_by(study_id=study.id).count() == 0

        db.session.refresh(sp)
        assert sp.submitted is False
        assert sp.submitted_at is None
        assert sp.last_viewed_image_id is None

    def test_reopen_draft_study_returns_400(self, client, admin_user, db):
        """POST /api/admin/studies/:id/reopen returns 400 for draft study."""
        login_admin(client)
        study = create_study_with_images(db, n=2)
        assert study.status == 'draft'

        resp = client.post(f'/api/admin/studies/{study.id}/reopen')
        assert resp.status_code == 400

    def test_deactivate_endpoint_removed(self, client, admin_user, db):
        """POST /api/admin/studies/:id/deactivate returns 404/405 (endpoint removed)."""
        login_admin(client)
        study = create_study_with_images(db, n=2)
        study.status = 'active'
        db.session.commit()

        resp = client.post(f'/api/admin/studies/{study.id}/deactivate')
        assert resp.status_code in (404, 405)

    def test_non_draft_study_blocks_schema_edit(self, client, admin_user, active_study_with_ratings):
        """PUT /api/admin/studies/:id/schema returns 403 when study is active."""
        login_admin(client)
        resp = client.put(f'/api/admin/studies/{active_study_with_ratings.id}/schema', json={
            'schema': get_default_rating_schema(),
        })
        assert resp.status_code == 403

    def test_draft_study_allows_schema_edit(self, client, admin_user, db):
        """PUT /api/admin/studies/:id/schema succeeds when study is in draft."""
        study = create_study_with_images(db, n=2)
        assert study.status == 'draft'

        login_admin(client)
        resp = client.put(f'/api/admin/studies/{study.id}/schema', json={
            'schema': get_default_rating_schema(),
        })
        assert resp.status_code == 200


# ===========================================================================
# Test: Access Control
# ===========================================================================

class TestStudyAccessControl:

    def test_participant_cannot_access_admin_studies(self, client, test_user, study_with_schema):
        """Participant gets 403 on admin study endpoints."""
        login_participant(client)
        resp = client.get('/api/admin/studies')
        assert resp.status_code == 403

    def test_participant_cannot_create_study(self, client, test_user):
        """Participant gets 403 trying to create a study."""
        login_participant(client)
        resp = client.post('/api/admin/studies', json={'name': 'Sneaky'})
        assert resp.status_code == 403


# ===========================================================================
# Test: Finished State
# ===========================================================================

def _rate_all_images(db_session, user, study):
    """Create complete ratings for every image in the study for the given user."""
    schema = study.rating_schema or {'questions': []}
    ordinal_ids = [q['id'] for q in schema.get('questions', []) if q.get('type') == 'ordinal']
    images = DatasetImage.query.filter_by(study_id=study.id).all()
    for img in images:
        responses = {qid: 1 for qid in ordinal_ids}
        rating = Rating(
            user_id=user.id,
            dataset_image_id=img.id,
            study_id=study.id,
            responses=responses,
        )
        db_session.session.add(rating)
    db_session.session.commit()


class TestFinishedState:

    def test_auto_finish_on_last_submission(self, client, admin_user, db):
        """When all non-test participants submit, study transitions to finished."""
        study, participants = create_full_study(db, n_images=2, n_participants=2)
        assert study.status == 'active'

        # Rate all images for both participants
        for p in participants:
            _rate_all_images(db, p, study)

        # Submit first participant
        login_participant(client, participants[0].email, 'testpassword')
        resp = client.post(f'/api/studies/{study.id}/submit')
        assert resp.status_code == 200

        db.session.refresh(study)
        assert study.status == 'active'  # not finished yet

        # Logout and submit second participant
        client.post('/api/auth/logout')
        login_participant(client, participants[1].email, 'testpassword')
        resp = client.post(f'/api/studies/{study.id}/submit')
        assert resp.status_code == 200

        db.session.refresh(study)
        assert study.status == 'finished'

    def test_auto_finish_on_unassign(self, client, admin_user, db):
        """Unassigning a non-submitted participant can trigger auto-finish."""
        study, participants = create_full_study(db, n_images=2, n_participants=2)

        # Only first participant rates and submits
        _rate_all_images(db, participants[0], study)
        sp0 = StudyParticipant.query.filter_by(
            study_id=study.id, user_id=participants[0].id,
        ).first()
        sp0.submitted = True
        db.session.commit()

        login_admin(client)

        # Unassign the non-submitted participant — should trigger auto-finish
        resp = client.post(f'/api/admin/studies/{study.id}/participants/unassign', json={
            'user_id': participants[1].id,
            'confirm': True,
        })
        assert resp.status_code == 200

        db.session.refresh(study)
        assert study.status == 'finished'

    def test_no_auto_finish_on_zero_participants(self, client, admin_user, db):
        """Unassigning the last participant does NOT trigger auto-finish (no vacuous truth)."""
        study, participants = create_full_study(db, n_images=2, n_participants=1)

        login_admin(client)

        resp = client.post(f'/api/admin/studies/{study.id}/participants/unassign', json={
            'user_id': participants[0].id,
            'confirm': True,
        })
        assert resp.status_code == 200

        db.session.refresh(study)
        assert study.status == 'active'

    def test_reopen_blocked_on_finished(self, client, admin_user, db):
        """Finished studies cannot be reverted to draft."""
        study, participants = create_full_study(db, n_images=2, n_participants=1)
        study.status = 'finished'
        db.session.commit()

        login_admin(client)
        resp = client.post(f'/api/admin/studies/{study.id}/reopen')
        assert resp.status_code == 400
        assert 'finished' in resp.get_json()['error'].lower()

    def test_assign_on_finished_requires_reactivate(self, client, admin_user, db):
        """Assigning to a finished study without reactivate flag returns 403."""
        study, _ = create_full_study(db, n_images=2, n_participants=1)
        study.status = 'finished'
        db.session.commit()

        new_user = User(
            first_name='New', last_name='User', email='newuser@test.com',
            institution='Test', role='participant', is_test_user=False,
        )
        new_user.set_password('testpassword')
        db.session.add(new_user)
        db.session.commit()

        login_admin(client)
        resp = client.post(f'/api/admin/studies/{study.id}/participants/assign', json={
            'user_id': new_user.id,
        })
        assert resp.status_code == 403

    def test_assign_on_finished_with_reactivate(self, client, admin_user, db):
        """Assigning to a finished study with reactivate reverts status to active."""
        study, _ = create_full_study(db, n_images=2, n_participants=1)
        study.status = 'finished'
        db.session.commit()

        new_user = User(
            first_name='New', last_name='User', email='newuser@test.com',
            institution='Test', role='participant', is_test_user=False,
        )
        new_user.set_password('testpassword')
        db.session.add(new_user)
        db.session.commit()

        login_admin(client)
        resp = client.post(f'/api/admin/studies/{study.id}/participants/assign', json={
            'user_id': new_user.id,
            'reactivate': True,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['reactivated'] is True

        db.session.refresh(study)
        assert study.status == 'active'

    def test_unassign_allowed_on_finished(self, client, admin_user, db):
        """Can unassign participants from a finished study."""
        study, participants = create_full_study(db, n_images=2, n_participants=1)
        study.status = 'finished'
        db.session.commit()

        login_admin(client)
        resp = client.post(f'/api/admin/studies/{study.id}/participants/unassign', json={
            'user_id': participants[0].id,
            'confirm': True,
        })
        assert resp.status_code == 200

    def test_unsubmit_blocked_on_finished(self, client, admin_user, db):
        """Cannot unsubmit a participant on a finished study."""
        study, participants = create_full_study(db, n_images=2, n_participants=1)
        study.status = 'finished'

        sp = StudyParticipant.query.filter_by(
            study_id=study.id, user_id=participants[0].id,
        ).first()
        sp.submitted = True
        db.session.commit()

        login_admin(client)
        resp = client.post(
            f'/api/admin/studies/{study.id}/participants/{participants[0].id}/unsubmit',
        )
        assert resp.status_code == 403
