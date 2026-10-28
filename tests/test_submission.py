"""Tests for submission flow: completion check, submit, read-only mode, test user reset."""

import pytest

from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import get_default_rating_schema


# ---------------------------------------------------------------------------
# Helper: log in as a participant via API
# ---------------------------------------------------------------------------

def _login(client, email, password):
    return client.post('/api/auth/login', json={
        'email': email,
        'password': password,
    })


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def eval_study(db):
    """Create a study with the default rating schema and 3 images."""
    study = Study(
        name='Submission Study',
        description='Study for submission tests',
        status='active',
        rating_schema=get_default_rating_schema(),
        uncertainty_enabled=True,
    )
    db.session.add(study)
    db.session.flush()

    for i in range(1, 4):
        img = DatasetImage(
            study_id=study.id,
            image_path=f'submit_dataset/image_{i}.png',
            attributes={
                'synthetic': (i % 2 == 0),
                'tissue_type': 'Tumor-dominant',
                'mpp_value': 0.5,
            },
            sequence_number=i,
        )
        db.session.add(img)

    db.session.commit()
    return study


@pytest.fixture()
def eval_study_with_freetext(db):
    """Create a study with ordinal + free_text questions and 2 images."""
    schema = get_default_rating_schema()
    # Add a free text question
    schema['questions'].append({
        'id': 'notes',
        'type': 'free_text',
        'name': 'Additional notes',
        'description': 'Any other observations',
    })
    study = Study(
        name='Freetext Study',
        description='Study with freetext for submission tests',
        status='active',
        rating_schema=schema,
    )
    db.session.add(study)
    db.session.flush()

    for i in range(1, 3):
        img = DatasetImage(
            study_id=study.id,
            image_path=f'freetext_dataset/image_{i}.png',
            attributes={'synthetic': False},
            sequence_number=i,
        )
        db.session.add(img)

    db.session.commit()
    return study


@pytest.fixture()
def assigned_user(db, test_user, eval_study):
    """Assign test_user to eval_study."""
    sp = StudyParticipant(
        study_id=eval_study.id,
        user_id=test_user.id,
        random_seed=42,
    )
    db.session.add(sp)
    db.session.commit()
    return test_user


COMPLETE_RESPONSES = {'F1': 2, 'F2': 1, 'F3': 2, 'F4': 1, 'F5': 2, 'F6': 2}


def _rate_all_images(db, user, study, responses=None):
    """Create complete ratings for all images in a study."""
    if responses is None:
        responses = COMPLETE_RESPONSES
    images = DatasetImage.query.filter_by(study_id=study.id).all()
    for img in images:
        rating = Rating(
            user_id=user.id,
            dataset_image_id=img.id,
            study_id=study.id,
            responses=dict(responses),
        )
        db.session.add(rating)
    db.session.commit()


# ===========================================================================
# Test: GET /api/studies/<id>/completion-status
# ===========================================================================

