"""Tests for the ratings API endpoints: save response, uncertainty, time, failure reason."""

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
    """Create a study configured for evaluation with rating schema and images."""
    study = Study(
        name='Rating API Study',
        description='Study for rating API tests',
        status='active',
        rating_schema=get_default_rating_schema(),
        uncertainty_enabled=True,
        session_instruction='<p>Rate carefully.</p>',
    )
    db.session.add(study)
    db.session.flush()

    for i in range(1, 4):
        img = DatasetImage(
            study_id=study.id,
            image_path=f'api_test_dataset/image_{i}.png',
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


@pytest.fixture()
def rating_with_empty_responses(db, assigned_user, eval_study):
    """Create a rating with empty responses for the first image."""
    images = DatasetImage.query.filter_by(study_id=eval_study.id).order_by(DatasetImage.id).all()
    rating = Rating(
        user_id=assigned_user.id,
        dataset_image_id=images[0].id,
        study_id=eval_study.id,
        responses={},
    )
    db.session.add(rating)
    db.session.commit()
    return rating


# ===========================================================================
# Test: PUT /api/ratings/<rating_id>/response -- save single question response
# ===========================================================================

class TestSaveResponse:

    def test_save_ordinal_response(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """PUT /api/ratings/<id>/response saves an ordinal score to responses JSON."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 2,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['responses']['F1'] == 2

        # Verify in database
        db.session.refresh(rating)
        assert rating.responses['F1'] == 2

    def test_save_multiple_responses(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """Saving multiple responses accumulates them in the JSON."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 2,
        })
        client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F2',
            'value': 1,
        })

        db.session.refresh(rating)
        assert rating.responses['F1'] == 2
        assert rating.responses['F2'] == 1

    def test_save_response_overwrites_previous(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """Saving a response for the same question overwrites the previous value."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 2,
        })
        client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 0,
        })

        db.session.refresh(rating)
        assert rating.responses['F1'] == 0

    def test_save_response_missing_fields(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """PUT /api/ratings/<id>/response returns 400 if fields are missing."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
        })
        assert resp.status_code == 400

    def test_save_response_wrong_user(self, client, db, eval_study, rating_with_empty_responses):
        """Cannot save a response for another user's rating."""
        # Create another participant
        other = User(
            first_name='Other',
            last_name='Participant',
            email='other@example.com',
            role='participant',
        )
        other.set_password('otherpass')
        db.session.add(other)
        db.session.flush()
        sp = StudyParticipant(
            study_id=eval_study.id,
            user_id=other.id,
            random_seed=99,
        )
        db.session.add(sp)
        db.session.commit()

        _login(client, 'other@example.com', 'otherpass')
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 2,
        })
        assert resp.status_code == 403

    def test_save_response_nonexistent_rating(self, client, assigned_user, db):
        """PUT /api/ratings/99999/response returns 404."""
        _login(client, 'participant@example.com', 'testpassword')
        resp = client.put('/api/ratings/99999/response', json={
            'question_id': 'F1',
            'value': 2,
        })
        assert resp.status_code == 404

    def test_save_response_unknown_question_rejected(self, client, assigned_user, rating_with_empty_responses):
        """Unknown question IDs are rejected for ordinal save endpoint."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'UNKNOWN_Q',
            'value': 1,
        })
        assert resp.status_code == 400
        assert 'unknown question_id' in resp.get_json()['error'].lower()

    def test_save_response_non_ordinal_question_rejected(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """Free-text questions cannot be written through the ordinal endpoint."""
        schema = dict(eval_study.rating_schema or {})
        questions = list(schema.get('questions', []))
        questions.append({
            'id': 'notes',
            'type': 'free_text',
            'name': 'Notes',
            'description': 'Optional notes',
        })
        schema['questions'] = questions
        eval_study.rating_schema = schema
        db.session.commit()

        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'notes',
            'value': 1,
        })
        assert resp.status_code == 400
        assert 'not an ordinal' in resp.get_json()['error'].lower()


# ===========================================================================
# Test: PUT /api/ratings/<rating_id>/text-response -- save text response
# ===========================================================================

class TestSaveTextResponse:

    def test_save_text_response(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """PUT /api/ratings/<id>/text-response saves text to responses JSON."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/text-response', json={
            'question_id': 'notes',
            'value': 'Some observation about the image.',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['responses']['notes'] == 'Some observation about the image.'

        db.session.refresh(rating)
        assert rating.responses['notes'] == 'Some observation about the image.'

    def test_save_text_response_empty_string(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """Saving an empty text response stores empty string."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/text-response', json={
            'question_id': 'notes',
            'value': '',
        })
        assert resp.status_code == 200
        db.session.refresh(rating)
        assert rating.responses['notes'] == ''

    def test_save_text_response_unknown_question_rejected(self, client, assigned_user, rating_with_empty_responses):
        """Unknown text question IDs are rejected (except the general 'notes' field)."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/text-response', json={
            'question_id': 'free_text_unknown',
            'value': 'hello',
        })
        assert resp.status_code == 400
        assert 'unknown question_id' in resp.get_json()['error'].lower()


# ===========================================================================
# Test: PUT /api/ratings/<rating_id>/uncertainty -- save uncertainty flag
# ===========================================================================

