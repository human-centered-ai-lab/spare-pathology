"""API endpoints for admin participant management: list, assign, unassign, unsubmit."""

import random

from flask import jsonify, request

from app import db
from app.api import bp
from app.api.decorators import api_admin_required
from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import get_ordinal_question_ids
from app.services.study_lifecycle import check_auto_finish
from app.services.statistics import invalidate_stats_cache


def _get_participant_status(user, study):
    """Compute the display status for a participant in a study.

    Returns a dict with:
    - status_key: 'not_started', 'in_progress', 'submitted'
    - status_label: human-readable label
    - completion_pct: integer percentage (0-100)
    """
    pu = StudyParticipant.query.filter_by(
        study_id=study.id, user_id=user.id,
    ).first()

    if pu and pu.submitted:
        return {
            'status_key': 'submitted',
            'status_label': 'Submitted',
            'completion_pct': 100,
        }

    schema = study.rating_schema or {'questions': []}
    ordinal_ids = get_ordinal_question_ids(schema)
    images = DatasetImage.query.filter_by(study_id=study.id).all()
    total_items = len(images) * len(ordinal_ids) if ordinal_ids else len(images)

    if total_items == 0:
        return {
            'status_key': 'not_started',
            'status_label': 'Not started',
            'completion_pct': 0,
        }

    ratings = Rating.query.filter_by(
        user_id=user.id, study_id=study.id,
    ).all()

    completed_items = 0
    for rating in ratings:
        responses = rating.responses or {}
        if ordinal_ids:
            for qid in ordinal_ids:
                if qid in responses and responses[qid] is not None:
                    completed_items += 1
        else:
            if responses:
                completed_items += 1

    if completed_items == 0:
        return {
            'status_key': 'not_started',
            'status_label': 'Not started',
            'completion_pct': 0,
        }

    pct = int(round(completed_items / total_items * 100))
    if pct > 100:
        pct = 100

    return {
        'status_key': 'in_progress',
        'status_label': f'In progress ({pct}%)',
        'completion_pct': pct,
    }


@bp.route('/admin/studies/<int:study_id>/participants', methods=['GET'])
@api_admin_required
def api_list_participants(study_id):
    """List participants assigned to a study with computed status.

    Returns assigned participants (with status) and available (unassigned) participants.
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    # Get assigned users with their StudyParticipant data
    assigned_pus = (
        StudyParticipant.query
        .join(User, StudyParticipant.user_id == User.id)
        .filter(
            StudyParticipant.study_id == study.id,
            User.role == 'participant',
        )
        .all()
    )
    assigned_user_ids = {pu.user_id for pu in assigned_pus}

    # Build participant list with status
    participant_list = []
    for pu in assigned_pus:
        user = pu.user
        status = _get_participant_status(user, study)
        has_ratings = Rating.query.filter_by(
            user_id=user.id, study_id=study.id,
        ).first() is not None
        participant_list.append({
            'user_id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'institution': user.institution,
            'is_test_user': user.is_test_user,
            'status_key': status['status_key'],
            'status_label': status['status_label'],
            'completion_pct': status['completion_pct'],
            'has_ratings': has_ratings,
            'submitted': pu.submitted,
            'submitted_at': pu.submitted_at.isoformat() if pu.submitted_at else None,
        })

    # Get available (unassigned) participant users
    available_users_query = (
        User.query
        .filter(
            User.role == 'participant',
            User.is_test_user.is_(False),
        )
        .order_by(User.last_name, User.first_name)
    )
    if assigned_user_ids:
        available_users_query = available_users_query.filter(
            ~User.id.in_(assigned_user_ids),
        )
    available_users = available_users_query.all()

    available_list = []
    for user in available_users:
        available_list.append({
            'user_id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'institution': user.institution,
        })

    return jsonify({
        'assigned': participant_list,
        'available': available_list,
    })


@bp.route('/admin/studies/<int:study_id>/participants/assign', methods=['POST'])
@api_admin_required
def api_assign_participant(study_id):
    """Assign a user to this study.

    Request JSON:
        {"user_id": 123}
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    reactivate = bool(data.get('reactivate', False))

    if study.status == 'finished' and not reactivate:
        return jsonify({'error': 'Cannot modify participants on a finished study.'}), 403

    if not user_id:
        return jsonify({'error': 'user_id is required.'}), 400

    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid user_id.'}), 400
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({'error': 'User not found.'}), 404
    if user.role != 'participant':
        return jsonify({'error': 'Only participant users can be assigned to studies.'}), 400

    # Check if already assigned
    existing = StudyParticipant.query.filter_by(
        study_id=study.id, user_id=user.id,
    ).first()
    if existing:
        return jsonify({'error': 'User is already assigned to this study.'}), 409

    # Reactivate finished study
    reactivated = False
    if study.status == 'finished' and reactivate:
        study.status = 'active'
        reactivated = True

    pu = StudyParticipant(
        study_id=study.id,
        user_id=user.id,
        random_seed=random.randint(0, 2**31 - 1),
    )
    db.session.add(pu)
    db.session.commit()

    return jsonify({
        'message': f'User {user.first_name} {user.last_name} assigned to study.',
        'user_id': user.id,
        'study_id': study.id,
        'reactivated': reactivated,
    }), 201