class TestCompletionStatus:

    def test_all_images_rated_complete(self, client, assigned_user, eval_study, db):
        """When all images have all ordinal answers, complete=true."""
        _rate_all_images(db, assigned_user, eval_study)

        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/completion-status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['complete'] is True
        assert data['total_images'] == 3
        assert data['completed_images'] == 3
        assert data['incomplete_images'] == []

    def test_missing_ratings_incomplete(self, client, assigned_user, eval_study, db):
        """When some images have missing ordinal answers, complete=false with details."""
        images = DatasetImage.query.filter_by(study_id=eval_study.id).order_by(DatasetImage.id).all()

        # Rate first image completely
        r1 = Rating(
            user_id=assigned_user.id,
            dataset_image_id=images[0].id,
            study_id=eval_study.id,
            responses=COMPLETE_RESPONSES,
        )
        db.session.add(r1)

        # Rate second image partially (missing F3, F4)
        r2 = Rating(
            user_id=assigned_user.id,
            dataset_image_id=images[1].id,
            study_id=eval_study.id,
            responses={'F1': 2, 'F2': 1, 'F5': 2, 'F6': 2},
        )
        db.session.add(r2)

        # Third image not rated at all
        db.session.commit()

        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/completion-status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['complete'] is False
        assert data['total_images'] == 3
        assert data['completed_images'] == 1
        assert len(data['incomplete_images']) == 2

        # Check that missing question IDs are reported
        positions = {item['position'] for item in data['incomplete_images']}
        # Positions may vary due to randomization, but we should have exactly 2 incomplete
        assert len(positions) == 2

        # One incomplete entry should have exactly 2 missing (F3, F4) - the partial one
        # The other should have all 6 missing - the unrated one
        missing_counts = sorted([len(item['missing']) for item in data['incomplete_images']])
        assert missing_counts == [2, 6]

        # Find the partially rated image entry (2 missing)
        for item in data['incomplete_images']:
            if len(item['missing']) == 2:
                assert 'F3' in item['missing']
                assert 'F4' in item['missing']

    def test_no_ratings_at_all(self, client, assigned_user, eval_study, db):
        """When no images are rated, all are incomplete."""
        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/completion-status')
        data = resp.get_json()
        assert data['complete'] is False
        assert data['completed_images'] == 0
        assert data['total_images'] == 3
        assert len(data['incomplete_images']) == 3


# ===========================================================================
# Test: POST /api/studies/<study_id>/submit
# ===========================================================================

class TestSubmit:

    def test_submit_sets_submitted_true(self, client, assigned_user, eval_study, db):
        """Submit sets StudyParticipant.submitted=True and submitted_at=now."""
        _rate_all_images(db, assigned_user, eval_study)

        _login(client, 'participant@example.com', 'testpassword')
        resp = client.post(f'/api/studies/{eval_study.id}/submit')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert 'submitted_at' in data

        # Verify database
        sp = StudyParticipant.query.filter_by(
            study_id=eval_study.id,
            user_id=assigned_user.id,
        ).first()
        assert sp.submitted is True
        assert sp.submitted_at is not None

    def test_submit_invalidates_stats_cache(self, client, assigned_user, eval_study, db, monkeypatch):
        """Submit should invalidate cached statistics for the study."""
        _rate_all_images(db, assigned_user, eval_study)

        invalidated_ids = []

        def mock_invalidate(study_id=None):
            invalidated_ids.append(study_id)

        monkeypatch.setattr('app.api.studies.invalidate_stats_cache', mock_invalidate)

        _login(client, 'participant@example.com', 'testpassword')
        resp = client.post(f'/api/studies/{eval_study.id}/submit')
        assert resp.status_code == 200
        assert eval_study.id in invalidated_ids

    def test_submit_fails_if_not_all_complete(self, client, assigned_user, eval_study, db):
        """Submit returns 400 if not all images have all ordinal answers."""
        images = DatasetImage.query.filter_by(study_id=eval_study.id).all()

        # Rate only the first image
        r = Rating(
            user_id=assigned_user.id,
            dataset_image_id=images[0].id,
            study_id=eval_study.id,
            responses=COMPLETE_RESPONSES,
        )
        db.session.add(r)
        db.session.commit()

        _login(client, 'participant@example.com', 'testpassword')
        resp = client.post(f'/api/studies/{eval_study.id}/submit')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

        # Verify not submitted
        sp = StudyParticipant.query.filter_by(
            study_id=eval_study.id,
            user_id=assigned_user.id,
        ).first()
        assert sp.submitted is False

    def test_submit_fails_with_partial_responses(self, client, assigned_user, eval_study, db):
        """Submit fails when an image has some but not all ordinal answers."""
        images = DatasetImage.query.filter_by(study_id=eval_study.id).all()

        for img in images:
            # Missing F6
            r = Rating(
                user_id=assigned_user.id,
                dataset_image_id=img.id,
                study_id=eval_study.id,
                responses={'F1': 2, 'F2': 1, 'F3': 2, 'F4': 1, 'F5': 2},
            )
            db.session.add(r)
        db.session.commit()

        _login(client, 'participant@example.com', 'testpassword')
        resp = client.post(f'/api/studies/{eval_study.id}/submit')
        assert resp.status_code == 400

    def test_submit_already_submitted_returns_400(self, client, assigned_user, eval_study, db):
        """Submitting again after already submitted returns 400."""
        _rate_all_images(db, assigned_user, eval_study)

        _login(client, 'participant@example.com', 'testpassword')
        resp1 = client.post(f'/api/studies/{eval_study.id}/submit')
        assert resp1.status_code == 200

        resp2 = client.post(f'/api/studies/{eval_study.id}/submit')
        assert resp2.status_code == 400
        assert 'Already submitted' in resp2.get_json()['error']

    def test_free_text_does_not_block_submission(self, client, test_user, eval_study_with_freetext, db):
        """Free-text questions do NOT block submission."""
        study = eval_study_with_freetext

        sp = StudyParticipant(
            study_id=study.id,
            user_id=test_user.id,
            random_seed=42,
        )
        db.session.add(sp)
        db.session.flush()

        images = DatasetImage.query.filter_by(study_id=study.id).all()
        for img in images:
            # All ordinal answered, free text (notes) NOT answered
            r = Rating(
                user_id=test_user.id,
                dataset_image_id=img.id,
                study_id=study.id,
                responses=COMPLETE_RESPONSES,
            )
            db.session.add(r)
        db.session.commit()

        _login(client, 'participant@example.com', 'testpassword')
        resp = client.post(f'/api/studies/{study.id}/submit')
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True


