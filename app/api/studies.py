"""API endpoints for participant studies: list, image data, submit, protocol PDF."""

import os
import random
from datetime import datetime, timezone

from flask import current_app, jsonify, request, send_from_directory, session, url_for
from flask_login import current_user

from app import db
from app.api import bp
from app.api.decorators import api_participant_required
from app.models import DatasetImage, Study, StudyParticipant, Rating
from app.services.study_lifecycle import check_auto_finish
from app.services.schema_service import (
    get_ordinal_question_ids,
    get_completion_status,
)
from app.services.question_templates import get_question_attribute_names
from app.services.statistics import invalidate_stats_cache
from app.services.xopat import infer_microns, make_study_slide_id


def _get_study_and_user(study_id):
    """Return (study, study_participant) or (None, error_response).

    Test users get auto-created StudyParticipant if needed.
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return None, (jsonify({'error': 'Study not found.'}), 404)

    is_impersonating = session.get('_impersonator_id') is not None
    if not current_user.is_test_user and not is_impersonating and study.status not in ('active', 'finished'):
        return None, (jsonify({'error': 'Study is not active.'}), 403)

    pu = StudyParticipant.query.filter_by(
        study_id=study.id,
        user_id=current_user.id,
    ).first()

    if pu is None:
        if current_user.is_test_user:
            # Auto-create assignment for test users
            pu = StudyParticipant(
                study_id=study.id,
                user_id=current_user.id,
            )
            db.session.add(pu)
            db.session.commit()
        else:
            return None, (jsonify({'error': 'Access denied.'}), 403)

    return (study, pu), None


def _get_shuffled_images(study_id, seed):
    """Return list of DatasetImage objects in randomized order for the given seed."""
    images = DatasetImage.query.filter_by(study_id=study_id).order_by(DatasetImage.id).all()
    rng = random.Random(seed)
    rng.shuffle(images)
    return images


def _get_shuffled_image_ids(study_id, seed):
    """Return list of dataset_image IDs in randomized order (lightweight, no ORM load)."""
    ids = [
        row[0]
        for row in db.session.query(DatasetImage.id)
        .filter_by(study_id=study_id)
        .order_by(DatasetImage.id)
        .all()
    ]
    rng = random.Random(seed)
    rng.shuffle(ids)
    return ids


@bp.route('/studies', methods=['GET'])
@api_participant_required
def api_list_studies():
    """List assigned studies for the current participant with completion info.

    - Regular participants see only active studies they are assigned to.
    - Test users (is_test_user=True) see ALL studies regardless of status.
    - Impersonating admins see ALL studies the participant is assigned to,
      regardless of status, so the admin can review any study state.
    """
    is_impersonating = session.get('_impersonator_id') is not None
    if current_user.is_test_user:
        # Test users see all studies
        studies = Study.query.order_by(Study.name).all()
    elif is_impersonating:
        # Admin reviewing a participant — show all assigned studies regardless of status
        studies = (
            db.session.query(Study)
            .join(StudyParticipant, Study.id == StudyParticipant.study_id)
            .filter(StudyParticipant.user_id == current_user.id)
            .order_by(Study.name)
            .all()
        )
    else:
        studies = (
            db.session.query(Study)
            .join(StudyParticipant, Study.id == StudyParticipant.study_id)
            .filter(
                StudyParticipant.user_id == current_user.id,
                Study.status.in_(['active', 'finished']),
            )
            .order_by(Study.name)
            .all()
        )

    result = []
    for study in studies:
        pu = StudyParticipant.query.filter_by(
            study_id=study.id,
            user_id=current_user.id,
        ).first()

        image_count = DatasetImage.query.filter_by(study_id=study.id).count()

        # Compute completion info
        completed_images = 0
        last_viewed_position = None
        if pu:
            schema = study.rating_schema or {'questions': []}
            ordinal_ids = get_ordinal_question_ids(schema)
            if pu.last_viewed_image_id is not None:
                image_ids = _get_shuffled_image_ids(study.id, pu.random_seed)
                try:
                    last_viewed_position = image_ids.index(pu.last_viewed_image_id) + 1
                except ValueError:
                    last_viewed_position = None

            if ordinal_ids:
                ratings = Rating.query.filter_by(
                    user_id=current_user.id,
                    study_id=study.id,
                ).all()

                for rating in ratings:
                    responses = rating.responses or {}
                    if all(responses.get(qid) is not None for qid in ordinal_ids):
                        completed_images += 1
            else:
                completed_images = image_count

        pct = round(completed_images / image_count * 100) if image_count > 0 else 0

        item = {
            'id': study.id,
            'name': study.name,
            'description': study.description,
            'status': study.status,
            'has_protocol_pdf': bool(study.protocol_pdf_path),
            'uncertainty_enabled': study.uncertainty_enabled,
            'session_instruction': study.session_instruction,
            'rating_schema': study.rating_schema or {'questions': []},
            'default_image_viewer': study.default_image_viewer,
            'completion': {
                'total': image_count,
                'completed': completed_images,
                'pct': pct,
            },
            'last_viewed_position': last_viewed_position,
            'submitted': pu.submitted if pu else False,
            'submitted_at': pu.submitted_at.isoformat() if pu and pu.submitted_at else None,
        }

        result.append(item)

    return jsonify(result)


@bp.route('/studies/<int:study_id>/images', methods=['GET'])
@api_participant_required
def api_image_list(study_id):
    """Return JSON list of images with status for the sidebar.

    Images are returned in the user's randomized order with:
    - position (1-based)
    - dataset_image_id
    - status: not_opened, opened, partial, complete
    - visible_attributes (if configured in schema)
    """
    result, error = _get_study_and_user(study_id)
    if error:
        return error
    study, pu = result

    images = _get_shuffled_images(study.id, pu.random_seed)

    # Get all ratings for this user in this study
    ratings = Rating.query.filter_by(
        user_id=current_user.id,
        study_id=study.id,
    ).all()
    ratings_by_image = {r.dataset_image_id: r for r in ratings}

    schema = study.rating_schema or {'questions': []}
    visible_attr_names = schema.get('visible_attributes', [])

    items = []
    for idx, img in enumerate(images):
        rating = ratings_by_image.get(img.id)

        if rating is None:
            status = 'not_opened'
        else:
            completion = get_completion_status(rating.responses, schema)
            if completion == 'not_started':
                status = 'opened'
            elif completion == 'partial':
                status = 'partial'
            else:
                status = 'complete'

        item = {
            'position': idx + 1,
            'dataset_image_id': img.id,
            'image_name': os.path.basename(img.image_path),
            'status': status,
        }

        if visible_attr_names:
            vis_attrs = {}
            for attr_name in visible_attr_names:
                val = (img.attributes or {}).get(attr_name)
                if val is not None:
                    vis_attrs[attr_name] = val
            if vis_attrs:
                item['visible_attributes'] = vis_attrs

        items.append(item)

    return jsonify(items)


@bp.route('/studies/<int:study_id>/image/<int:position>', methods=['GET'])
@api_participant_required
def api_image_data(study_id, position):
    """Return JSON data for a specific image by position.

    Includes:
    - dataset_image_id
    - image_url (for serving)
    - position
    - current ratings (if any)
    - visible_attributes (if configured in schema)
    """
    result, error = _get_study_and_user(study_id)
    if error:
        return error
    study, pu = result

    # Use lightweight ID-only shuffle instead of loading all ORM objects
    image_ids = _get_shuffled_image_ids(study.id, pu.random_seed)

    if position < 1 or position > len(image_ids):
        return jsonify({'error': 'Image not found.'}), 404

    image_id = image_ids[position - 1]
    img = db.session.get(DatasetImage, image_id)

    track_view = request.args.get('track', '1') != '0'
    is_impersonating = session.get('_impersonator_id') is not None
    needs_commit = False

    if track_view and pu.last_viewed_image_id != img.id and not is_impersonating:
        pu.last_viewed_image_id = img.id
        needs_commit = True

    # Get current rating if exists
    rating = Rating.query.filter_by(
        user_id=current_user.id,
        dataset_image_id=img.id,
    ).first()

    if rating is None and not pu.submitted and not is_impersonating and (
        study.status == 'active' or current_user.is_test_user
    ):
        rating = Rating(
            user_id=current_user.id,
            dataset_image_id=img.id,
            study_id=study.id,
            responses={},
        )
        db.session.add(rating)
        needs_commit = True

    if needs_commit:
        db.session.commit()

    schema = study.rating_schema or {'questions': []}
    visible_attr_names = schema.get('visible_attributes', [])
    question_attr_names = get_question_attribute_names(schema)

    data = {
        'dataset_image_id': img.id,
        'position': position,
        'image_url': url_for('api.api_serve_participant_image', image_path=img.image_path),
        'total_images': len(image_ids),
        'xopat_slide_id': make_study_slide_id(study.id, img.id),
        'xopat_microns': infer_microns(img.attributes),
    }

    if visible_attr_names:
        data['visible_attributes'] = {
            name: (img.attributes or {}).get(name)
            for name in visible_attr_names
            if (img.attributes or {}).get(name) is not None
        }

    if question_attr_names:
        question_attrs = {
            name: (img.attributes or {}).get(name)
            for name in question_attr_names
            if (img.attributes or {}).get(name) is not None
        }
        if question_attrs:
            data['question_attributes'] = question_attrs

    if rating:
        data['rating'] = {
            'id': rating.id,
            'responses': rating.responses,
            'uncertainty': rating.uncertainty,
            'time_spent_seconds': rating.time_spent_seconds,
        }
    else:
        data['rating'] = None

    return jsonify(data)


@bp.route('/studies/<int:study_id>/submit', methods=['POST'])
@api_participant_required
def api_submit(study_id):
    """Submit the evaluation for a study.

    Sets StudyParticipant.submitted=True and submitted_at=now.
    Fails if not all images have all ordinal questions answered.
    """
    if session.get('_impersonator_id'):
        return jsonify({'error': 'Read-only: admin impersonation.'}), 403

    result, error = _get_study_and_user(study_id)
    if error:
        return error
    study, pu = result

    if pu.submitted:
        return jsonify({'error': 'Already submitted.'}), 400

    if not current_user.is_test_user and study.status != 'active':
        return jsonify({'error': 'Study is not active.'}), 403

    schema = study.rating_schema or {'questions': []}
    ordinal_ids = get_ordinal_question_ids(schema)

    # Check completion of all images
    images = DatasetImage.query.filter_by(study_id=study.id).all()
    ratings = Rating.query.filter_by(
        user_id=current_user.id,
        study_id=study.id,
    ).all()
    ratings_by_image = {r.dataset_image_id: r for r in ratings}

    for img in images:
        rating = ratings_by_image.get(img.id)
        responses = rating.responses if rating else {}
        for qid in ordinal_ids:
            if not responses or qid not in responses or responses[qid] is None:
                return jsonify({
                    'error': 'Not all images are complete. Please rate all ordinal questions for every image.',
                }), 400

    pu.submitted = True
    pu.submitted_at = datetime.now(timezone.utc)
    db.session.commit()

    invalidate_stats_cache(study.id)

    check_auto_finish(study)

    return jsonify({'ok': True, 'submitted_at': pu.submitted_at.isoformat()})


@bp.route('/studies/<int:study_id>/protocol-pdf', methods=['GET'])
@api_participant_required
def api_protocol_pdf(study_id):
    """Download the protocol PDF for a study.

    The participant must be assigned to the study (or be a test user).
    """
    result, error = _get_study_and_user(study_id)
    if error:
        return error
    study, _ = result

    if not study.protocol_pdf_path or not os.path.exists(study.protocol_pdf_path):
        return jsonify({'error': 'No protocol PDF available for this study.'}), 404

    directory = os.path.dirname(os.path.abspath(study.protocol_pdf_path))
    filename = os.path.basename(study.protocol_pdf_path)
    return send_from_directory(directory, filename, as_attachment=True)


@bp.route('/studies/images/<path:image_path>', methods=['GET'])
@api_participant_required
def api_serve_participant_image(image_path):
    """Serve an image file from the datasets directory for participant evaluation.

    Authorization: the participant must be able to access at least one
    active/finished study containing this image, or be a test user.
    """
    if not current_user.is_test_user:
        is_impersonating = session.get('_impersonator_id') is not None
        query = (
            db.session.query(DatasetImage.id)
            .join(Study, DatasetImage.study_id == Study.id)
            .join(StudyParticipant, DatasetImage.study_id == StudyParticipant.study_id)
            .filter(
                DatasetImage.image_path == image_path,
                StudyParticipant.user_id == current_user.id,
            )
        )
        if not is_impersonating:
            query = query.filter(Study.status.in_(('active', 'finished')))

        if query.first() is None:
            return jsonify({'error': 'Access denied.'}), 403

    datasets_dir = current_app.config.get('DATASETS_DIR', 'uploads/datasets')
    return send_from_directory(datasets_dir, image_path)
