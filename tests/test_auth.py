"""Tests for authentication API endpoints: login, logout, me, change-password."""


from tests.helpers import login, login_admin, login_participant


class TestLogin:

    def test_login_valid_admin(self, client, admin_user):
        """POST /api/auth/login succeeds for admin with correct credentials."""
        resp = login_admin(client)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['email'] == 'admin'
        assert data['role'] == 'admin'

    def test_login_valid_participant(self, client, test_user):
        """POST /api/auth/login succeeds for participant with correct credentials."""
        resp = login_participant(client)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['email'] == 'participant@example.com'
        assert data['role'] == 'participant'

    def test_login_wrong_password(self, client, admin_user):
        """POST /api/auth/login returns 401 for wrong password."""
        resp = login(client, 'admin', 'wrongpassword')
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client, db):
        """POST /api/auth/login returns 401 for nonexistent email."""
        resp = login(client, 'nobody@example.com', 'password')
        assert resp.status_code == 401


class TestMe:

    def test_get_current_user_authenticated(self, client, admin_user):
        """GET /api/auth/me returns current user when authenticated."""
        login_admin(client)
        resp = client.get('/api/auth/me')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['email'] == 'admin'

    def test_get_current_user_unauthenticated(self, client, db):
        """GET /api/auth/me returns 401 when not authenticated."""
        resp = client.get('/api/auth/me')
        assert resp.status_code == 401


class TestLogout:

    def test_logout_clears_session(self, client, admin_user):
        """POST /api/auth/logout clears the session so /me returns 401."""
        login_admin(client)
        resp = client.post('/api/auth/logout')
        assert resp.status_code == 204

        resp = client.get('/api/auth/me')
        assert resp.status_code == 401


class TestChangePassword:

    def test_change_password_success(self, client, test_user, db):
        """POST /api/auth/change-password updates the password."""
        login_participant(client)
        resp = client.post('/api/auth/change-password', json={
            'current_password': 'testpassword',
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123',
        })
        assert resp.status_code == 200

        # Verify the new password works
        client.post('/api/auth/logout')
        resp = login(client, 'participant@example.com', 'newpassword123')
        assert resp.status_code == 200

    def test_change_password_wrong_current(self, client, test_user):
        """POST /api/auth/change-password returns 400 if current password is wrong."""
        login_participant(client)
        resp = client.post('/api/auth/change-password', json={
            'current_password': 'wrongpassword',
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123',
        })
        assert resp.status_code == 400

    def test_change_password_mismatch_confirm(self, client, test_user):
        """POST /api/auth/change-password returns 400 if confirm doesn't match."""
        login_participant(client)
        resp = client.post('/api/auth/change-password', json={
            'current_password': 'testpassword',
            'new_password': 'newpassword123',
            'confirm_password': 'differentpassword',
        })
        assert resp.status_code == 400
