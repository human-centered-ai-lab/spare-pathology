"""Regression coverage for access control, study lifecycle, and data validation."""

import csv

import pytest

from app import db
from app.models import DatasetImage, Study, StudyParticipant, User
from app.services.schema_service import (
    compute_pass_fail,
    get_default_rating_schema,
    get_default_pass_fail_config,
    validate_schema,
    validate_pass_fail_config,
)
from tests.helpers import (
    create_study_with_images,
    login_admin,
    login_participant,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture()
def active_study_with_participant(db, test_user):
    """Create an active study with images and an assigned participant."""
    study = create_study_with_images(db, n=5)
    study.status = 'active'
    sp = StudyParticipant(
        study_id=study.id,
        user_id=test_user.id,
        random_seed=42,
    )
    db.session.add(sp)
    db.session.commit()
    return study, test_user, sp


# ===========================================================================
# open_rating submission check
# ===========================================================================

class TestOpenRatingSubmissionCheck:

    def test_open_rating_blocked_after_submission(self, client, admin_user, active_study_with_participant):
        """open_rating returns 403 if user has already submitted."""
        study, user, sp = active_study_with_participant
        images = DatasetImage.query.filter_by(study_id=study.id).all()

        # Mark user as submitted
        sp.submitted = True
        db.session.commit()

        login_participant(client)
        resp = client.post('/api/ratings/open', json={
            'study_id': study.id,
            'dataset_image_id': images[0].id,
        })
        assert resp.status_code == 403
        assert 'submitted' in resp.get_json()['error'].lower()


# ===========================================================================
# open_rating study_id filter
# ===========================================================================

class TestOpenRatingStudyIdFilter:

    def test_open_rating_scoped_to_study(self, client, db, admin_user, test_user):
        """Ratings are scoped per study -- same image in two studies gets separate ratings."""
        # Create two active studies with the same image path
        s1 = Study(name='S1', status='active', rating_schema=get_default_rating_schema(), dataset_name='ds')
        s2 = Study(name='S2', status='active', rating_schema=get_default_rating_schema(), dataset_name='ds')
        db.session.add_all([s1, s2])
        db.session.flush()

        img1 = DatasetImage(study_id=s1.id, image_path='ds/img.png', attributes={}, sequence_number=1)
        img2 = DatasetImage(study_id=s2.id, image_path='ds/img.png', attributes={}, sequence_number=1)
        db.session.add_all([img1, img2])
        db.session.flush()

        sp1 = StudyParticipant(study_id=s1.id, user_id=test_user.id, random_seed=42)
        sp2 = StudyParticipant(study_id=s2.id, user_id=test_user.id, random_seed=42)
        db.session.add_all([sp1, sp2])
        db.session.commit()

        login_participant(client)

        # Open rating in study 1
        resp1 = client.post('/api/ratings/open', json={
            'study_id': s1.id,
            'dataset_image_id': img1.id,
        })
        assert resp1.status_code == 201
        rating1_id = resp1.get_json()['id']

        # Open rating in study 2 -- should create a separate rating
        resp2 = client.post('/api/ratings/open', json={
            'study_id': s2.id,
            'dataset_image_id': img2.id,
        })
        assert resp2.status_code == 201
        rating2_id = resp2.get_json()['id']

        assert rating1_id != rating2_id


# ===========================================================================
# compute_pass_fail partial responses
# ===========================================================================

class TestComputePassFailPartial:

    def test_partial_responses_return_none(self):
        """Partially answered ordinal questions should return None (indeterminate)."""
        schema = get_default_rating_schema()
        config = get_default_pass_fail_config()
        # Only answer 3 of the 6 total_score_questions
        responses = {'F1': 2, 'F2': 2, 'F3': 2}
        result = compute_pass_fail(responses, schema, config)
        assert result is None

    def test_all_answered_returns_bool(self):
        """Fully answered questions should return True or False."""
        schema = get_default_rating_schema()
        config = get_default_pass_fail_config()
        responses = {'F1': 2, 'F2': 2, 'F3': 2, 'F4': 2, 'F5': 2, 'F6': 2}
        result = compute_pass_fail(responses, schema, config)
        assert result is True

    def test_no_answers_returns_none(self):
        """No answers should return None."""
        schema = get_default_rating_schema()
        config = get_default_pass_fail_config()
        result = compute_pass_fail({}, schema, config)
        assert result is None


# ===========================================================================
# validate_schema invalid ordinal not in ordinal_ids
# ===========================================================================

class TestValidateSchemaInvalidOrdinal:

    def test_invalid_ordinal_not_in_ids(self):
        """An ordinal question with invalid min/max is caught by schema validation.
        Referencing a nonexistent question in pass_fail_config should be an error."""
        schema = {
            'questions': [
                {
                    'id': 'Q1',
                    'type': 'ordinal',
                    'name': 'Bad question',
                    'min': 5,
                    'max': 3,  # invalid: min >= max
                },
            ],
        }
        schema_errors = validate_schema(schema)
        assert any('min must be less than max' in e for e in schema_errors)

        # Referencing a nonexistent question should be flagged
        config = {
            'total_score_questions': ['NONEXISTENT'],
            'conditions': [],
        }
        config_errors = validate_pass_fail_config(config, schema)
        assert any('unknown ordinal' in e.lower() for e in config_errors)


# ===========================================================================
# Admin self-delete and self-role-change blocked
# ===========================================================================

class TestAdminSelfProtection:

    def test_admin_cannot_delete_self(self, client, admin_user):
        """Admin should get 400 when trying to delete their own account."""
        login_admin(client)
        resp = client.delete(f'/api/admin/users/{admin_user.id}?confirm=yes')
        assert resp.status_code == 400
        assert 'own account' in resp.get_json()['error'].lower()

    def test_admin_cannot_change_own_role(self, client, admin_user):
        """Admin should get 400 when trying to change their own role."""
        login_admin(client)
        resp = client.put(f'/api/admin/users/{admin_user.id}', json={
            'first_name': admin_user.first_name,
            'last_name': admin_user.last_name,
            'email': admin_user.email,
            'role': 'participant',
            'institution': 'Test',
        })
        assert resp.status_code == 400
        assert 'own role' in resp.get_json()['errors'][0].lower()

    def test_admin_can_update_self_without_role_change(self, client, admin_user):
        """Admin should be able to update own details if role stays the same."""
        login_admin(client)
        resp = client.put(f'/api/admin/users/{admin_user.id}', json={
            'first_name': 'Updated',
            'last_name': admin_user.last_name,
            'email': admin_user.email,
            'role': 'admin',
        })
        assert resp.status_code == 200


# ===========================================================================
# Reopen status guards
# ===========================================================================

class TestLifecycleStatusGuards:

    def test_reopen_draft_returns_400(self, client, admin_user, sample_study):
        """Reopening an already-draft study should return 400."""
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{sample_study.id}/reopen')
        assert resp.status_code == 400
        assert resp.get_json()['error']

    def test_reopen_active_succeeds(self, client, admin_user, active_study_with_participant):
        """Reopening an active study should succeed."""
        study, _, _ = active_study_with_participant
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{study.id}/reopen')
        assert resp.status_code == 200


# ===========================================================================
# Participant image authorization
# ===========================================================================

class TestParticipantImageAuthorization:

    def test_unassigned_participant_blocked(self, client, db, test_user):
        """A participant not assigned to any study with the image gets 403."""
        study = Study(name='S', status='active', rating_schema={'questions': []})
        db.session.add(study)
        db.session.flush()
        di = DatasetImage(study_id=study.id, image_path='ds/img.png', attributes={}, sequence_number=1)
        db.session.add(di)
        db.session.commit()
        # test_user is NOT assigned to the study

        login_participant(client)
        resp = client.get('/api/studies/images/ds/img.png')
        assert resp.status_code == 403

    def test_test_user_can_access_any_image(self, client, db, admin_user):
        """A test user should be able to access any image."""
        test_usr = User(
            first_name='T', last_name='U', email='tester@t.com',
            role='participant', is_test_user=True,
        )
        test_usr.set_password('pass')
        db.session.add(test_usr)
        db.session.flush()

        study = Study(name='S', status='active', rating_schema={'questions': []})
        db.session.add(study)
        db.session.flush()
        di = DatasetImage(study_id=study.id, image_path='ds/test.png', attributes={}, sequence_number=1)
        db.session.add(di)
        db.session.commit()

        # Log in as test user -- 404 expected because file doesn't exist, but NOT 403
        client.post('/api/auth/login', json={'email': 'tester@t.com', 'password': 'pass'})
        resp = client.get('/api/studies/images/ds/test.png')
        # Should get 404 (file not found) not 403 (unauthorized)
        assert resp.status_code == 404


# ===========================================================================
# Dataset 404 for nonexistent datasets
# ===========================================================================

class TestDataset404:

    def test_browse_nonexistent_dataset(self, client, admin_user, tmp_path):
        """Browsing a nonexistent dataset returns 404."""
        with client.application.app_context():
            client.application.config['DATASETS_DIR'] = str(tmp_path)

        login_admin(client)
        resp = client.get('/api/admin/datasets/nonexistent_dataset/images')
        assert resp.status_code == 404
        assert 'not found' in resp.get_json()['error'].lower()

    def test_attributes_nonexistent_dataset(self, client, admin_user, tmp_path):
        """Getting attributes for a nonexistent dataset returns 404."""
        with client.application.app_context():
            client.application.config['DATASETS_DIR'] = str(tmp_path)

        login_admin(client)
        resp = client.get('/api/admin/datasets/nonexistent_dataset/attributes')
        assert resp.status_code == 404
        assert 'not found' in resp.get_json()['error'].lower()


# ===========================================================================
# Toggle-remove reverts submitted users
# ===========================================================================

class TestToggleRemoveRevertsSubmitted:

    def test_toggle_remove_reverts_submitted(self, client, admin_user, db, test_user):
        """Removing an image via toggle should revert submitted users."""
        study = Study(name='S', status='draft', rating_schema={'questions': []})
        db.session.add(study)
        db.session.flush()

        di = DatasetImage(study_id=study.id, image_path='ds/img.png', attributes={}, sequence_number=1)
        db.session.add(di)

        sp = StudyParticipant(study_id=study.id, user_id=test_user.id, random_seed=42, submitted=True)
        db.session.add(sp)
        db.session.commit()

        assert sp.submitted is True

        login_admin(client)
        resp = client.post(f'/api/admin/studies/{study.id}/dataset/toggle', json={
            'image_path': 'ds/img.png',
        })
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'removed'

        db.session.refresh(sp)
        assert sp.submitted is False
        assert sp.submitted_at is None


# ===========================================================================
# Stats cache invalidation on unassign
# ===========================================================================

class TestUnassignStatsCacheInvalidation:

    def test_unassign_calls_invalidate_stats_cache(self, client, admin_user, db, test_user, monkeypatch):
        """Unassigning a participant should invalidate the stats cache."""
        study = create_study_with_images(db, n=3)
        study.status = 'active'
        sp = StudyParticipant(study_id=study.id, user_id=test_user.id, random_seed=42)
        db.session.add(sp)
        db.session.commit()

        invalidated_ids = []
        from app.services import statistics
        original_invalidate = statistics.invalidate_stats_cache
        def mock_invalidate(sid=None):
            invalidated_ids.append(sid)
            return original_invalidate(sid)

        monkeypatch.setattr('app.api.admin_participants.invalidate_stats_cache', mock_invalidate)

        login_admin(client)
        resp = client.post(f'/api/admin/studies/{study.id}/participants/unassign', json={
            'user_id': test_user.id,
            'confirm': True,
        })
        assert resp.status_code == 200
        assert study.id in invalidated_ids


# ===========================================================================
# scan_datasets correct count
# ===========================================================================

class TestScanDatasetsCount:

    def test_empty_rows_not_counted(self, tmp_path):
        """scan_datasets should not count rows with empty image_name."""
        ds_dir = tmp_path / 'test_ds'
        ds_dir.mkdir()
        csv_path = ds_dir / 'metadata.csv'
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['image_name', 'attr1'])
            writer.writerow(['img1.png', 'val1'])
            writer.writerow(['', 'val2'])  # empty image_name
            writer.writerow(['  ', 'val3'])  # whitespace-only image_name
            writer.writerow(['img2.png', 'val4'])

        from app.services.image_scanner import scan_datasets
        results = scan_datasets(str(tmp_path))
        assert len(results) == 1
        assert results[0]['image_count'] == 2  # Only img1.png and img2.png


