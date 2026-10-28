"""API endpoints for admin evaluation: statistics data, status overview, filter options."""

from flask import current_app, jsonify, request

from app import db
from app.api import bp
from app.api.decorators import api_admin_required
from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import get_completion_status, get_default_rating_schema


@bp.route('/admin/studies/<int:study_id>/evaluation/data', methods=['GET'])
@api_admin_required
def api_evaluation_data(study_id):
    """Return all computed statistics as JSON, with optional filters.

    Query parameters (all optional):
        submitted_only: '1' or '0' (default '1')
        user_ids: comma-separated list of user IDs
        group_by: attribute name to group by
        <attr_name>: any other param is treated as an attribute filter
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    filters = _parse_filters(request.args)

    schema = study.rating_schema
    if not schema:
        schema = get_default_rating_schema()

    pass_fail_config = study.pass_fail_config

    from app.services.statistics import compute_all

    try:
        result = compute_all(study_id, filters=filters, schema=schema, pass_fail_config=pass_fail_config)
    except Exception:
        current_app.logger.exception(f"Statistics computation failed for study {study_id}")
        return jsonify({'error': 'Statistics computation failed.'}), 500

    return jsonify(result)


@bp.route('/admin/studies/<int:study_id>/evaluation/status', methods=['GET'])
@api_admin_required
def api_evaluation_status(study_id):
    """Return user status overview as JSON.

    Returns counts of submitted / in_progress / not_started,
    plus per-user details.
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    # Get all non-test study participants
    study_participants = (
        db.session.query(StudyParticipant, User)
        .join(User, StudyParticipant.user_id == User.id)
        .filter(
            StudyParticipant.study_id == study_id,
            User.is_test_user.is_(False),
        )
        .all()
    )

    schema = study.rating_schema or get_default_rating_schema()
    total_images = db.session.query(db.func.count(DatasetImage.id)).filter_by(
        study_id=study_id,
    ).scalar()

    # Batch-load all ratings for non-submitted users in one query
    non_submitted_user_ids = [
        user.id for pu, user in study_participants if not pu.submitted
    ]
    ratings_by_user: dict[int, list] = {uid: [] for uid in non_submitted_user_ids}
    if non_submitted_user_ids:
        all_ratings = Rating.query.filter(
            Rating.study_id == study_id,
            Rating.user_id.in_(non_submitted_user_ids),
        ).all()
        for r in all_ratings:
            ratings_by_user[r.user_id].append(r)

    submitted_count = 0
    in_progress_count = 0
    not_started_count = 0
    users_detail = []

    for pu, user in study_participants:
        if pu.submitted:
            status_key = 'submitted'
            submitted_count += 1
        else:
            user_ratings = ratings_by_user.get(user.id, [])
            if not user_ratings:
                status_key = 'not_started'
                not_started_count += 1
            else:
                has_any_response = any(
                    get_completion_status(r.responses, schema) != 'not_started'
                    for r in user_ratings
                )
                if has_any_response:
                    status_key = 'in_progress'
                    in_progress_count += 1
                else:
                    status_key = 'not_started'
                    not_started_count += 1

        users_detail.append({
            'user_id': user.id,
            'name': f'{user.first_name} {user.last_name}',
            'email': user.email,
            'institution': user.institution,
            'status': status_key,
            'submitted_at': pu.submitted_at.isoformat() if pu.submitted_at else None,
        })

    return jsonify({
        'total_users': len(study_participants),
        'total_images': total_images,
        'submitted': submitted_count,
        'in_progress': in_progress_count,
        'not_started': not_started_count,
        'users': users_detail,
    })


@bp.route('/admin/studies/<int:study_id>/evaluation/filter-options', methods=['GET'])
@api_admin_required
def api_evaluation_filter_options(study_id):
    """Return available filter options derived from dataset image attributes."""
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    images = DatasetImage.query.filter_by(study_id=study_id).all()

    # Collect unique values per attribute
    attr_values = {}
    for img in images:
        for key, val in (img.attributes or {}).items():
            if key not in attr_values:
                attr_values[key] = set()
            attr_values[key].add(val)

    attributes = []
    for key in sorted(attr_values.keys()):
        values = attr_values[key]
        # Detect type
        if all(isinstance(v, bool) for v in values):
            attr_type = 'boolean'
        elif all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
            attr_type = 'numeric'
        else:
            attr_type = 'string'

        sorted_vals = sorted(values, key=lambda x: (isinstance(x, str), str(x)))
        attributes.append({
            'name': key,
            'type': attr_type,
            'values': sorted_vals,
        })

    # Users list
    users = (
        db.session.query(User)
        .join(StudyParticipant, StudyParticipant.user_id == User.id)
        .filter(StudyParticipant.study_id == study_id, User.is_test_user.is_(False))
        .order_by(User.last_name, User.first_name)
        .all()
    )
    user_list = [{'id': u.id, 'name': f'{u.first_name} {u.last_name}', 'institution': u.institution} for u in users]

    return jsonify({'attributes': attributes, 'users': user_list})


def _parse_filters(args):
    """Parse query string arguments into a filters dict for the statistics engine."""
    filters = {}

    submitted_only = args.get('submitted_only', '1')
    filters['submitted_only'] = submitted_only in ('1', 'true', 'yes')

    user_ids = args.get('user_ids')
    if user_ids and user_ids.strip():
        try:
            filters['user_ids'] = [int(uid) for uid in user_ids.split(',') if uid.strip()]
        except (ValueError, TypeError):
            pass

    group_by = args.get('group_by')
    if group_by and group_by.strip():
        filters['group_by'] = group_by.strip()

    # All other params are attribute filters (supports comma-separated multi-values)
    skip_keys = {'submitted_only', 'user_ids', 'group_by'}
    attr_filters = {}
    for key, val in args.items():
        if key in skip_keys or not val:
            continue
        # Split on comma for multi-value support
        parts = [v.strip() for v in val.split(',') if v.strip()]
        parsed = set()
        for part in parts:
            lower = part.lower()
            if lower in ('true', 'false'):
                parsed.add(lower == 'true')
            else:
                try:
                    parsed.add(float(part))
                except (ValueError, TypeError):
                    parsed.add(part)
        if parsed:
            attr_filters[key] = sorted(parsed, key=lambda x: (type(x).__name__, str(x)))

    if attr_filters:
        filters['attributes'] = attr_filters

    return filters
