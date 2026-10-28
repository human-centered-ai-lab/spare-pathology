"""API endpoints for authentication: login, logout, current user, change password, test-user reset."""

from datetime import datetime, timezone

from flask import jsonify, request, session
from flask_login import current_user, login_user, logout_user

from app import db
from app.api import bp
from app.api.decorators import api_admin_required, api_login_required
from app.models import StudyParticipant, Rating, User


@bp.route('/auth/login', methods=['POST'])
def api_login():
    """Authenticate a user with JSON credentials and set session cookie.

    Request JSON:
        {"email": "...", "password": "..."}

    Returns user object JSON on success, 401 on failure.
    """
    if current_user.is_authenticated:
        return jsonify(serialize_user(current_user)), 200

    data = request.get_json(silent=True) or {}
    if not all(isinstance(data.get(key, ''), str) for key in ('email', 'password')):
        return jsonify(error='Email and password must be strings.'), 400
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'Email and password are required.'}), 400

    user = User.query.filter_by(email=email).first()

    if user is None or not user.check_password(password):
        return jsonify({'error': 'Invalid email or password.'}), 401

    login_user(user)
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify(serialize_user(user)), 200


@bp.route('/auth/logout', methods=['POST'])
def api_logout():
    """Clear the session and return 204."""
    # Explicitly clear impersonation marker so logout does not depend on
    # before_request side effects.
    session.pop('_impersonator_id', None)
    logout_user()
    return '', 204


@bp.route('/auth/me', methods=['GET'])
def api_me():
    """Return the currently authenticated user as JSON, or 401."""
    if not current_user.is_authenticated:
        return jsonify({'error': 'Not authenticated.'}), 401
    return jsonify(serialize_user(current_user)), 200


@bp.route('/auth/change-password', methods=['POST'])
@api_login_required
def api_change_password():
    """Change the current user's password.

    Request JSON:
        {"current_password": "...", "new_password": "...", "confirm_password": "..."}
    """
    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')

    if not all(isinstance(value, str) for value in (current_password, new_password, confirm_password)):
        return jsonify(error='Passwords must be strings.'), 400
    if len(new_password.encode('utf-8')) > 72:
        return jsonify(error='Password must be at most 72 UTF-8 bytes.'), 400

    if not current_user.check_password(current_password):
        return jsonify({'error': 'Current password is incorrect.'}), 400

    if not new_password:
        return jsonify({'error': 'New password cannot be empty.'}), 400

    if new_password != confirm_password:
        return jsonify({'error': 'New passwords do not match.'}), 400

    current_user.set_password(new_password)
    db.session.commit()

    return jsonify({'message': 'Password changed successfully.'}), 200


@bp.route('/auth/test-user-reset', methods=['POST'])
@api_login_required
def api_test_user_reset():
    """Reset all test user data: clear ratings and submission states across all studies.

    Only accessible by the test user (is_test_user=True).
    """
    if not current_user.is_test_user:
        return jsonify({'error': 'Forbidden. Only test users can reset data.'}), 403

    user_id = current_user.id

    # Delete all ratings for this user
    ratings_deleted = Rating.query.filter_by(user_id=user_id).delete()

    # Reset all study participant records: submitted=False, submitted_at=None, last_viewed_image_id=None
    study_participants = StudyParticipant.query.filter_by(user_id=user_id).all()
    studies_reset = 0
    for pu in study_participants:
        if pu.submitted or pu.last_viewed_image_id is not None:
            studies_reset += 1
        pu.submitted = False
        pu.submitted_at = None
        pu.last_viewed_image_id = None

    db.session.commit()

    return jsonify({
        'ok': True,
        'ratings_deleted': ratings_deleted,
        'studies_reset': studies_reset,
    })


@bp.route('/admin/impersonate/<int:user_id>', methods=['POST'])
@api_admin_required
def api_impersonate(user_id):
    """Impersonate a participant user.

    Stores the admin's real user ID in the session so they can switch back.
    """
    target = db.session.get(User, user_id)
    if target is None:
        return jsonify({'error': 'User not found.'}), 404

    if target.role != 'participant':
        return jsonify({'error': 'Can only impersonate participants.'}), 400

    session['_impersonator_id'] = current_user.id
    login_user(target)

    return jsonify(serialize_user(target)), 200


@bp.route('/admin/unimpersonate', methods=['POST'])
@api_login_required
def api_unimpersonate():
    """Stop impersonating and restore the admin session."""
    impersonator_id = session.pop('_impersonator_id', None)
    if impersonator_id is None:
        return jsonify({'error': 'Not impersonating.'}), 400

    admin = db.session.get(User, impersonator_id)
    if admin is None:
        return jsonify({'error': 'Original admin not found.'}), 500

    login_user(admin)
    return jsonify(serialize_user(admin)), 200


def serialize_user(u):
    """Serialize a User model instance to a JSON-safe dict."""
    data = {
        'id': u.id,
        'first_name': u.first_name,
        'last_name': u.last_name,
        'email': u.email,
        'institution': u.institution,
        'role': u.role,
        'comments': u.comments,
        'last_login': u.last_login.isoformat() if u.last_login else None,
        'is_test_user': u.is_test_user,
        'created_at': u.created_at.isoformat(),
    }
    impersonator_id = session.get('_impersonator_id')
    if impersonator_id is not None:
        data['impersonating'] = True
        data['impersonator_id'] = impersonator_id
    return data
