"""Tests for CSV export service functions.

Tests cover:
- Export service: generate_csv, get_export_status
- Test user exclusion, column structure, computed scores, completion warnings
"""

import csv
import io
from datetime import datetime, timezone

import pytest

from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import get_default_pass_fail_config, get_default_rating_schema


@pytest.fixture()
def full_study(db):
    """Create a study with the default rating schema."""
    study = Study(
        name="Export Test Study",
        description="Study for testing CSV export",
        status="active",
        rating_schema=get_default_rating_schema(),
        pass_fail_config=get_default_pass_fail_config(),
    )
    db.session.add(study)
    db.session.commit()
    return study


@pytest.fixture()
def regular_user(db):
    """Create a regular (non-test) participant user."""
    user = User(
        first_name="Alice",
        last_name="Smith",
        email="alice@example.com",
        institution="General Hospital",
        role="participant",
        is_test_user=False,
    )
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def regular_user_2(db):
    """Create a second regular participant."""
    user = User(
        first_name="Bob",
        last_name="Test",  # last name is "Test" but NOT a test user
        email="bob@example.com",
        institution="City Clinic",
        role="participant",
        is_test_user=False,
    )
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def test_user_flagged(db):
    """Create a user flagged as test user (is_test_user=True)."""
    user = User(
        first_name="Tester",
        last_name="Bot",
        email="tester@example.com",
        institution="Test Lab",
        role="participant",
        is_test_user=True,
    )
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def images(db, full_study):
    """Create two dataset images for the study."""
    img1 = DatasetImage(
        study_id=full_study.id,
        image_path="images/img_001.png",
        attributes={
            "synthetic": False,
            "tissue_type": "Tumor-dominant",
            "mpp_value": 0.25,
        },
        sequence_number=1,
    )
    img2 = DatasetImage(
        study_id=full_study.id,
        image_path="images/img_002.png",
        attributes={
            "synthetic": True,
            "tissue_type": "Stroma-dominant",
            "mpp_value": 0.5,
            "model_name": "ModelA",
        },
        sequence_number=2,
    )
    db.session.add_all([img1, img2])
    db.session.commit()
    return [img1, img2]


def _make_responses():
    """Return sample responses for the default schema (F1-F6)."""
    return {"F1": 2, "F2": 2, "F3": 1, "F4": 2, "F5": 2, "F6": 1}


def _add_rating(db, user, image, study, responses=None, uncertainty=None, time_spent=10.0):
    """Helper to add a rating."""
    rating = Rating(
        user_id=user.id,
        dataset_image_id=image.id,
        study_id=study.id,
        responses=responses or _make_responses(),
        uncertainty=uncertainty,
        time_spent_seconds=time_spent,
        updated_at=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
    )
    db.session.add(rating)
    db.session.commit()
    return rating


def _assign_user(db, study, user, submitted=False):
    """Helper to assign a user to a study."""
    sp = StudyParticipant(
        study_id=study.id,
        user_id=user.id,
        submitted=submitted,
        submitted_at=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc) if submitted else None,
    )
    db.session.add(sp)
    db.session.commit()
    return sp


def _parse_csv(csv_string):
    """Parse a CSV string and return (header, rows)."""
    reader = csv.reader(io.StringIO(csv_string))
    rows = list(reader)
    return rows[0], rows[1:]


# --------------------------------------------------
# Export Service Tests
# --------------------------------------------------

