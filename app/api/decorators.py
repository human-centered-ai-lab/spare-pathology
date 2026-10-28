"""API authentication decorators returning JSON error responses."""

from functools import wraps

from flask import jsonify
from flask_login import current_user


def api_login_required(f):
    """Return 401 JSON if the user is not authenticated."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required.'}), 401
        return f(*args, **kwargs)
    return decorated_function


def api_admin_required(f):
    """Return 401/403 JSON if the user is not an authenticated admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required.'}), 401
        if current_user.role != 'admin':
            return jsonify({'error': 'Admin access required.'}), 403
        return f(*args, **kwargs)
    return decorated_function


def api_participant_required(f):
    """Return 401/403 JSON if the user is not an authenticated participant."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required.'}), 401
        if current_user.role != 'participant':
            return jsonify({'error': 'Participant access required.'}), 403
        return f(*args, **kwargs)
    return decorated_function
