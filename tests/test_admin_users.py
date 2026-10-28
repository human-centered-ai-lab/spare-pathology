"""Tests for admin user management API: list, create, get, update, delete, reset password."""

import pytest

from app.models import Study, StudyParticipant, Rating, DatasetImage, User
from app.services.schema_service import get_default_rating_schema
from tests.helpers import login_admin, login_participant


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def user_study(db):
    """Create a study for user assignment tests."""
    study = Study(
        name='User Test Study',
        status='active',
        rating_schema=get_default_rating_schema(),
    )
    db.session.add(study)
    db.session.commit()
    return study


@pytest.fixture()
def participant_with_ratings(db, user_study):
    """Create a participant who has ratings in a study."""
    user = User(
        first_name='Rated',
        last_name='Participant',
        email='rated@example.com',
        institution='Test Hospital',
        role='participant',
    )
    user.set_password('testpass')
    db.session.add(user)
    db.session.flush()

    sp = StudyParticipant(study_id=user_study.id, user_id=user.id, random_seed=42)
    db.session.add(sp)

    img = DatasetImage(
        study_id=user_study.id,
        image_path='test/img1.png',
        attributes={'synthetic': False, 'mpp_value': 0.5},
        sequence_number=1,
    )
    db.session.add(img)
    db.session.flush()

    rating = Rating(
        user_id=user.id,
        dataset_image_id=img.id,
        study_id=user_study.id,
        responses={'F1': 2},
    )
    db.session.add(rating)
    db.session.commit()
    return user


# ===========================================================================
# Test: GET /api/admin/users
# ===========================================================================

class TestListUsers:

    def test_list_users_admin(self, client, admin_user, test_user):
        """Admin can list all users."""
        login_admin(client)
        resp = client.get('/api/admin/users')
        assert resp.status_code == 200
        data = resp.get_json()
        emails = [u['email'] for u in data]
        assert 'admin' in emails
        assert 'participant@example.com' in emails

    def test_list_users_participant_forbidden(self, client, test_user):
        """Participant gets 403 on admin user list."""
        login_participant(client)
        resp = client.get('/api/admin/users')
        assert resp.status_code == 403

    def test_list_users_unauthenticated(self, client, db):
        """Unauthenticated request gets 401."""
        resp = client.get('/api/admin/users')
        assert resp.status_code == 401


# ===========================================================================
# Test: POST /api/admin/users
# ===========================================================================