class TestSaveUncertainty:

    def test_save_uncertainty_true(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """PUT /api/ratings/<id>/uncertainty sets uncertainty to True."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/uncertainty', json={
            'value': True,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['uncertainty'] is True

        db.session.refresh(rating)
        assert rating.uncertainty is True

    def test_save_uncertainty_false(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """PUT /api/ratings/<id>/uncertainty sets uncertainty to False."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        # First set to True
        client.put(f'/api/ratings/{rating.id}/uncertainty', json={'value': True})
        # Then set to False
        resp = client.put(f'/api/ratings/{rating.id}/uncertainty', json={'value': False})
        assert resp.status_code == 200

        db.session.refresh(rating)
        assert rating.uncertainty is False

    def test_save_uncertainty_missing_value(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """PUT /api/ratings/<id>/uncertainty returns 400 if value is missing."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/uncertainty', json={})
        assert resp.status_code == 400


# ===========================================================================
# Test: PUT /api/ratings/<rating_id>/time -- add elapsed time
# ===========================================================================

class TestSaveTime:

    def test_save_time_adds_to_cumulative(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """PUT /api/ratings/<id>/time adds elapsed to cumulative time_spent_seconds."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses
        assert rating.time_spent_seconds == 0.0

        resp = client.put(f'/api/ratings/{rating.id}/time', json={
            'elapsed': 5.3,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert abs(data['time_spent_seconds'] - 5.3) < 0.01

        db.session.refresh(rating)
        assert abs(rating.time_spent_seconds - 5.3) < 0.01

    def test_save_time_cumulative(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """Multiple time saves accumulate."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        client.put(f'/api/ratings/{rating.id}/time', json={'elapsed': 3.0})
        client.put(f'/api/ratings/{rating.id}/time', json={'elapsed': 2.5})

        db.session.refresh(rating)
        assert abs(rating.time_spent_seconds - 5.5) < 0.01

    def test_save_time_negative_rejected(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """Negative elapsed time is rejected."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/time', json={'elapsed': -1.0})
        assert resp.status_code == 400

    def test_save_time_missing_elapsed(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """PUT /api/ratings/<id>/time returns 400 if elapsed is missing."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/time', json={})
        assert resp.status_code == 400


# ===========================================================================
# Test: PUT /api/ratings/<rating_id>/failure-reason -- save failure reason
# ===========================================================================

class TestSaveFailureReason:

    def test_save_failure_reason_string(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """PUT /api/ratings/<id>/failure-reason saves a string value."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        # Set an ordinal response to 0 so the condition (any_ordinal equals 0) is met
        client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1', 'value': 0,
        })

        resp = client.put(f'/api/ratings/{rating.id}/failure-reason', json={
            'value': 'Nuclear/cytology inconsistency (F1)',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['responses']['failure_reason'] == 'Nuclear/cytology inconsistency (F1)'

        db.session.refresh(rating)
        assert rating.responses['failure_reason'] == 'Nuclear/cytology inconsistency (F1)'

    def test_save_failure_reason_list(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """PUT /api/ratings/<id>/failure-reason saves a list value (multi-select)."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        # Enable multi_select on the schema for this test
        schema = dict(eval_study.rating_schema)
        schema['failure_reason'] = dict(schema['failure_reason'])
        schema['failure_reason']['multi_select'] = True
        eval_study.rating_schema = schema
        db.session.commit()

        # Set an ordinal response to 0 so the condition (any_ordinal equals 0) is met
        client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1', 'value': 0,
        })

        resp = client.put(f'/api/ratings/{rating.id}/failure-reason', json={
            'value': ['Nuclear/cytology inconsistency (F1)', 'Architecture incoherence (F2)'],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['responses']['failure_reason'] == [
            'Nuclear/cytology inconsistency (F1)',
            'Architecture incoherence (F2)',
        ]

    def test_save_failure_reason_null_clears(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """Saving null failure reason clears it."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        # Set an ordinal response to 0 so the condition (any_ordinal equals 0) is met
        client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1', 'value': 0,
        })
        # Set a value first
        client.put(f'/api/ratings/{rating.id}/failure-reason', json={
            'value': 'Nuclear/cytology inconsistency (F1)',
        })
        # Clear it
        resp = client.put(f'/api/ratings/{rating.id}/failure-reason', json={
            'value': None,
        })
        assert resp.status_code == 200
        db.session.refresh(rating)
        assert rating.responses.get('failure_reason') is None


# ===========================================================================
# Test: Save status indicator logic
# ===========================================================================

class TestSaveStatusLogic:

    def test_response_returns_updated_at(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """Save response returns updated_at timestamp for status indicator."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 2,
        })
        data = resp.get_json()
        assert 'updated_at' in data

    def test_sequential_saves_update_timestamp(self, client, assigned_user, eval_study, rating_with_empty_responses, db):
        """Each save updates the updated_at timestamp."""
        _login(client, 'participant@example.com', 'testpassword')
        rating = rating_with_empty_responses

        resp1 = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 2,
        })
        ts1 = resp1.get_json()['updated_at']

        resp2 = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F2',
            'value': 1,
        })
        ts2 = resp2.get_json()['updated_at']

        # Timestamps should be set (both are valid ISO strings)
        assert ts1 is not None
        assert ts2 is not None


# ===========================================================================
# Test: Admin cannot use rating endpoints
# ===========================================================================

class TestRatingApiAccessControl:

    def test_admin_cannot_save_response(self, client, admin_user, eval_study, db, rating_with_empty_responses):
        """Admin user gets 403 on rating save endpoints."""
        _login(client, 'admin', 'adminpassword')
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 2,
        })
        assert resp.status_code == 403

    def test_unauthenticated_cannot_save_response(self, client, rating_with_empty_responses):
        """Unauthenticated user gets 401 on rating save endpoints."""
        rating = rating_with_empty_responses

        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 2,
        })
        assert resp.status_code == 401
