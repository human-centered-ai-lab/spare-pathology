"""API endpoints for admin user management: CRUD, study assignment, password reset."""

import random

from flask import jsonify, request
from flask_login import current_user

from app import db
from app.api import bp
from app.api.auth import serialize_user
from app.api.decorators import api_admin_required
from app.models import Study, StudyParticipant, Rating, User


def serialize_user_detail(u):
    """Serialize a User with study assignment details."""
    data = serialize_user(u)
    data['studies'] = []
    for pu in u.study_participants:
        study = pu.study
        has_ratings = Rating.query.filter_by(
            user_id=u.id, study_id=study.id,
        ).first() is not None
        data['studies'].append({
            'study_id': study.id,
            'study_name': study.name,
            'submitted': pu.submitted,
            'submitted_at': pu.submitted_at.isoformat() if pu.submitted_at else None,
            'has_ratings': has_ratings,
        })
    return data


def _validate_user_fields(first_name, last_name, email, role, institution,
                          password_required=False, password=''):
    """Validate user fields and return a list of error messages."""
    errors = []
    if not first_name:
        errors.append('First name is required.')
    if not last_name:
        errors.append('Last name is required.')
    if not email:
        errors.append('Email is required.')
    if role not in ('admin', 'participant'):
        errors.append('Role must be either admin or participant.')
    if role == 'participant' and not institution:
        errors.append('Institution is required for participants.')
    if password_required and not password:
        errors.append('Password is required.')
    if not isinstance(password, str) or len(password.encode('utf-8')) > 72:
        errors.append('Password must be a string of at most 72 UTF-8 bytes.')
    return errors


@bp.route('/admin/users', methods=['GET'])
@api_admin_required
def api_list_users():
    """List all users as JSON."""
    users = User.query.order_by(User.last_name, User.first_name).all()
    return jsonify([serialize_user(u) for u in users])


@bp.route('/admin/users', methods=['POST'])
@api_admin_required
def api_create_user():
    """Create a new user from JSON body.

    Request JSON:
        {
            "first_name": "...",
            "last_name": "...",
            "email": "...",
            "institution": "...",
            "role": "participant",
            "password": "...",
            "is_test_user": false,
            "comments": "...",
            "study_ids": [1, 2]
        }
    """
    data = request.get_json(silent=True) or {}

    if any(data.get(key) is not None and not isinstance(data[key], str)
           for key in ('first_name', 'last_name', 'email', 'institution', 'comments')):
        return jsonify(errors=['User details must be strings.']), 400

    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    email = (data.get('email') or '').strip()
    institution = (data.get('institution') or '').strip()
    role = data.get('role', 'participant')
    password = data.get('password', '')
    is_test_user = bool(data.get('is_test_user', False))
    comments = (data.get('comments') or '').strip()

    # Validation
    errors = _validate_user_fields(
        first_name, last_name, email, role, institution,
        password_required=True, password=password,
    )

    # Check email uniqueness
    if email and User.query.filter_by(email=email).first():
        errors.append('A user with this email already exists.')

    if errors:
        return jsonify({'errors': errors}), 400

    user = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        institution=institution or None,
        role=role,
        is_test_user=is_test_user,
        comments=comments or None,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()  # Get the user ID

    # Assign to selected studies (participants only)
    study_ids = data.get('study_ids', [])
    if study_ids is None:
        study_ids = []
    if not isinstance(study_ids, list):
        db.session.rollback()
        return jsonify({'errors': ['study_ids must be a list.']}), 400
    if role != 'participant' and study_ids:
        db.session.rollback()
        return jsonify({'errors': ['Only participant users can be assigned to studies.']}), 400

    parsed_study_ids = []
    seen_study_ids = set()
    for sid in study_ids:
        try:
            sid_int = int(sid)
        except (ValueError, TypeError):
            db.session.rollback()
            return jsonify({'errors': [f'Invalid study_id: {sid}']}), 400
        if sid_int in seen_study_ids:
            continue
        seen_study_ids.add(sid_int)
        parsed_study_ids.append(sid_int)

    for sid_int in parsed_study_ids:
        s = db.session.get(Study, sid_int)
        if s is None:
            db.session.rollback()
            return jsonify({'errors': [f'Study not found: {sid_int}']}), 400
        pu = StudyParticipant(
            study_id=sid_int,
            user_id=user.id,
            random_seed=random.randint(0, 2**31 - 1),
        )
        db.session.add(pu)

    db.session.commit()

    return jsonify(serialize_user_detail(user)), 201