# ===========================================================================
# Test: After submission -- ratings are read-only (PUT returns 403)
# ===========================================================================

class TestReadOnlyAfterSubmission:

    def test_save_response_returns_403_after_submission(self, client, assigned_user, eval_study, db):
        """PUT /api/ratings/<id>/response returns 403 after submission."""
        _rate_all_images(db, assigned_user, eval_study)
        _login(client, 'participant@example.com', 'testpassword')

        # Submit
        client.post(f'/api/studies/{eval_study.id}/submit')

        # Try to save a response
        rating = Rating.query.filter_by(
            user_id=assigned_user.id,
            study_id=eval_study.id,
        ).first()
        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 0,
        })
        assert resp.status_code == 403

    def test_save_text_response_returns_403_after_submission(self, client, assigned_user, eval_study, db):
        """PUT /api/ratings/<id>/text-response returns 403 after submission."""
        _rate_all_images(db, assigned_user, eval_study)
        _login(client, 'participant@example.com', 'testpassword')
        client.post(f'/api/studies/{eval_study.id}/submit')

        rating = Rating.query.filter_by(
            user_id=assigned_user.id,
            study_id=eval_study.id,
        ).first()
        resp = client.put(f'/api/ratings/{rating.id}/text-response', json={
            'question_id': 'notes',
            'value': 'late change',
        })
        assert resp.status_code == 403

    def test_save_uncertainty_returns_403_after_submission(self, client, assigned_user, eval_study, db):
        """PUT /api/ratings/<id>/uncertainty returns 403 after submission."""
        _rate_all_images(db, assigned_user, eval_study)
        _login(client, 'participant@example.com', 'testpassword')
        client.post(f'/api/studies/{eval_study.id}/submit')

        rating = Rating.query.filter_by(
            user_id=assigned_user.id,
            study_id=eval_study.id,
        ).first()
        resp = client.put(f'/api/ratings/{rating.id}/uncertainty', json={
            'value': True,
        })
        assert resp.status_code == 403

    def test_save_time_returns_403_after_submission(self, client, assigned_user, eval_study, db):
        """PUT /api/ratings/<id>/time returns 403 after submission."""
        _rate_all_images(db, assigned_user, eval_study)
        _login(client, 'participant@example.com', 'testpassword')
        client.post(f'/api/studies/{eval_study.id}/submit')

        rating = Rating.query.filter_by(
            user_id=assigned_user.id,
            study_id=eval_study.id,
        ).first()
        resp = client.put(f'/api/ratings/{rating.id}/time', json={
            'elapsed': 5.0,
        })
        assert resp.status_code == 403

    def test_save_failure_reason_returns_403_after_submission(self, client, assigned_user, eval_study, db):
        """PUT /api/ratings/<id>/failure-reason returns 403 after submission."""
        _rate_all_images(db, assigned_user, eval_study)
        _login(client, 'participant@example.com', 'testpassword')
        client.post(f'/api/studies/{eval_study.id}/submit')

        rating = Rating.query.filter_by(
            user_id=assigned_user.id,
            study_id=eval_study.id,
        ).first()
        resp = client.put(f'/api/ratings/{rating.id}/failure-reason', json={
            'value': 'Some reason',
        })
        assert resp.status_code == 403