class TestGenerateCSV:
    """Tests for export_service.generate_csv()."""

    def test_basic_csv_generation(self, app, db, full_study, regular_user, images):
        """CSV is generated with correct columns and one row per rating."""
        _assign_user(db, full_study, regular_user, submitted=True)
        _add_rating(db, regular_user, images[0], full_study)
        _add_rating(db, regular_user, images[1], full_study)

        from app.services.export_service import generate_csv
        csv_string, is_complete, warning = generate_csv(full_study.id)

        header, rows = _parse_csv(csv_string)
        assert len(rows) == 2
        assert header[0] == "user_id"
        assert header[1] == "user_name"
        assert "S_total" in header
        assert "pass_fail" in header

    def test_csv_column_order(self, app, db, full_study, regular_user, images):
        """CSV columns match the spec ordering."""
        _assign_user(db, full_study, regular_user, submitted=True)
        _add_rating(db, regular_user, images[0], full_study)

        from app.services.export_service import generate_csv
        csv_string, _, _ = generate_csv(full_study.id)

        header, _ = _parse_csv(csv_string)
        # Check fixed columns
        assert header[0] == "user_id"
        assert header[1] == "user_name"
        assert header[2] == "institution"
        assert header[3] == "sequence_number"
        assert header[4] == "image_path"
        # Dynamic attribute columns (sorted alphabetically)
        attr_start = 5
        attr_keys = sorted(["model_name", "mpp_value", "synthetic", "tissue_type"])
        for i, key in enumerate(attr_keys):
            assert header[attr_start + i] == key
        # Question columns F1-F6
        q_start = attr_start + len(attr_keys)
        assert header[q_start] == "F1"
        assert header[q_start + 5] == "F6"
        # Trailing columns
        assert header[q_start + 6] == "failure_reason"
        assert header[q_start + 7] == "uncertainty"
        assert header[q_start + 8] == "time_spent_seconds"
        assert header[q_start + 9] == "S_total"
        assert header[q_start + 10] == "pass_fail"
        assert header[q_start + 11] == "submitted"
        assert header[q_start + 12] == "updated_at"

    def test_excludes_test_users(self, app, db, full_study, regular_user, test_user_flagged, images):
        """Ratings by test users (is_test_user=True) are excluded."""
        _assign_user(db, full_study, regular_user, submitted=True)
        _assign_user(db, full_study, test_user_flagged, submitted=True)
        _add_rating(db, regular_user, images[0], full_study)
        _add_rating(db, test_user_flagged, images[0], full_study)

        from app.services.export_service import generate_csv
        csv_string, _, _ = generate_csv(full_study.id)

        header, rows = _parse_csv(csv_string)
        # Only the regular user's rating should be present
        assert len(rows) == 1
        assert rows[0][header.index("user_name")] == "Alice Smith"

    def test_includes_user_with_test_in_name(self, app, db, full_study, regular_user_2, images):
        """A user with 'Test' in their name but is_test_user=False IS included."""
        _assign_user(db, full_study, regular_user_2, submitted=True)
        _add_rating(db, regular_user_2, images[0], full_study)

        from app.services.export_service import generate_csv
        csv_string, _, _ = generate_csv(full_study.id)

        header, rows = _parse_csv(csv_string)
        assert len(rows) == 1
        assert rows[0][header.index("user_name")] == "Bob Test"

    def test_s_total_and_pass_fail_computed(self, app, db, full_study, regular_user, images):
        """S_total and pass_fail are correctly computed from responses."""
        _assign_user(db, full_study, regular_user, submitted=True)
        # F1=2, F2=2, F3=1, F4=2, F5=2, F6=1 => S_total = 10
        # pass_fail conditions: S_total >= 9 (10 >= 9 = True) AND F5 >= 1 (2 >= 1 = True) => True
        _add_rating(db, regular_user, images[0], full_study)

        from app.services.export_service import generate_csv
        csv_string, _, _ = generate_csv(full_study.id)

        header, rows = _parse_csv(csv_string)
        s_total_idx = header.index("S_total")
        pass_fail_idx = header.index("pass_fail")
        assert rows[0][s_total_idx] == "10"
        assert rows[0][pass_fail_idx] == "1"

    def test_s_total_fail_case(self, app, db, full_study, regular_user, images):
        """pass_fail is False when score is below threshold."""
        _assign_user(db, full_study, regular_user, submitted=True)
        # All zeros => S_total = 0, F5 = 0 => fails both conditions
        responses = {"F1": 0, "F2": 0, "F3": 0, "F4": 0, "F5": 0, "F6": 0}
        _add_rating(db, regular_user, images[0], full_study, responses=responses)

        from app.services.export_service import generate_csv
        csv_string, _, _ = generate_csv(full_study.id)

        header, rows = _parse_csv(csv_string)
        assert rows[0][header.index("S_total")] == "0"
        assert rows[0][header.index("pass_fail")] == "0"

    def test_incomplete_warning(self, app, db, full_study, regular_user, regular_user_2, images):
        """Warning is returned when not all users have submitted."""
        _assign_user(db, full_study, regular_user, submitted=True)
        _assign_user(db, full_study, regular_user_2, submitted=False)
        _add_rating(db, regular_user, images[0], full_study)

        from app.services.export_service import generate_csv
        csv_string, is_complete, warning = generate_csv(full_study.id)

        assert is_complete is False
        assert warning is not None
        assert "1 of 2" in warning

    def test_complete_no_warning(self, app, db, full_study, regular_user, images):
        """No warning when all non-test users have submitted."""
        _assign_user(db, full_study, regular_user, submitted=True)
        _add_rating(db, regular_user, images[0], full_study)

        from app.services.export_service import generate_csv
        csv_string, is_complete, warning = generate_csv(full_study.id)

        assert is_complete is True
        assert warning is None

    def test_empty_study_no_ratings(self, app, db, full_study):
        """CSV with only headers when no ratings exist."""
        from app.services.export_service import generate_csv
        csv_string, is_complete, warning = generate_csv(full_study.id)

        header, rows = _parse_csv(csv_string)
        assert len(rows) == 0
        assert "user_id" in header

    def test_question_responses_flattened(self, app, db, full_study, regular_user, images):
        """Each question ID becomes its own column with the response value."""
        _assign_user(db, full_study, regular_user, submitted=True)
        responses = {"F1": 2, "F2": 1, "F3": 0, "F4": 2, "F5": 1, "F6": 2}
        _add_rating(db, regular_user, images[0], full_study, responses=responses)

        from app.services.export_service import generate_csv
        csv_string, _, _ = generate_csv(full_study.id)

        header, rows = _parse_csv(csv_string)
        assert rows[0][header.index("F1")] == "2"
        assert rows[0][header.index("F2")] == "1"
        assert rows[0][header.index("F3")] == "0"
        assert rows[0][header.index("F4")] == "2"
        assert rows[0][header.index("F5")] == "1"
        assert rows[0][header.index("F6")] == "2"


class TestGetExportStatus:
    """Tests for export_service.get_export_status()."""

    def test_status_complete(self, app, db, full_study, regular_user):
        """Status shows complete when all users submitted."""
        _assign_user(db, full_study, regular_user, submitted=True)

        from app.services.export_service import get_export_status
        status = get_export_status(full_study.id)

        assert status["complete"] is True
        assert status["warning"] is None
        assert status["total_users"] == 1
        assert status["submitted_users"] == 1

    def test_status_incomplete(self, app, db, full_study, regular_user, regular_user_2):
        """Status shows incomplete with warning when not all submitted."""
        _assign_user(db, full_study, regular_user, submitted=True)
        _assign_user(db, full_study, regular_user_2, submitted=False)

        from app.services.export_service import get_export_status
        status = get_export_status(full_study.id)

        assert status["complete"] is False
        assert status["warning"] is not None
        assert status["total_users"] == 2
        assert status["submitted_users"] == 1