@bp.route('/admin/users/<int:user_id>', methods=['GET'])
@api_admin_required
def api_get_user(user_id):
    """Get user detail with study assignments."""
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({'error': 'User not found.'}), 404

    return jsonify(serialize_user_detail(user))


@bp.route('/admin/users/<int:user_id>', methods=['PUT'])
@api_admin_required
def api_update_user(user_id):
    """Update user from JSON body.

    Request JSON:
        {
            "first_name": "...",
            "last_name": "...",
            "email": "...",
            "institution": "...",
            "role": "participant",
            "password": "...",  (optional - only set if non-empty)
            "is_test_user": false,
            "comments": "..."
        }
    """
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({'error': 'User not found.'}), 404

    data = request.get_json(silent=True) or {}

    if any(data.get(key) is not None and not isinstance(data[key], str)
           for key in ('first_name', 'last_name', 'email', 'institution', 'comments')):
        return jsonify(errors=['User details must be strings.']), 400

    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    email = (data.get('email') or '').strip()
    institution = (data.get('institution') or '').strip()
    role = data.get('role', 'participant')
    password = data.get('password', '')
    is_test_user = bool(data.get('is_test_user', False))
    comments = (data.get('comments') or '').strip()

    # Prevent admin from changing their own role
    if user.id == current_user.id and role != user.role:
        return jsonify({'errors': ['Cannot change your own role.']}), 400

    # Validation
    errors = _validate_user_fields(
        first_name, last_name, email, role, institution,
        password_required=False, password=password,
    )

    # Check email uniqueness (exclude current user)
    if email:
        existing = User.query.filter_by(email=email).first()
        if existing and existing.id != user.id:
            errors.append('A user with this email already exists.')

    if errors:
        return jsonify({'errors': errors}), 400

    # Preserve participant-only study assignment invariant on role change.
    if user.role == 'participant' and role != 'participant':
        has_assignment = StudyParticipant.query.filter_by(user_id=user.id).first() is not None
        has_ratings = Rating.query.filter_by(user_id=user.id).first() is not None
        if has_assignment or has_ratings:
            return jsonify({
                'errors': [
                    'Cannot change role while the user has study assignments or ratings. '
                    'Unassign the user from all studies first.'
                ]
            }), 400

    user.first_name = first_name
    user.last_name = last_name
    user.email = email
    user.institution = institution or None
    user.role = role
    user.is_test_user = is_test_user
    user.comments = comments or None

    if password:
        user.set_password(password)

    db.session.commit()

    return jsonify(serialize_user_detail(user))


@bp.route('/admin/users/<int:user_id>', methods=['DELETE'])
@api_admin_required
def api_delete_user(user_id):
    """Delete a user.

    Query param: ?confirm=yes required if user has ratings.
    """
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({'error': 'User not found.'}), 404

    if user.id == current_user.id:
        return jsonify({'error': 'Cannot delete your own account.'}), 400

    has_ratings = Rating.query.filter_by(user_id=user.id).first() is not None
    confirmed = request.args.get('confirm') == 'yes'

    if has_ratings and not confirmed:
        return jsonify({
            'error': 'User has ratings. Please confirm deletion.',
            'has_ratings': True,
            'confirm_required': True,
        }), 409

    db.session.delete(user)
    db.session.commit()

    return '', 204


@bp.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@api_admin_required
def api_reset_user_password(user_id):
    """Admin resets a user's password.

    Request JSON:
        {"new_password": "..."}
    """
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({'error': 'User not found.'}), 404

    data = request.get_json(silent=True) or {}
    new_password = data.get('new_password', '')

    if not isinstance(new_password, str) or len(new_password.encode('utf-8')) > 72:
        return jsonify(error='Password must be a string of at most 72 UTF-8 bytes.'), 400

    if not new_password:
        return jsonify({'error': 'New password cannot be empty.'}), 400

    user.set_password(new_password)
    db.session.commit()

    return jsonify({'message': f'Password for {user.email} has been reset.'})
