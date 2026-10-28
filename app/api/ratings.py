"""API endpoints for rating CRUD operations."""

import math
import random

from flask import jsonify, request, session
from flask_login import current_user

from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified

from app import db
from app.api import bp
from app.api.decorators import api_participant_required
from app.models import DatasetImage, Study, StudyParticipant, Rating
from app.services.schema_service import evaluate_condition, get_ordinal_question_ids, get_question_by_id
from app.services.statistics import invalidate_stats_cache


def _get_study_access(study_id):
    """Return (study, study_participant) or (None, error_response).

    For test users, a StudyParticipant may not exist; we return None for pu.
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return None, (jsonify({'error': 'Study not found.'}), 404)

    # Non-test, non-impersonating users can only access active studies
    is_impersonating = session.get('_impersonator_id') is not None
    if not current_user.is_test_user and not is_impersonating and study.status not in ('active', 'finished'):
        return None, (jsonify({'error': 'Study is not active.'}), 403)

    pu = StudyParticipant.query.filter_by(
        study_id=study.id,
        user_id=current_user.id,
    ).first()

    if current_user.is_test_user:
        # Test users can access any study even without assignment
        return (study, pu), None

    if pu is None:
        return None, (jsonify({'error': 'Access denied.'}), 403)

    return (study, pu), None


def _get_rating_for_current_user(rating_id):
    """Return (rating, None) or (None, error_response)."""
    rating = db.session.get(Rating, rating_id)
    if rating is None:
        return None, (jsonify({'error': 'Rating not found.'}), 404)
    if rating.user_id != current_user.id:
        return None, (jsonify({'error': 'Access denied.'}), 403)
    return rating, None


def _check_not_impersonating():
    """Return error response if the current session is an admin impersonation, else None."""
    if session.get('_impersonator_id'):
        return jsonify({'error': 'Read-only: admin impersonation.'}), 403
    return None


def _check_not_submitted(rating):
    """Return error response if the user has already submitted this study, else None."""
    result, error = _get_study_access(rating.study_id)
    if error:
        return error
    study, _ = result
    if not current_user.is_test_user and study.status != 'active':
        return jsonify({'error': 'Study is not active.'}), 403
    pu = StudyParticipant.query.filter_by(
        study_id=rating.study_id,
        user_id=current_user.id,
    ).first()
    if pu and pu.submitted:
        return jsonify({'error': 'Already submitted.'}), 403
    return None


def _rating_response_json(rating):
    """Return a standard JSON dict for a rating."""
    return {
        'id': rating.id,
        'user_id': rating.user_id,
        'dataset_image_id': rating.dataset_image_id,
        'study_id': rating.study_id,
        'responses': rating.responses,
        'uncertainty': rating.uncertainty,
        'time_spent_seconds': rating.time_spent_seconds,
        'created_at': rating.created_at.isoformat(),
        'updated_at': rating.updated_at.isoformat(),
    }


@bp.route('/ratings/open', methods=['POST'])
@api_participant_required
def open_rating():
    """Create a Rating row with empty responses when an image is first opened.

    Request JSON:
        {
            "study_id": int,
            "dataset_image_id": int
        }

    Returns the rating as JSON, or the existing rating if already opened.
    """
    impersonation_error = _check_not_impersonating()
    if impersonation_error:
        return impersonation_error

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid JSON.'}), 400

    study_id = data.get('study_id')
    dataset_image_id = data.get('dataset_image_id')

    if not study_id or not dataset_image_id:
        return jsonify({'error': 'study_id and dataset_image_id are required.'}), 400

    result, error = _get_study_access(study_id)
    if error:
        return error
    study, pu = result

    if not current_user.is_test_user and study.status != 'active':
        return jsonify({'error': 'Study is not active.'}), 403

    # Block if user has already submitted
    if pu and pu.submitted:
        return jsonify({'error': 'Already submitted.'}), 403

    # Verify the image belongs to this study
    image = db.session.get(DatasetImage, dataset_image_id)
    if image is None or image.study_id != study.id:
        return jsonify({'error': 'Image not found.'}), 404

    # Check if rating already exists
    existing = Rating.query.filter_by(
        user_id=current_user.id,
        dataset_image_id=dataset_image_id,
        study_id=study.id,
    ).first()

    if existing:
        return jsonify(_rating_response_json(existing))

    # Create new rating with empty responses
    rating = Rating(
        user_id=current_user.id,
        dataset_image_id=dataset_image_id,
        study_id=study.id,
        responses={},
    )
    db.session.add(rating)

    # Update last_viewed_image on the study_participant
    if pu:
        pu.last_viewed_image_id = dataset_image_id

    db.session.commit()

    return jsonify(_rating_response_json(rating)), 201


@bp.route('/ratings/<int:rating_id>/response', methods=['PUT'])
@api_participant_required
def save_response(rating_id):
    """Save a single question response (immediate save for discrete changes).

    Request JSON:
        {"question_id": "F1", "value": 2}
    """
    impersonation_error = _check_not_impersonating()
    if impersonation_error:
        return impersonation_error

    rating, error = _get_rating_for_current_user(rating_id)
    if error:
        return error
    submitted_error = _check_not_submitted(rating)
    if submitted_error:
        return submitted_error

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid JSON.'}), 400

    question_id = data.get('question_id')
    if question_id is None or 'value' not in data:
        return jsonify({'error': 'question_id and value are required.'}), 400

    value = data['value']

    # Validate question ID/type and ordinal value range
    study = db.session.get(Study, rating.study_id)
    schema = study.rating_schema or {} if study else {}
    question = get_question_by_id(schema, question_id)
    if question is None:
        return jsonify({'error': f'Unknown question_id: {question_id}.'}), 400
    if question.get('type') != 'ordinal':
        return jsonify({'error': f'Question {question_id} is not an ordinal question.'}), 400

    if isinstance(value, str) and value.lstrip('-').isdigit():
        value = int(value)
    if type(value) is not int:
        return jsonify({'error': 'Ordinal value must be an integer.'}), 400
    qmin = question.get('min', 0)
    qmax = question.get('max', 2)
    if value < qmin or value > qmax:
        return jsonify({
            'error': f'Value {value} is out of range [{qmin}, {qmax}] for question {question_id}.'
        }), 400

    # Refresh to get latest DB state, then update and flag for change detection
    db.session.refresh(rating)
    responses = dict(rating.responses or {})
    responses[question_id] = value
    rating.responses = responses
    flag_modified(rating, 'responses')

    db.session.commit()
    invalidate_stats_cache(rating.study_id)

    return jsonify(_rating_response_json(rating))


@bp.route('/ratings/<int:rating_id>/text-response', methods=['PUT'])
@api_participant_required
def save_text_response(rating_id):
    """Save a text response (called after debounce).

    Request JSON:
        {"question_id": "text1", "value": "some text"}
    """
    impersonation_error = _check_not_impersonating()
    if impersonation_error:
        return impersonation_error

    rating, error = _get_rating_for_current_user(rating_id)
    if error:
        return error
    submitted_error = _check_not_submitted(rating)
    if submitted_error:
        return submitted_error

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid JSON.'}), 400

    question_id = data.get('question_id')
    if question_id is None or 'value' not in data:
        return jsonify({'error': 'question_id and value are required.'}), 400

    value = data['value']

    # The general notes field is available independently of schema questions.
    study = db.session.get(Study, rating.study_id)
    schema = study.rating_schema or {} if study else {}
    question = get_question_by_id(schema, question_id)
    if question is None:
        if question_id != 'notes':
            return jsonify({'error': f'Unknown question_id: {question_id}.'}), 400
    elif question.get('type') != 'free_text':
        return jsonify({'error': f'Question {question_id} is not a text question.'}), 400

    # Validate text length
    MAX_TEXT_LENGTH = 10000
    if not isinstance(value, str) or len(value) > MAX_TEXT_LENGTH:
        return jsonify({'error': f'Text response must be a string of at most {MAX_TEXT_LENGTH} characters.'}), 400

    db.session.refresh(rating)
    responses = dict(rating.responses or {})
    responses[question_id] = value
    rating.responses = responses
    flag_modified(rating, 'responses')

    db.session.commit()
    invalidate_stats_cache(rating.study_id)

    return jsonify(_rating_response_json(rating))


@bp.route('/ratings/<int:rating_id>/uncertainty', methods=['PUT'])
@api_participant_required
def save_uncertainty(rating_id):
    """Save the uncertainty flag.

    Request JSON:
        {"value": true}
    """
    impersonation_error = _check_not_impersonating()
    if impersonation_error:
        return impersonation_error

    rating, error = _get_rating_for_current_user(rating_id)
    if error:
        return error
    submitted_error = _check_not_submitted(rating)
    if submitted_error:
        return submitted_error

    data = request.get_json(silent=True)
    if not data or 'value' not in data:
        return jsonify({'error': 'value is required.'}), 400

    if not isinstance(data['value'], bool):
        return jsonify({'error': 'value must be a boolean.'}), 400
    rating.uncertainty = data['value']
    db.session.commit()
    invalidate_stats_cache(rating.study_id)

    return jsonify(_rating_response_json(rating))


@bp.route('/ratings/<int:rating_id>/time', methods=['PUT'])
@api_participant_required
def save_time(rating_id):
    """Add elapsed time to cumulative total.

    Request JSON:
        {"elapsed": 5.3}
    """
    impersonation_error = _check_not_impersonating()
    if impersonation_error:
        return impersonation_error

    rating, error = _get_rating_for_current_user(rating_id)
    if error:
        return error
    submitted_error = _check_not_submitted(rating)
    if submitted_error:
        return submitted_error

    data = request.get_json(silent=True)
    if not data or 'elapsed' not in data:
        return jsonify({'error': 'elapsed is required.'}), 400

    elapsed = data['elapsed']
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        return jsonify({'error': 'elapsed must be a non-negative number.'}), 400

    db.session.execute(
        Rating.__table__.update()
        .where(Rating.id == rating.id)
        .values(time_spent_seconds=func.coalesce(Rating.time_spent_seconds, 0.0) + elapsed)
    )
    db.session.commit()
    db.session.refresh(rating)

    return jsonify(_rating_response_json(rating))


@bp.route('/ratings/<int:rating_id>/failure-reason', methods=['PUT'])
@api_participant_required
def save_failure_reason(rating_id):
    """Save the failure reason.

    Request JSON:
        {"value": "Nuclear/cytology inconsistency (F1)"}
        or {"value": ["option1", "option2"]} for multi-select
        or {"value": null} to clear
    """
    impersonation_error = _check_not_impersonating()
    if impersonation_error:
        return impersonation_error

    rating, error = _get_rating_for_current_user(rating_id)
    if error:
        return error
    submitted_error = _check_not_submitted(rating)
    if submitted_error:
        return submitted_error

    data = request.get_json(silent=True)
    if data is None or 'value' not in data:
        return jsonify({'error': 'value is required.'}), 400

    value = data['value']

    # Normalize empty list to null (clearing the selection)
    if isinstance(value, list) and len(value) == 0:
        value = None

    # Validate failure_reason against schema options
    study = db.session.get(Study, rating.study_id)
    schema = study.rating_schema or {} if study else {}
    fr_config = schema.get('failure_reason', {})

    if value is not None and not fr_config.get('enabled', False):
        return jsonify({'error': 'Failure reason is not enabled for this study.'}), 400

    if value is not None:
        allowed_options = fr_config.get('options', [])
        if not allowed_options and value is not None:
            return jsonify({'error': 'No failure reason options configured.'}), 400
        multi_select = fr_config.get('multi_select', False)

        if isinstance(value, list):
            if not multi_select:
                return jsonify({'error': 'Multi-select is not enabled for failure reasons.'}), 400
            for opt in value:
                if not isinstance(opt, str):
                    return jsonify({'error': 'Each failure reason must be a string.'}), 400
                if allowed_options and opt not in allowed_options:
                    return jsonify({'error': f'Invalid failure reason: {opt}'}), 400
        elif isinstance(value, str):
            if allowed_options and value not in allowed_options:
                return jsonify({'error': f'Invalid failure reason: {value}'}), 400
        else:
            return jsonify({'error': 'Failure reason must be a string or list of strings.'}), 400

    # Check that the failure reason condition is actually met
    if value is not None:
        fr_condition = fr_config.get('condition')
        if fr_condition:
            db.session.refresh(rating)
            current_responses = dict(rating.responses or {})
            if not evaluate_condition(fr_condition, current_responses, schema):
                return jsonify({'error': 'Failure reason condition is not met.'}), 400

    db.session.refresh(rating)
    responses = dict(rating.responses or {})
    if value is None:
        responses.pop('failure_reason', None)
    else:
        responses['failure_reason'] = value
    rating.responses = responses
    flag_modified(rating, 'responses')

    db.session.commit()
    invalidate_stats_cache(rating.study_id)

    return jsonify(_rating_response_json(rating))


@bp.route('/studies/<int:study_id>/completion-status', methods=['GET'])
@api_participant_required
def completion_status(study_id):
    """Return completion check for the current user on a study.

    Returns JSON:
        {
            "complete": true/false,
            "total_images": N,
            "completed_images": M,
            "incomplete_images": [{"position": P, "missing": ["F3", "F4"]}, ...]
        }
    """
    result, error = _get_study_access(study_id)
    if error:
        return error
    study, pu = result

    schema = study.rating_schema or {'questions': []}
    ordinal_ids = get_ordinal_question_ids(schema)

    # Get images in the user's randomized order
    images = DatasetImage.query.filter_by(study_id=study.id).order_by(DatasetImage.id).all()
    if pu:
        rng = random.Random(pu.random_seed)
        rng.shuffle(images)

    # Get all ratings for this user in this study
    ratings = Rating.query.filter_by(
        user_id=current_user.id,
        study_id=study.id,
    ).all()
    ratings_by_image = {r.dataset_image_id: r for r in ratings}

    total_images = len(images)
    completed_images = 0
    incomplete_images = []

    for idx, img in enumerate(images):
        rating = ratings_by_image.get(img.id)
        responses = rating.responses if rating else {}

        missing = []
        for qid in ordinal_ids:
            if not responses or qid not in responses or responses[qid] is None:
                missing.append(qid)

        if not missing:
            completed_images += 1
        else:
            incomplete_images.append({
                'position': idx + 1,
                'missing': missing,
            })

    return jsonify({
        'complete': completed_images == total_images,
        'total_images': total_images,
        'completed_images': completed_images,
        'incomplete_images': incomplete_images,
    })
