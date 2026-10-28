"""Tests for admin participant management API: list, assign, unassign, unsubmit."""

import pytest
from datetime import datetime, timezone

from app.models import DatasetImage, StudyParticipant, Rating, User
from tests.helpers import create_study_with_images, login_admin, login_participant


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def participant_study(db):
    """Create an active study with images for participant tests."""
    study = create_study_with_images(db, n=4)
    study.status = 'active'
    db.session.commit()
    return study


@pytest.fixture()
def unassigned_participant(db):
    """Create a participant not assigned to any study."""
    user = User(
        first_name='Unassigned',
        last_name='User',
        email='unassigned@test.com',
        institution='Test Hospital',
        role='participant',
        is_test_user=False,
    )
    user.set_password('testpass')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def assigned_participant(db, participant_study, unassigned_participant):
    """Assign the participant to the study (no ratings)."""
    sp = StudyParticipant(
        study_id=participant_study.id,
        user_id=unassigned_participant.id,
        random_seed=42,
    )
    db.session.add(sp)
    db.session.commit()
    return unassigned_participant


@pytest.fixture()
def rated_participant(db, participant_study):
    """Create a participant with ratings in the study."""
    user = User(
        first_name='Rated',
        last_name='Participant',
        email='rated@test.com',
        institution='Test Hospital',
        role='participant',
        is_test_user=False,
    )
    user.set_password('testpass')
    db.session.add(user)
    db.session.flush()

    sp = StudyParticipant(
        study_id=participant_study.id,
        user_id=user.id,
        random_seed=99,
    )
    db.session.add(sp)

    img = DatasetImage.query.filter_by(study_id=participant_study.id).first()
    rating = Rating(
        user_id=user.id,
        dataset_image_id=img.id,
        study_id=participant_study.id,
        responses={'F1': 2},
    )
    db.session.add(rating)
    db.session.commit()
    return user


@pytest.fixture()
def submitted_participant(db, participant_study):
    """Create a participant who has submitted their evaluation."""
    user = User(
        first_name='Submitted',
        last_name='Participant',
        email='submitted@test.com',
        institution='Test Hospital',
        role='participant',
        is_test_user=False,
    )
    user.set_password('testpass')
    db.session.add(user)
    db.session.flush()

    sp = StudyParticipant(
        study_id=participant_study.id,
        user_id=user.id,
        random_seed=55,
        submitted=True,
        submitted_at=datetime.now(timezone.utc),
    )
    db.session.add(sp)
    db.session.commit()
    return user


# ===========================================================================
# Test: GET /api/admin/studies/:id/participants
# ===========================================================================

class TestListParticipants:

    def test_list_participants_with_status(self, client, admin_user, participant_study, assigned_participant):
        """List shows assigned participants with computed status."""
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{participant_study.id}/participants')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'assigned' in data
        assert 'available' in data
        assigned_emails = [p['email'] for p in data['assigned']]
        assert 'unassigned@test.com' in assigned_emails

    def test_list_shows_available_users(self, client, admin_user, participant_study, unassigned_participant):
        """Available list includes unassigned non-test participants."""
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{participant_study.id}/participants')
        assert resp.status_code == 200
        data = resp.get_json()
        available_emails = [u['email'] for u in data['available']]
        assert 'unassigned@test.com' in available_emails

    def test_list_filters_non_participant_assignments(self, client, admin_user, participant_study, db):
        """Assigned list should not include users whose role is not participant."""
        bad_admin = User(
            first_name='Bad',
            last_name='Assignment',
            email='bad-assigned-admin@test.com',
            role='admin',
            is_test_user=False,
        )
        bad_admin.set_password('adminpass')
        db.session.add(bad_admin)
        db.session.flush()
        db.session.add(
            StudyParticipant(
                study_id=participant_study.id,
                user_id=bad_admin.id,
                random_seed=7,
            )
        )
        db.session.commit()

        login_admin(client)
        resp = client.get(f'/api/admin/studies/{participant_study.id}/participants')
        assert resp.status_code == 200
        data = resp.get_json()
        assigned_emails = [p['email'] for p in data['assigned']]
        assert 'bad-assigned-admin@test.com' not in assigned_emails


# ===========================================================================
# Test: POST /api/admin/studies/:id/participants/assign
# ===========================================================================

