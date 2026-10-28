"""Tests for the admin CSV export API endpoints.

Covers:
- GET /api/admin/studies/<id>/export -- CSV download
- GET /api/admin/studies/<id>/export/check -- completion status
- Test user exclusion from export
- Computed S_total and pass_fail columns
- Participant access control
"""

import csv
import io
from datetime import datetime, timezone

import pytest

from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import get_default_pass_fail_config, get_default_rating_schema
from tests.helpers import login_admin, login_participant


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def export_study(db):
    """Create an active study with schema and images for export tests."""
    study = Study(
        name='Export API Study',
        description='Study for export API tests',
        status='active',
        rating_schema=get_default_rating_schema(),
        pass_fail_config=get_default_pass_fail_config(),
    )
    db.session.add(study)
    db.session.flush()

    for i in range(1, 3):
        img = DatasetImage(
            study_id=study.id,
            image_path=f'export_ds/img_{i}.png',
            attributes={'synthetic': (i % 2 == 0), 'mpp_value': 0.5},
            sequence_number=i,
        )
        db.session.add(img)

    db.session.commit()
    return study


@pytest.fixture()
def regular_user(db):
    """Create a regular participant for export."""
    user = User(
        first_name='Export',
        last_name='User',
        email='export_user@example.com',
        institution='Export Hospital',
        role='participant',
        is_test_user=False,
    )
    user.set_password('exportpass')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def test_user_flagged(db):
    """Create a test user (is_test_user=True)."""
    user = User(
        first_name='TestBot',
        last_name='Tester',
        email='testbot@example.com',
        institution='Test Lab',
        role='participant',
        is_test_user=True,
    )
    user.set_password('testpass')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def participant_user(db):
    """Create a participant for access control tests."""
    user = User(
        first_name='Blocked',
        last_name='Participant',
        email='blocked@example.com',
        institution='No Access',
        role='participant',
        is_test_user=False,
    )
    user.set_password('blockedpass')
    db.session.add(user)
    db.session.commit()
    return user


def _assign(db_session, study, user, submitted=False):
    sp = StudyParticipant(
        study_id=study.id,
        user_id=user.id,
        submitted=submitted,
        submitted_at=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc) if submitted else None,
    )
    db_session.session.add(sp)
    db_session.session.commit()
    return sp


def _add_rating(db_session, user, image, study, responses=None):
    rating = Rating(
        user_id=user.id,
        dataset_image_id=image.id,
        study_id=study.id,
        responses=responses or {'F1': 2, 'F2': 2, 'F3': 1, 'F4': 2, 'F5': 2, 'F6': 1},
        time_spent_seconds=10.0,
        updated_at=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
    )
    db_session.session.add(rating)
    db_session.session.commit()
    return rating