class TestCreateUser:

    def test_create_user_minimal(self, client, admin_user, db):
        """Create a user with minimal required fields."""
        login_admin(client)
        resp = client.post('/api/admin/users', json={
            'first_name': 'New',
            'last_name': 'User',
            'email': 'newuser@example.com',
            'institution': 'Hospital',
            'role': 'participant',
            'password': 'securepass',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['email'] == 'newuser@example.com'
        assert data['role'] == 'participant'

    def test_create_user_with_study_assignments(self, client, admin_user, user_study, db):
        """Create a user assigned to a study."""
        login_admin(client)
        resp = client.post('/api/admin/users', json={
            'first_name': 'Assigned',
            'last_name': 'User',
            'email': 'assigned@example.com',
            'institution': 'Hospital',
            'role': 'participant',
            'password': 'securepass',
            'study_ids': [user_study.id],
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert len(data['studies']) == 1
        assert data['studies'][0]['study_id'] == user_study.id

    def test_create_admin_user_with_study_assignments_rejected(self, client, admin_user, user_study):
        """Admin-role users cannot be created with study assignments."""
        login_admin(client)
        resp = client.post('/api/admin/users', json={
            'first_name': 'Admin',
            'last_name': 'Assigned',
            'email': 'admin-assigned@example.com',
            'role': 'admin',
            'password': 'securepass',
            'study_ids': [user_study.id],
        })
        assert resp.status_code == 400
        errors = resp.get_json()['errors']
        assert any('participant' in err.lower() for err in errors)

    def test_create_user_duplicate_email(self, client, admin_user, test_user):
        """Duplicate email returns 400."""
        login_admin(client)
        resp = client.post('/api/admin/users', json={
            'first_name': 'Dup',
            'last_name': 'User',
            'email': 'participant@example.com',
            'institution': 'Hospital',
            'role': 'participant',
            'password': 'securepass',
        })
        assert resp.status_code == 400
        assert 'already exists' in resp.get_json()['errors'][0]

    def test_create_user_missing_required_fields(self, client, admin_user):
        """Missing required fields return 400 with errors."""
        login_admin(client)
        resp = client.post('/api/admin/users', json={
            'email': 'incomplete@example.com',
        })
        assert resp.status_code == 400
        errors = resp.get_json()['errors']
        assert len(errors) > 0


# ===========================================================================
# Test: GET /api/admin/users/:id
# ===========================================================================

class TestGetUser:

    def test_get_user_detail(self, client, admin_user, test_user):
        """Get a specific user by ID."""
        login_admin(client)
        resp = client.get(f'/api/admin/users/{test_user.id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['email'] == 'participant@example.com'
        assert 'studies' in data

    def test_get_user_not_found(self, client, admin_user):
        """Nonexistent user ID returns 404."""
        login_admin(client)
        resp = client.get('/api/admin/users/99999')
        assert resp.status_code == 404


# ===========================================================================
# Test: PUT /api/admin/users/:id
# ===========================================================================

class TestUpdateUser:

    def test_update_user_name_institution(self, client, admin_user, test_user, db):
        """Update user name and institution."""
        login_admin(client)
        resp = client.put(f'/api/admin/users/{test_user.id}', json={
            'first_name': 'Updated',
            'last_name': 'Name',
            'email': 'participant@example.com',
            'institution': 'New Hospital',
            'role': 'participant',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['first_name'] == 'Updated'
        assert data['institution'] == 'New Hospital'

    def test_update_user_role(self, client, admin_user, test_user, db):
        """Update user role to admin."""
        login_admin(client)
        resp = client.put(f'/api/admin/users/{test_user.id}', json={
            'first_name': 'Test',
            'last_name': 'Participant',
            'email': 'participant@example.com',
            'role': 'admin',
        })
        assert resp.status_code == 200
        assert resp.get_json()['role'] == 'admin'

    def test_update_user_role_with_assignments_rejected(self, client, admin_user, test_user, user_study, db):
        """Cannot promote a participant with assignments/ratings to admin."""
        sp = StudyParticipant(study_id=user_study.id, user_id=test_user.id, random_seed=123)
        db.session.add(sp)
        db.session.commit()

        login_admin(client)
        resp = client.put(f'/api/admin/users/{test_user.id}', json={
            'first_name': 'Test',
            'last_name': 'Participant',
            'email': 'participant@example.com',
            'role': 'admin',
        })
        assert resp.status_code == 400
        errors = resp.get_json()['errors']
        assert any('unassign' in err.lower() for err in errors)

    def test_update_user_with_password_change(self, client, admin_user, test_user, db):
        """Update user with a new password."""
        login_admin(client)
        resp = client.put(f'/api/admin/users/{test_user.id}', json={
            'first_name': 'Test',
            'last_name': 'Participant',
            'email': 'participant@example.com',
            'institution': 'Test Hospital',
            'role': 'participant',
            'password': 'newpassword',
        })
        assert resp.status_code == 200

        # Verify new password works
        client.post('/api/auth/logout')
        resp = client.post('/api/auth/login', json={
            'email': 'participant@example.com',
            'password': 'newpassword',
        })
        assert resp.status_code == 200

    def test_update_user_duplicate_email(self, client, admin_user, test_user, db):
        """Cannot update email to one that already exists."""
        login_admin(client)
        resp = client.put(f'/api/admin/users/{test_user.id}', json={
            'first_name': 'Test',
            'last_name': 'Participant',
            'email': 'admin',
            'institution': 'Test Hospital',
            'role': 'participant',
        })
        assert resp.status_code == 400


# ===========================================================================
# Test: DELETE /api/admin/users/:id
# ===========================================================================

class TestDeleteUser:

    def test_delete_user_no_ratings(self, client, admin_user, test_user, db):
        """Delete a user with no ratings succeeds."""
        login_admin(client)
        resp = client.delete(f'/api/admin/users/{test_user.id}')
        assert resp.status_code == 204

        assert db.session.get(User, test_user.id) is None

    def test_delete_user_with_ratings_no_confirm(self, client, admin_user, participant_with_ratings):
        """Delete user with ratings requires confirmation -> 409."""
        login_admin(client)
        resp = client.delete(f'/api/admin/users/{participant_with_ratings.id}')
        assert resp.status_code == 409
        data = resp.get_json()
        assert data['confirm_required'] is True

    def test_delete_user_with_ratings_confirmed(self, client, admin_user, participant_with_ratings, db):
        """Delete user with ratings + confirm=yes succeeds."""
        login_admin(client)
        uid = participant_with_ratings.id
        resp = client.delete(f'/api/admin/users/{uid}?confirm=yes')
        assert resp.status_code == 204

        assert db.session.get(User, uid) is None


# ===========================================================================
# Test: POST /api/admin/users/:id/reset-password
# ===========================================================================

class TestResetPassword:

    def test_reset_password(self, client, admin_user, test_user, db):
        """Admin resets a user's password."""
        login_admin(client)
        resp = client.post(f'/api/admin/users/{test_user.id}/reset-password', json={
            'new_password': 'resetpassword',
        })
        assert resp.status_code == 200

        # Verify new password works
        client.post('/api/auth/logout')
        resp = client.post('/api/auth/login', json={
            'email': 'participant@example.com',
            'password': 'resetpassword',
        })
        assert resp.status_code == 200

    def test_reset_password_not_found(self, client, admin_user):
        """Reset password for nonexistent user returns 404."""
        login_admin(client)
        resp = client.post('/api/admin/users/99999/reset-password', json={
            'new_password': 'whatever',
        })
        assert resp.status_code == 404