class TestAssignParticipant:

    def test_assign_user_to_study(self, client, admin_user, participant_study, unassigned_participant, db):
        """Assign a participant to a study."""
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{participant_study.id}/participants/assign', json={
            'user_id': unassigned_participant.id,
        })
        assert resp.status_code == 201

        sp = StudyParticipant.query.filter_by(
            study_id=participant_study.id,
            user_id=unassigned_participant.id,
        ).first()
        assert sp is not None

    def test_assign_already_assigned_user(self, client, admin_user, participant_study, assigned_participant):
        """Re-assigning an already assigned user returns 409."""
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{participant_study.id}/participants/assign', json={
            'user_id': assigned_participant.id,
        })
        assert resp.status_code == 409

    def test_assign_admin_user_rejected(self, client, admin_user, participant_study, db):
        """Only participant-role users can be assigned to studies."""
        other_admin = User(
            first_name='Other',
            last_name='Admin',
            email='other-admin@test.com',
            role='admin',
            is_test_user=False,
        )
        other_admin.set_password('adminpass')
        db.session.add(other_admin)
        db.session.commit()

        login_admin(client)
        resp = client.post(f'/api/admin/studies/{participant_study.id}/participants/assign', json={
            'user_id': other_admin.id,
        })
        assert resp.status_code == 400
        assert 'participant' in resp.get_json()['error'].lower()


# ===========================================================================
# Test: POST /api/admin/studies/:id/participants/unassign
# ===========================================================================

class TestUnassignParticipant:

    def test_unassign_user_no_ratings(self, client, admin_user, participant_study, assigned_participant, db):
        """Unassign a participant with no ratings succeeds."""
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{participant_study.id}/participants/unassign', json={
            'user_id': assigned_participant.id,
        })
        assert resp.status_code == 200

        sp = StudyParticipant.query.filter_by(
            study_id=participant_study.id,
            user_id=assigned_participant.id,
        ).first()
        assert sp is None

    def test_unassign_user_with_ratings_no_confirm(self, client, admin_user, participant_study, rated_participant):
        """Unassign user with ratings requires confirmation -> 409."""
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{participant_study.id}/participants/unassign', json={
            'user_id': rated_participant.id,
        })
        assert resp.status_code == 409
        data = resp.get_json()
        assert data['confirm_required'] is True

    def test_unassign_user_with_ratings_confirmed(self, client, admin_user, participant_study, rated_participant, db):
        """Unassign user with ratings + confirm deletes ratings and assignment."""
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{participant_study.id}/participants/unassign', json={
            'user_id': rated_participant.id,
            'confirm': True,
        })
        assert resp.status_code == 200

        assert Rating.query.filter_by(
            user_id=rated_participant.id, study_id=participant_study.id,
        ).count() == 0


# ===========================================================================
# Test: POST /api/admin/studies/:id/participants/:user_id/unsubmit
# ===========================================================================

class TestUnsubmitParticipant:

    def test_unsubmit_participant(self, client, admin_user, participant_study, submitted_participant, db):
        """Un-submit a participant reverts their submitted status."""
        login_admin(client)
        resp = client.post(
            f'/api/admin/studies/{participant_study.id}/participants/{submitted_participant.id}/unsubmit'
        )
        assert resp.status_code == 200

        sp = StudyParticipant.query.filter_by(
            study_id=participant_study.id,
            user_id=submitted_participant.id,
        ).first()
        assert sp.submitted is False
        assert sp.submitted_at is None

    def test_unsubmit_invalidates_stats_cache(self, client, admin_user, participant_study, submitted_participant, monkeypatch):
        """Unsubmit should invalidate cached statistics for the study."""
        invalidated_ids = []

        def mock_invalidate(study_id=None):
            invalidated_ids.append(study_id)

        monkeypatch.setattr('app.api.admin_participants.invalidate_stats_cache', mock_invalidate)

        login_admin(client)
        resp = client.post(
            f'/api/admin/studies/{participant_study.id}/participants/{submitted_participant.id}/unsubmit'
        )
        assert resp.status_code == 200
        assert participant_study.id in invalidated_ids


# ===========================================================================
# Test: Access Control
# ===========================================================================

class TestParticipantAccessControl:

    def test_participant_cannot_manage(self, client, test_user, participant_study, unassigned_participant):
        """Participant gets 403 on participant management endpoints."""
        login_participant(client)
        resp = client.post(f'/api/admin/studies/{participant_study.id}/participants/assign', json={
            'user_id': unassigned_participant.id,
        })
        assert resp.status_code == 403
