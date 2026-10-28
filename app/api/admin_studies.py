"""API endpoints for admin study management: CRUD, lifecycle, settings, schema, stratification."""

import os
import uuid

from flask import current_app, jsonify, request, send_from_directory
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.utils import secure_filename

from app import db
from app.api import bp
from app.api.decorators import api_admin_required
from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import (
    get_default_rating_schema,
    get_default_pass_fail_config,
    validate_schema,
    validate_pass_fail_config,
)
from app.services.statistics import invalidate_stats_cache

DEFAULT_SESSION_INSTRUCTION = (
    '<h2>Study Instructions</h2>'
    '<p>Welcome to this image evaluation study. Please read the following instructions before you begin.</p>'
    '<p></p>'
    '<h3>Navigation</h3>'
    '<ul>'
    '<li>Use the <strong>left / right arrow keys</strong> or the image list on the left to navigate between images.</li>'
    '<li>In the <strong>image viewer</strong>, use the <strong>mouse wheel</strong> to zoom and <strong>click and drag</strong> to pan around the image.</li>'
    '<li>Each image in the list has a coloured dot indicating its status:<br><strong>gray</strong> = not yet started, <strong>orange</strong> = partially answered, <strong>green</strong> = complete.</li>'
    '</ul>'
    '<p></p>'
    '<h3>Answering Questions</h3>'
    '<ul>'
    '<li>Answer all questions in the rating panel on the right side of the screen.</li>'
    '<li>Use the <strong>number keys (0–9)</strong> to quickly score the focused question, or click the rating buttons directly.</li>'
    '<li>When using keyboard shortcuts, press <strong>Tab</strong> to move focus to the next question.</li>'
    '</ul>'
    '<p></p>'
    '<h3>Saving &amp; Submitting</h3>'
    '<ul>'
    '<li>Your answers are <strong>saved automatically</strong> as you work — you can leave and return at any time without losing progress.</li>'
    '<li>Once you have rated all images, click the <strong>Submit</strong> button to finalise your evaluation.</li>'
    '<li>Submission is permanent and ratings cannot be changed afterwards.</li>'
    '</ul>'
)


def _serialize_study_summary(study):
    """Serialize a study for list views."""
    image_count = DatasetImage.query.filter_by(study_id=study.id).count()
    participant_count = (
        db.session.query(StudyParticipant)
        .join(User)
        .filter(
            StudyParticipant.study_id == study.id,
            User.is_test_user.is_(False),
            User.role == 'participant',
        )
        .count()
    )
    rating_count = Rating.query.filter_by(study_id=study.id).count()
    completed_count = (
        db.session.query(StudyParticipant)
        .join(User)
        .filter(
            StudyParticipant.study_id == study.id,
            User.is_test_user.is_(False),
            User.role == 'participant',
            StudyParticipant.submitted.is_(True),
        )
        .count()
    )
    return {
        'id': study.id,
        'name': study.name,
        'description': study.description,
        'status': study.status,
        'created_at': study.created_at.isoformat(),
        'image_count': image_count,
        'participant_count': participant_count,
        'completed_count': completed_count,
        'rating_count': rating_count,
        'has_pdf': bool(study.protocol_pdf_path),
    }


def _serialize_study_detail(study):
    """Serialize a study with full detail."""
    data = _serialize_study_summary(study)
    data.update({
        'uncertainty_enabled': study.uncertainty_enabled,
        'session_instruction': study.session_instruction,
        'rating_schema': study.rating_schema,
        'pass_fail_config': study.pass_fail_config,
        'dataset_name': study.dataset_name,
        'default_image_viewer': study.default_image_viewer,
        'protocol_pdf_path': study.protocol_pdf_path,
    })
    return data


