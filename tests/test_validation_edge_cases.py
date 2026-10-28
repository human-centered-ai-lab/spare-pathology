"""Tests for input validation edge cases on ratings endpoints and CSV sanitization.

Covers:
- Ordinal range validation (above max, below min, boundary, non-integer)
- Text response length limits and type validation
- CSV formula injection sanitization (service function + export integration)
"""

import csv
import io
from datetime import datetime, timezone

import pytest

from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import get_default_pass_fail_config, get_default_rating_schema
from tests.helpers import login_participant


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def eval_study(db):
    """Create an active study with schema (F1-F6, min=0, max=2) and images."""
    study = Study(
        name='Validation Test Study',
        description='Study for validation tests',
        status='active',
        rating_schema=get_default_rating_schema(),
        uncertainty_enabled=True,
    )
    db.session.add(study)
    db.session.flush()

    for i in range(1, 3):
        img = DatasetImage(
            study_id=study.id,
            image_path=f'val_ds/img_{i}.png',
            attributes={'synthetic': False, 'mpp_value': 0.5},
            sequence_number=i,
        )
        db.session.add(img)

    db.session.commit()
    return study


@pytest.fixture()
def participant(db, eval_study):
    """Create a participant assigned to the study."""
    user = User(
        first_name='Val',
        last_name='Tester',
        email='valtester@example.com',
        institution='Test Hospital',
        role='participant',
        is_test_user=False,
    )
    user.set_password('valpass')
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


@pytest.fixture()
def rating(db, participant, eval_study):
    """Create a rating with empty responses for the first image."""
    images = DatasetImage.query.filter_by(study_id=eval_study.id).order_by(DatasetImage.id).all()
    r = Rating(
        user_id=participant.id,
        dataset_image_id=images[0].id,
        study_id=eval_study.id,
        responses={},
    )
    db.session.add(r)
    db.session.commit()
    return r


# ---------------------------------------------------------------------------
# Ordinal Range Validation Tests
# ---------------------------------------------------------------------------

class TestOrdinalRangeValidation:
    """Tests for ordinal value range enforcement on PUT /api/ratings/<id>/response."""

    def test_ordinal_value_above_max(self, client, participant, rating):
        """Value above max (3 > 2) returns 400."""
        login_participant(client, 'valtester@example.com', 'valpass')

        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 3,
        })
        assert resp.status_code == 400
        assert 'out of range' in resp.get_json()['error'].lower()

    def test_ordinal_value_below_min(self, client, participant, rating):
        """Value below min (-1 < 0) returns 400."""
        login_participant(client, 'valtester@example.com', 'valpass')

        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': -1,
        })
        assert resp.status_code == 400
        assert 'out of range' in resp.get_json()['error'].lower()

    def test_ordinal_boundary_min_accepted(self, client, participant, rating):
        """Value at min boundary (0) returns 200."""
        login_participant(client, 'valtester@example.com', 'valpass')

        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 0,
        })
        assert resp.status_code == 200
        assert resp.get_json()['responses']['F1'] == 0

    def test_ordinal_boundary_max_accepted(self, client, participant, rating):
        """Value at max boundary (2) returns 200."""
        login_participant(client, 'valtester@example.com', 'valpass')

        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 2,
        })
        assert resp.status_code == 200
        assert resp.get_json()['responses']['F1'] == 2

    def test_ordinal_non_integer(self, client, participant, rating):
        """Non-integer value ("abc") returns 400."""
        login_participant(client, 'valtester@example.com', 'valpass')

        resp = client.put(f'/api/ratings/{rating.id}/response', json={
            'question_id': 'F1',
            'value': 'abc',
        })
        assert resp.status_code == 400
        assert 'integer' in resp.get_json()['error'].lower()


# ---------------------------------------------------------------------------
# Text Response Validation Tests
# ---------------------------------------------------------------------------