# ===========================================================================
# _get_study_access status check
# ===========================================================================

class TestRatingStudyStatusCheck:

    def test_non_active_study_blocked_for_participant(self, client, db, admin_user, test_user):
        """Non-active study should block rating access for regular participants."""
        study = Study(
            name='Draft Study',
            status='draft',
            rating_schema=get_default_rating_schema(),
        )
        db.session.add(study)
        db.session.flush()

        di = DatasetImage(study_id=study.id, image_path='ds/img.png', attributes={}, sequence_number=1)
        db.session.add(di)

        sp = StudyParticipant(study_id=study.id, user_id=test_user.id, random_seed=42)
        db.session.add(sp)
        db.session.commit()

        login_participant(client)
        resp = client.post('/api/ratings/open', json={
            'study_id': study.id,
            'dataset_image_id': di.id,
        })
        assert resp.status_code == 403
        assert 'not active' in resp.get_json()['error'].lower()

    def test_test_user_can_access_draft_study(self, client, db, admin_user):
        """Test users should be able to access non-active studies."""
        tester = User(
            first_name='T', last_name='U', email='tester2@t.com',
            role='participant', is_test_user=True,
        )
        tester.set_password('pass')
        db.session.add(tester)
        db.session.flush()

        study = Study(
            name='Draft Study',
            status='draft',
            rating_schema=get_default_rating_schema(),
        )
        db.session.add(study)
        db.session.flush()

        di = DatasetImage(study_id=study.id, image_path='ds/img.png', attributes={}, sequence_number=1)
        db.session.add(di)
        db.session.commit()

        client.post('/api/auth/login', json={'email': 'tester2@t.com', 'password': 'pass'})
        resp = client.post('/api/ratings/open', json={
            'study_id': study.id,
            'dataset_image_id': di.id,
        })
        assert resp.status_code == 201