def _compute_readiness(study):
    """Compute the readiness checklist for a study."""
    schema = study.rating_schema or {}
    questions = schema.get('questions', [])
    has_schema = len(questions) > 0

    image_count = DatasetImage.query.filter_by(study_id=study.id).count()
    has_images = image_count > 0

    non_test_participants = (
        db.session.query(StudyParticipant)
        .join(User)
        .filter(
            StudyParticipant.study_id == study.id,
            User.is_test_user.is_(False),
            User.role == 'participant',
        )
        .count()
    )
    has_participants = non_test_participants > 0

    has_dataset = bool(study.dataset_name)

    return [
        {
            'id': 'schema',
            'label': 'Rating schema has at least one question',
            'ready': has_schema,
        },
        {
            'id': 'dataset_selected',
            'label': 'Dataset selected',
            'ready': has_dataset,
        },
        {
            'id': 'dataset',
            'label': 'At least one image of the dataset was assigned to the study',
            'ready': has_images,
        },
        {
            'id': 'participants',
            'label': 'At least one participant assigned',
            'ready': has_participants,
        },
    ]


def _cascade_schema_update(study, new_schema):
    """Handle cascade effects when schema is updated on an unlocked study.

    If questions were removed, delete those response keys from all existing ratings.
    """
    old_schema = study.rating_schema or {}
    old_question_ids = {q['id'] for q in old_schema.get('questions', [])}
    new_question_ids = {q['id'] for q in new_schema.get('questions', [])}

    removed_ids = old_question_ids - new_question_ids
    if not removed_ids:
        return

    ratings = Rating.query.filter_by(study_id=study.id).all()
    for rating in ratings:
        if not rating.responses:
            continue
        updated = False
        new_responses = dict(rating.responses)
        for qid in removed_ids:
            if qid in new_responses:
                del new_responses[qid]
                updated = True
        if updated:
            rating.responses = new_responses
            flag_modified(rating, 'responses')


# ---------------------------------------------------------------------------
# Study CRUD
# ---------------------------------------------------------------------------

@bp.route('/admin/studies', methods=['GET'])
@api_admin_required
def api_admin_list_studies():
    """List all studies with summary info."""
    studies = Study.query.order_by(Study.name).all()
    return jsonify([_serialize_study_summary(p) for p in studies])


@bp.route('/admin/studies', methods=['POST'])
@api_admin_required
def api_create_study():
    """Create a new study with default schema and stratification.

    Request JSON (optional):
        {"name": "My Study"}
    """
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        name = 'Untitled Study'

    study = Study(
        name=name,
        status='draft',
        rating_schema=get_default_rating_schema(),
        pass_fail_config=get_default_pass_fail_config(),
        session_instruction=DEFAULT_SESSION_INSTRUCTION,
        dataset_name=data.get('dataset_name'),
        default_image_viewer='native',
    )
    db.session.add(study)
    db.session.flush()

    # Auto-assign all test users to the new study
    test_users = User.query.filter_by(is_test_user=True).all()
    for test_user in test_users:
        sp = StudyParticipant(
            study_id=study.id,
            user_id=test_user.id,
        )
        db.session.add(sp)

    db.session.commit()

    return jsonify(_serialize_study_detail(study)), 201


@bp.route('/admin/studies/<int:study_id>', methods=['GET'])
@api_admin_required
def api_get_study(study_id):
    """Get full study detail."""
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    return jsonify(_serialize_study_detail(study))