class TestTextResponseValidation:
    """Tests for text response limits on PUT /api/ratings/<id>/text-response."""

    def test_text_over_limit(self, client, participant, rating):
        """Text over 10000 chars returns 400."""
        login_participant(client, 'valtester@example.com', 'valpass')

        resp = client.put(f'/api/ratings/{rating.id}/text-response', json={
            'question_id': 'notes',
            'value': 'x' * 10001,
        })
        assert resp.status_code == 400

    def test_text_at_limit(self, client, participant, rating):
        """Text at exactly 10000 chars returns 200."""
        login_participant(client, 'valtester@example.com', 'valpass')

        resp = client.put(f'/api/ratings/{rating.id}/text-response', json={
            'question_id': 'notes',
            'value': 'x' * 10000,
        })
        assert resp.status_code == 200

    def test_text_non_string(self, client, participant, rating):
        """Non-string value (integer 123) returns 400."""
        login_participant(client, 'valtester@example.com', 'valpass')

        resp = client.put(f'/api/ratings/{rating.id}/text-response', json={
            'question_id': 'notes',
            'value': 123,
        })
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# CSV Sanitization Tests (service function)
# ---------------------------------------------------------------------------

class TestCSVSanitization:
    """Tests for _sanitize_csv_value preventing formula injection."""

    def _sanitize(self, value):
        from app.services.export_service import _sanitize_csv_value
        return _sanitize_csv_value(value)

    def test_sanitize_csv_equals(self):
        """'=SUM(A1)' is prefixed with an apostrophe."""
        assert self._sanitize('=SUM(A1)') == "'=SUM(A1)"

    def test_sanitize_csv_plus(self):
        """'+cmd' is prefixed with an apostrophe."""
        assert self._sanitize('+cmd') == "'+cmd"

    def test_sanitize_csv_minus(self):
        """'-cmd' is prefixed with an apostrophe."""
        assert self._sanitize('-cmd') == "'-cmd"

    def test_sanitize_csv_at(self):
        """'@SUM' is prefixed with an apostrophe."""
        assert self._sanitize('@SUM') == "'@SUM"

    def test_sanitize_csv_normal(self):
        """Normal text is unchanged."""
        assert self._sanitize('normal text') == 'normal text'

    def test_sanitize_csv_empty(self):
        """Empty string is unchanged."""
        assert self._sanitize('') == ''

    def test_sanitize_csv_number(self):
        """Integer 42 is unchanged (not a string)."""
        assert self._sanitize(42) == 42


# ---------------------------------------------------------------------------
# CSV Sanitization via Export Integration Test
# ---------------------------------------------------------------------------

class TestExportSanitization:
    """Test that CSV export sanitizes dangerous values end-to-end."""

    def test_export_sanitizes_dangerous_values(self, app, db):
        """Formula-like names are marked as text in exported CSV."""
        study = Study(
            name='Sanitize Test',
            status='active',
            rating_schema=get_default_rating_schema(),
            pass_fail_config=get_default_pass_fail_config(),
        )
        db.session.add(study)
        db.session.flush()

        img = DatasetImage(
            study_id=study.id,
            image_path='sanitize_ds/img.png',
            attributes={'synthetic': False},
            sequence_number=1,
        )
        db.session.add(img)
        db.session.flush()

        # User whose name starts with '='
        dangerous_user = User(
            first_name='=FORMULA',
            last_name='Injector',
            email='dangerous@example.com',
            institution='Evil Corp',
            role='participant',
            is_test_user=False,
        )
        dangerous_user.set_password('pass')
        db.session.add(dangerous_user)
        db.session.flush()

        sp = StudyParticipant(
            study_id=study.id,
            user_id=dangerous_user.id,
            submitted=True,
            submitted_at=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        )
        db.session.add(sp)

        rating = Rating(
            user_id=dangerous_user.id,
            dataset_image_id=img.id,
            study_id=study.id,
            responses={'F1': 2, 'F2': 2, 'F3': 1, 'F4': 2, 'F5': 2, 'F6': 1},
            time_spent_seconds=10.0,
            updated_at=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        )
        db.session.add(rating)
        db.session.commit()

        from app.services.export_service import generate_csv
        csv_string, _, _ = generate_csv(study.id)

        reader = csv.reader(io.StringIO(csv_string))
        rows = list(reader)
        header = rows[0]
        data_row = rows[1]

        user_name_idx = header.index('user_name')
        # The name should be sanitized: apostrophe-prefixed
        assert data_row[user_name_idx] == "'=FORMULA Injector"