# ===========================================================================
# int() cast validation
# ===========================================================================

class TestIntCastValidation:

    def test_assign_participant_bad_user_id(self, client, admin_user, sample_study):
        """Assigning with non-numeric user_id should return 400."""
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{sample_study.id}/participants/assign', json={
            'user_id': 'abc',
        })
        assert resp.status_code == 400

    def test_unassign_participant_bad_user_id(self, client, admin_user, sample_study):
        """Unassigning with non-numeric user_id should return 400."""
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{sample_study.id}/participants/unassign', json={
            'user_id': 'xyz',
        })
        assert resp.status_code == 400


# ===========================================================================
# User creation with bad study_ids
# ===========================================================================

class TestUserCreationBadStudyIds:

    def test_nonexistent_study_id(self, client, admin_user):
        """Creating a user with a nonexistent study_id should return 400."""
        login_admin(client)
        resp = client.post('/api/admin/users', json={
            'first_name': 'New',
            'last_name': 'User',
            'email': 'newuser@test.com',
            'role': 'participant',
            'institution': 'Test',
            'password': 'testpass',
            'study_ids': [99999],
        })
        assert resp.status_code == 400

    def test_invalid_study_id_string(self, client, admin_user):
        """Creating a user with a non-numeric study_id should return 400."""
        login_admin(client)
        resp = client.post('/api/admin/users', json={
            'first_name': 'New',
            'last_name': 'User',
            'email': 'newuser2@test.com',
            'role': 'participant',
            'institution': 'Test',
            'password': 'testpass',
            'study_ids': ['abc'],
        })
        assert resp.status_code == 400