@bp.route('/admin/studies/<int:study_id>', methods=['DELETE'])
@api_admin_required
def api_delete_study(study_id):
    """Delete a study and cascade to dataset, ratings."""
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    # Remove PDF file if exists
    if study.protocol_pdf_path and os.path.exists(study.protocol_pdf_path):
        try:
            os.remove(study.protocol_pdf_path)
        except OSError:
            pass

    db.session.delete(study)
    db.session.commit()

    return '', 204


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@bp.route('/admin/studies/<int:study_id>/settings', methods=['PUT'])
@api_admin_required
def api_update_settings(study_id):
    """Update study settings: name, description, uncertainty, session_instruction.

    Request JSON:
        {
            "name": "...",
            "description": "...",
            "uncertainty_enabled": true/false,
            "session_instruction": "...",
            "default_image_viewer": "native" | "xopat"
        }
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    data = request.get_json(silent=True) or {}

    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            return jsonify({'error': 'Study name is required.'}), 400
        study.name = name
    if 'description' in data:
        study.description = (data['description'] or '').strip() or None
    if 'uncertainty_enabled' in data:
        study.uncertainty_enabled = bool(data['uncertainty_enabled'])
    if 'session_instruction' in data:
        study.session_instruction = (data['session_instruction'] or '').strip() or None
    if 'default_image_viewer' in data:
        viewer = (data.get('default_image_viewer') or '').strip().lower() or 'native'
        if viewer not in {'native', 'xopat'}:
            return jsonify({'error': 'default_image_viewer must be "native" or "xopat".'}), 400
        study.default_image_viewer = viewer

    if 'dataset_name' in data:
        if study.status != 'draft':
            return jsonify({'error': 'Dataset can only be changed when the study is in draft status.'}), 403
        new_dataset = (data.get('dataset_name') or '').strip() or None
        old_dataset = study.dataset_name

        if new_dataset != old_dataset:
            # Clean up existing images and cascaded ratings when switching datasets
            existing_images = DatasetImage.query.filter_by(study_id=study.id).all()
            if existing_images:
                image_ids = [img.id for img in existing_images]

                # Null out last_viewed_image_id for study participants
                StudyParticipant.query.filter(
                    StudyParticipant.study_id == study.id,
                    StudyParticipant.last_viewed_image_id.in_(image_ids),
                ).update({StudyParticipant.last_viewed_image_id: None}, synchronize_session='fetch')

                # Revert submitted users
                StudyParticipant.query.filter_by(
                    study_id=study.id, submitted=True,
                ).update({
                    'submitted': False,
                    'submitted_at': None,
                }, synchronize_session='fetch')

                # Delete images (cascades to ratings via ORM relationship)
                for img in existing_images:
                    db.session.delete(img)

        study.dataset_name = new_dataset

    db.session.commit()

    return jsonify(_serialize_study_detail(study))


# ---------------------------------------------------------------------------
# PDF upload / download
# ---------------------------------------------------------------------------

@bp.route('/admin/studies/<int:study_id>/upload-pdf', methods=['POST'])
@api_admin_required
def api_upload_pdf(study_id):
    """Upload a protocol PDF for the study (multipart form)."""
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    file = request.files.get('protocol_pdf')
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected.'}), 400

    filename = secure_filename(file.filename)
    if not filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Only PDF files are allowed.'}), 400

    uploads_dir = current_app.config.get('UPLOADS_DIR', 'uploads')
    study_uploads_dir = os.path.join(uploads_dir, 'protocols')
    os.makedirs(study_uploads_dir, exist_ok=True)

    unique_filename = f'{study.id}_{uuid.uuid4().hex[:8]}_{filename}'
    filepath = os.path.join(study_uploads_dir, unique_filename)
    file.save(filepath)

    # Remove old PDF if exists
    if study.protocol_pdf_path and os.path.exists(study.protocol_pdf_path):
        try:
            os.remove(study.protocol_pdf_path)
        except OSError:
            pass

    study.protocol_pdf_path = filepath
    db.session.commit()

    return jsonify({'message': 'Protocol PDF uploaded.', 'path': filepath})


@bp.route('/admin/studies/<int:study_id>/download-pdf', methods=['GET'])
@api_admin_required
def api_download_pdf(study_id):
    """Download the protocol PDF for the study."""
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    if not study.protocol_pdf_path or not os.path.exists(study.protocol_pdf_path):
        return jsonify({'error': 'No protocol PDF available.'}), 404

    directory = os.path.dirname(os.path.abspath(study.protocol_pdf_path))
    filename = os.path.basename(study.protocol_pdf_path)
    return send_from_directory(directory, filename, as_attachment=True)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

@bp.route('/admin/studies/<int:study_id>/schema', methods=['PUT'])
@api_admin_required
def api_update_schema(study_id):
    """Update the rating schema from JSON.

    Request JSON:
        {"schema": {...}}
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    if study.status != 'draft':
        return jsonify({
            'error': 'Schema can only be modified when the study is in draft status.',
        }), 403

    data = request.get_json(silent=True) or {}
    schema = data.get('schema')

    if not isinstance(schema, dict):
        return jsonify({'error': 'Request must include a "schema" key with the schema JSON.'}), 400

    # Strip pass_fail from incoming schema — it's managed separately
    schema.pop('pass_fail', None)

    errors = validate_schema(schema)
    if errors:
        return jsonify({'errors': errors}), 400

    # Cascade: remove deleted question responses from existing ratings
    _cascade_schema_update(study, schema)

    study.rating_schema = schema
    db.session.commit()

    return jsonify({
        'message': 'Rating schema updated.',
        'rating_schema': study.rating_schema,
    })