@bp.route('/admin/studies/<int:study_id>/participants/unassign', methods=['POST'])
@api_admin_required
def api_unassign_participant(study_id):
    """Unassign a user from this study.

    Request JSON:
        {"user_id": 123, "confirm": true}
        (confirm required if user has ratings — ratings will be deleted)
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')

    if not user_id:
        return jsonify({'error': 'user_id is required.'}), 400

    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid user_id.'}), 400
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({'error': 'User not found.'}), 404

    # Test users cannot be unassigned
    if user.is_test_user:
        return jsonify({'error': 'Test users cannot be unassigned from studies.'}), 403

    pu = StudyParticipant.query.filter_by(
        study_id=study.id, user_id=user.id,
    ).first()
    if not pu:
        return jsonify({'error': 'User is not assigned to this study.'}), 404

    # Check for ratings
    has_ratings = Rating.query.filter_by(
        user_id=user.id, study_id=study.id,
    ).first() is not None
    confirmed = bool(data.get('confirm', False))

    if has_ratings and not confirmed:
        return jsonify({
            'error': f'User {user.first_name} {user.last_name} has ratings in this study. Unassigning will permanently delete all their ratings. Please confirm.',
            'has_ratings': True,
            'confirm_required': True,
        }), 409

    # Delete ratings for this study
    Rating.query.filter_by(user_id=user.id, study_id=study.id).delete()

    # Delete the study assignment
    db.session.delete(pu)
    db.session.commit()

    invalidate_stats_cache(study.id)

    check_auto_finish(study)

    return jsonify({
        'message': f'User {user.first_name} {user.last_name} unassigned from study.',
    })


@bp.route('/admin/studies/<int:study_id>/participants/<int:user_id>/unsubmit', methods=['POST'])
@api_admin_required
def api_unsubmit_participant(study_id, user_id):
    """Un-submit a participant's evaluation, making their ratings editable again."""
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    if study.status == 'finished':
        return jsonify({'error': 'Cannot modify participants on a finished study.'}), 403

    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({'error': 'User not found.'}), 404

    pu = StudyParticipant.query.filter_by(
        study_id=study.id, user_id=user.id,
    ).first()
    if not pu:
        return jsonify({'error': 'User is not assigned to this study.'}), 404

    pu.submitted = False
    pu.submitted_at = None
    db.session.commit()

    invalidate_stats_cache(study.id)

    return jsonify({
        'message': f'Submission for {user.first_name} {user.last_name} has been reverted.',
    })