# ===========================================================================
# Settings partial update
# ===========================================================================

class TestSettingsPartialUpdate:

    def test_update_name_only(self, client, admin_user, sample_study):
        """Sending only name should update name and leave other fields unchanged."""
        sample_study.description = 'Original desc'
        sample_study.uncertainty_enabled = True
        sample_study.session_instruction = 'Original instruction'
        db.session.commit()

        login_admin(client)
        resp = client.put(f'/api/admin/studies/{sample_study.id}/settings', json={
            'name': 'New Name',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['name'] == 'New Name'
        assert data['description'] == 'Original desc'
        assert data['uncertainty_enabled'] is True
        assert data['session_instruction'] == 'Original instruction'

    def test_update_description_only(self, client, admin_user, sample_study):
        """Sending only description should update it without touching name."""
        login_admin(client)
        resp = client.put(f'/api/admin/studies/{sample_study.id}/settings', json={
            'description': 'Updated desc',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['name'] == sample_study.name
        assert data['description'] == 'Updated desc'

    def test_empty_name_rejected(self, client, admin_user, sample_study):
        """Sending an empty name should return 400."""
        login_admin(client)
        resp = client.put(f'/api/admin/studies/{sample_study.id}/settings', json={
            'name': '',
        })
        assert resp.status_code == 400

    def test_no_fields_is_noop(self, client, admin_user, sample_study):
        """Sending empty body should succeed without changing anything."""
        login_admin(client)
        resp = client.put(f'/api/admin/studies/{sample_study.id}/settings', json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['name'] == sample_study.name