@bp.route('/admin/studies/<int:study_id>/schema/reset', methods=['POST'])
@api_admin_required
def api_reset_schema(study_id):
    """Reset the rating schema to defaults."""
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    if study.status != 'draft':
        return jsonify({
            'error': 'Schema can only be modified when the study is in draft status.',
        }), 403

    # Cascade: remove deleted question responses from existing ratings
    _cascade_schema_update(study, get_default_rating_schema())

    study.rating_schema = get_default_rating_schema()
    study.pass_fail_config = get_default_pass_fail_config()
    db.session.commit()

    return jsonify({
        'message': 'Rating schema reset to defaults.',
        'rating_schema': study.rating_schema,
        'pass_fail_config': study.pass_fail_config,
    })


# ---------------------------------------------------------------------------
# Pass/Fail Config (editable at any time, no draft restriction)
# ---------------------------------------------------------------------------

@bp.route('/admin/studies/<int:study_id>/pass-fail-config', methods=['PUT'])
@api_admin_required
def api_update_pass_fail_config(study_id):
    """Update the pass/fail configuration. No draft restriction.

    Request JSON:
        {"pass_fail_config": {...}}
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    data = request.get_json(silent=True) or {}
    config = data.get('pass_fail_config')

    if config is None:
        return jsonify({'error': 'Request must include a "pass_fail_config" key.'}), 400

    schema = study.rating_schema or {}
    errors = validate_pass_fail_config(config, schema)
    if errors:
        return jsonify({'errors': errors}), 400

    study.pass_fail_config = config
    invalidate_stats_cache(study.id)
    db.session.commit()

    return jsonify({
        'message': 'Pass/fail configuration updated.',
        'pass_fail_config': study.pass_fail_config,
    })


# ---------------------------------------------------------------------------
# Lifecycle: activate, reopen, auto-finish
# ---------------------------------------------------------------------------

@bp.route('/admin/studies/<int:study_id>/activate', methods=['POST'])
@api_admin_required
def api_activate_study(study_id):
    """Activate a study after validating all requirements are met."""
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    if study.status != 'draft':
        return jsonify({'error': 'Only draft studies can be activated.'}), 400

    readiness = _compute_readiness(study)
    all_ready = all(item['ready'] for item in readiness)

    if not all_ready:
        return jsonify({
            'error': 'Cannot activate study: not all requirements are met.',
            'checklist': readiness,
        }), 400

    study.status = 'active'
    db.session.commit()

    return jsonify({
        'message': f'Study "{study.name}" is now active.',
        'status': study.status,
    })


@bp.route('/admin/studies/<int:study_id>/reopen', methods=['POST'])
@api_admin_required
def api_reopen_study(study_id):
    """Revert an active study to draft, deleting all evaluation data.

    This is a full rollback: all ratings are deleted, participant submission
    state is reset, and the study returns to draft for editing.
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    if study.status == 'finished':
        return jsonify({'error': 'Finished studies cannot be reverted to draft.'}), 400

    if study.status != 'active':
        return jsonify({'error': 'Only active studies can be reverted to draft.'}), 400

    # Delete all ratings for this study
    deleted_count = Rating.query.filter_by(study_id=study.id).delete()

    # Reset all participant state
    StudyParticipant.query.filter_by(study_id=study.id).update({
        'submitted': False,
        'submitted_at': None,
        'last_viewed_image_id': None,
    }, synchronize_session='fetch')

    study.status = 'draft'
    invalidate_stats_cache(study.id)
    db.session.commit()

    return jsonify({
        'message': f'Study reverted to draft. {deleted_count} rating(s) deleted.',
        'status': study.status,
        'deleted_ratings': deleted_count,
    })


@bp.route('/admin/studies/<int:study_id>/readiness', methods=['GET'])
@api_admin_required
def api_readiness_checklist(study_id):
    """Return JSON readiness checklist for the study."""
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    readiness = _compute_readiness(study)
    return jsonify({
        'study_id': study.id,
        'status': study.status,
        'checklist': readiness,
        'all_ready': all(item['ready'] for item in readiness),
    })