def _parse_csv(csv_string):
    reader = csv.reader(io.StringIO(csv_string))
    rows = list(reader)
    return rows[0], rows[1:]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExportCSV:

    def test_export_csv_returns_csv(self, client, admin_user, export_study, regular_user, db):
        """GET /api/admin/studies/<id>/export returns CSV with correct Content-Type."""
        _assign(db, export_study, regular_user, submitted=True)
        images = DatasetImage.query.filter_by(study_id=export_study.id).all()
        _add_rating(db, regular_user, images[0], export_study)

        login_admin(client)

        resp = client.get(f'/api/admin/studies/{export_study.id}/export')
        assert resp.status_code == 200
        assert 'text/csv' in resp.content_type

    def test_export_csv_correct_headers(self, client, admin_user, export_study, regular_user, db):
        """CSV has expected column headers."""
        _assign(db, export_study, regular_user, submitted=True)
        images = DatasetImage.query.filter_by(study_id=export_study.id).all()
        _add_rating(db, regular_user, images[0], export_study)

        login_admin(client)
        resp = client.get(f'/api/admin/studies/{export_study.id}/export')

        header, _ = _parse_csv(resp.data.decode('utf-8'))
        assert 'user_id' in header
        assert 'user_name' in header
        assert 'institution' in header
        assert 'sequence_number' in header
        assert 'image_path' in header
        assert 'F1' in header
        assert 'F6' in header
        assert 'S_total' in header
        assert 'pass_fail' in header
        assert 'submitted' in header

    def test_export_excludes_test_users(
        self, client, admin_user, export_study, regular_user, test_user_flagged, db
    ):
        """Test user ratings are NOT included in the CSV export."""
        _assign(db, export_study, regular_user, submitted=True)
        _assign(db, export_study, test_user_flagged, submitted=True)

        images = DatasetImage.query.filter_by(study_id=export_study.id).all()
        _add_rating(db, regular_user, images[0], export_study)
        _add_rating(db, test_user_flagged, images[0], export_study)

        login_admin(client)
        resp = client.get(f'/api/admin/studies/{export_study.id}/export')

        header, rows = _parse_csv(resp.data.decode('utf-8'))
        assert len(rows) == 1
        user_name_idx = header.index('user_name')
        assert rows[0][user_name_idx] == 'Export User'

    def test_export_includes_computed_scores(
        self, client, admin_user, export_study, regular_user, db
    ):
        """S_total and pass_fail columns are present and correctly computed."""
        _assign(db, export_study, regular_user, submitted=True)
        images = DatasetImage.query.filter_by(study_id=export_study.id).all()
        # F1=2, F2=2, F3=1, F4=2, F5=2, F6=1 => S_total = 10 => pass
        _add_rating(db, regular_user, images[0], export_study)

        login_admin(client)
        resp = client.get(f'/api/admin/studies/{export_study.id}/export')

        header, rows = _parse_csv(resp.data.decode('utf-8'))
        s_total_idx = header.index('S_total')
        pass_fail_idx = header.index('pass_fail')
        assert rows[0][s_total_idx] == '10'
        assert rows[0][pass_fail_idx] == '1'  # pass = True = 1


class TestExportCheck:

    def test_export_check_returns_status(
        self, client, admin_user, export_study, regular_user, db
    ):
        """GET /api/admin/studies/<id>/export/check returns status fields."""
        _assign(db, export_study, regular_user, submitted=True)

        login_admin(client)
        resp = client.get(f'/api/admin/studies/{export_study.id}/export/check')
        assert resp.status_code == 200

        data = resp.get_json()
        assert 'complete' in data
        assert 'warning' in data
        assert 'total_users' in data
        assert 'submitted_users' in data
        assert data['complete'] is True
        assert data['total_users'] == 1
        assert data['submitted_users'] == 1

    def test_export_check_incomplete(
        self, client, admin_user, export_study, regular_user, db
    ):
        """Export check shows incomplete when not all users submitted."""
        _assign(db, export_study, regular_user, submitted=False)

        login_admin(client)
        resp = client.get(f'/api/admin/studies/{export_study.id}/export/check')
        data = resp.get_json()

        assert data['complete'] is False
        assert data['warning'] is not None
        assert data['submitted_users'] == 0


class TestExportAccessControl:

    def test_participant_cannot_export(
        self, client, admin_user, participant_user, export_study, db
    ):
        """Participant gets 403 on export endpoint."""
        login_participant(client, 'blocked@example.com', 'blockedpass')

        resp = client.get(f'/api/admin/studies/{export_study.id}/export')
        assert resp.status_code == 403

    def test_participant_cannot_check_export(
        self, client, admin_user, participant_user, export_study, db
    ):
        """Participant gets 403 on export check endpoint."""
        login_participant(client, 'blocked@example.com', 'blockedpass')

        resp = client.get(f'/api/admin/studies/{export_study.id}/export/check')
        assert resp.status_code == 403

    def test_unauthenticated_cannot_export(self, client, export_study, db):
        """Unauthenticated user gets 401 on export endpoint."""
        resp = client.get(f'/api/admin/studies/{export_study.id}/export')
        assert resp.status_code == 401