# ===========================================================================
# Test: POST /api/auth/test-user-reset -- reset test user data
# ===========================================================================

class TestTestUserReset:

    def test_reset_clears_all_ratings_and_submissions(self, client, db):
        """Test user reset clears all ratings and submission states across all studies."""
        test_user_account = User.query.filter_by(email='test').first()
        test_user_account.set_password('testpass')
        db.session.commit()

        # Create two studies
        s1 = Study(name='S1', status='active', rating_schema=get_default_rating_schema())
        s2 = Study(name='S2', status='active', rating_schema=get_default_rating_schema())
        db.session.add_all([s1, s2])
        db.session.flush()

        for study in [s1, s2]:
            for i in range(1, 3):
                img = DatasetImage(
                    study_id=study.id,
                    image_path=f'reset_test_{study.id}/img_{i}.png',
                    sequence_number=i,
                )
                db.session.add(img)

        db.session.flush()

        # Create study participants
        sp1 = StudyParticipant(study_id=s1.id, user_id=test_user_account.id, submitted=True)
        sp2 = StudyParticipant(study_id=s2.id, user_id=test_user_account.id, submitted=True)
        db.session.add_all([sp1, sp2])
        db.session.flush()

        # Create ratings
        for study in [s1, s2]:
            images = DatasetImage.query.filter_by(study_id=study.id).all()
            for img in images:
                r = Rating(
                    user_id=test_user_account.id,
                    dataset_image_id=img.id,
                    study_id=study.id,
                    responses=COMPLETE_RESPONSES,
                )
                db.session.add(r)
        db.session.commit()

        # Verify data exists
        assert Rating.query.filter_by(user_id=test_user_account.id).count() == 4
        assert StudyParticipant.query.filter_by(user_id=test_user_account.id, submitted=True).count() == 2

        _login(client, 'test', 'testpass')
        resp = client.post('/api/auth/test-user-reset')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

        # All ratings deleted
        assert Rating.query.filter_by(user_id=test_user_account.id).count() == 0

        # All study participants have submitted=False and submitted_at=None
        for sp in StudyParticipant.query.filter_by(user_id=test_user_account.id).all():
            assert sp.submitted is False
            assert sp.submitted_at is None

    def test_reset_only_accessible_by_test_user(self, client, test_user, db):
        """Regular participants cannot access the test user reset endpoint."""
        _login(client, 'participant@example.com', 'testpassword')
        resp = client.post('/api/auth/test-user-reset')
        assert resp.status_code == 403

    def test_reset_not_accessible_by_admin(self, client, admin_user, db):
        """Admin users cannot access the test user reset endpoint."""
        _login(client, 'admin', 'adminpassword')
        resp = client.post('/api/auth/test-user-reset')
        assert resp.status_code == 403

    def test_reset_not_accessible_unauthenticated(self, client, db):
        """Unauthenticated users get 401 on the test user reset endpoint."""
        resp = client.post('/api/auth/test-user-reset')
        assert resp.status_code == 401

    def test_reset_does_not_affect_other_users(self, client, test_user, db):
        """Test user reset does not affect other users' data."""
        test_user_account = User.query.filter_by(email='test').first()
        test_user_account.set_password('testpass')
        db.session.commit()

        # Create a study
        study = Study(name='Shared', status='active', rating_schema=get_default_rating_schema())
        db.session.add(study)
        db.session.flush()

        img = DatasetImage(
            study_id=study.id,
            image_path='shared/img.png',
            sequence_number=1,
        )
        db.session.add(img)
        db.session.flush()

        # Create ratings for both users
        sp_test = StudyParticipant(study_id=study.id, user_id=test_user_account.id, submitted=True)
        sp_regular = StudyParticipant(study_id=study.id, user_id=test_user.id, submitted=True)
        db.session.add_all([sp_test, sp_regular])
        db.session.flush()

        r_test = Rating(
            user_id=test_user_account.id,
            dataset_image_id=img.id,
            study_id=study.id,
            responses=COMPLETE_RESPONSES,
        )
        r_regular = Rating(
            user_id=test_user.id,
            dataset_image_id=img.id,
            study_id=study.id,
            responses=COMPLETE_RESPONSES,
        )
        db.session.add_all([r_test, r_regular])
        db.session.commit()

        _login(client, 'test', 'testpass')
        resp = client.post('/api/auth/test-user-reset')
        assert resp.status_code == 200

        # Test user data cleared
        assert Rating.query.filter_by(user_id=test_user_account.id).count() == 0

        # Regular user data preserved
        assert Rating.query.filter_by(user_id=test_user.id).count() == 1
        sp = StudyParticipant.query.filter_by(
            study_id=study.id,
            user_id=test_user.id,
        ).first()
        assert sp.submitted is True

    def test_reset_clears_last_viewed(self, client, db):
        """Test user reset clears last_viewed_image_id on all study participants."""
        test_user_account = User.query.filter_by(email='test').first()
        test_user_account.set_password('testpass')
        db.session.commit()

        study = Study(name='LV', status='active', rating_schema=get_default_rating_schema())
        db.session.add(study)
        db.session.flush()

        img = DatasetImage(
            study_id=study.id,
            image_path='lv/img.png',
            sequence_number=1,
        )
        db.session.add(img)
        db.session.flush()

        sp = StudyParticipant(
            study_id=study.id,
            user_id=test_user_account.id,
            last_viewed_image_id=img.id,
        )
        db.session.add(sp)
        db.session.commit()

        _login(client, 'test', 'testpass')
        client.post('/api/auth/test-user-reset')

        db.session.refresh(sp)
        assert sp.last_viewed_image_id is None

    def test_reset_returns_counts(self, client, db):
        """Test user reset returns counts of cleared data."""
        test_user_account = User.query.filter_by(email='test').first()
        test_user_account.set_password('testpass')
        db.session.commit()

        study = Study(name='Counts', status='active', rating_schema=get_default_rating_schema())
        db.session.add(study)
        db.session.flush()

        for i in range(1, 4):
            img = DatasetImage(
                study_id=study.id,
                image_path=f'counts/img_{i}.png',
                sequence_number=i,
            )
            db.session.add(img)
        db.session.flush()

        sp = StudyParticipant(study_id=study.id, user_id=test_user_account.id, submitted=True)
        db.session.add(sp)
        db.session.flush()

        images = DatasetImage.query.filter_by(study_id=study.id).all()
        for img in images:
            r = Rating(
                user_id=test_user_account.id,
                dataset_image_id=img.id,
                study_id=study.id,
                responses=COMPLETE_RESPONSES,
            )
            db.session.add(r)
        db.session.commit()

        _login(client, 'test', 'testpass')
        resp = client.post('/api/auth/test-user-reset')
        data = resp.get_json()
        assert data['ok'] is True
        assert data['ratings_deleted'] == 3
        assert data['studies_reset'] == 1
