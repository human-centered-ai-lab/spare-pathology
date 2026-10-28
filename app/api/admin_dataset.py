"""API endpoints for admin dataset management: browse, add, remove, stats."""

from pathlib import Path

from flask import current_app, jsonify, request
from sqlalchemy import asc, desc, func

from app import db
from app.api import bp
from app.api.decorators import api_admin_required
from app.models import DatasetImage, Study, StudyParticipant
from app.services.xopat import infer_microns, make_admin_slide_id


@bp.route('/admin/datasets', methods=['GET'])
@api_admin_required
def api_list_datasets():
    """List available datasets from the filesystem."""
    datasets_dir = current_app.config['DATASETS_DIR']
    from app.services.image_scanner import scan_datasets
    datasets = scan_datasets(datasets_dir)
    return jsonify(datasets)


@bp.route('/admin/datasets/<dataset_name>/images', methods=['GET'])
@api_admin_required
def api_browse_dataset_images(dataset_name):
    """Browse images in a dataset with optional attribute filters and pagination.

    Query params: page, per_page, in_study (study_id to check membership),
    plus any attribute name as filter (e.g. ?mpp_value=0.5&synthetic=true)
    """
    datasets_dir = current_app.config['DATASETS_DIR']

    if not (Path(datasets_dir) / dataset_name).is_dir():
        return jsonify({'error': 'Dataset not found.'}), 404

    from app.services.image_scanner import scan_dataset, parse_value

    images = scan_dataset(datasets_dir, dataset_name)
    if not images:
        return jsonify({'items': [], 'total': 0, 'page': 1, 'per_page': 50, 'total_pages': 1})

    # Apply attribute filters from query params
    skip_keys = {
        'page', 'per_page', 'in_study', 'only_selected', 'exclude_selected', 'all',
    }
    for key, val in request.args.items():
        if key in skip_keys or not val:
            continue
        # Support comma-separated multi-value filters (e.g. mpp_value=0.5,1.0)
        allowed = {parse_value(v) for v in val.split(',')}
        images = [img for img in images if img['attributes'].get(key) in allowed]

    # Check study membership if requested
    study_id = request.args.get('in_study', type=int)
    existing_map = {}
    if study_id is not None:
        existing_map = dict(
            db.session.query(DatasetImage.image_path, DatasetImage.id)
            .filter_by(study_id=study_id)
            .all()
        )

    # Filter to only selected images if requested
    only_selected = request.args.get('only_selected', '').lower() == 'true'
    if only_selected and study_id is not None:
        images = [
            img for img in images
            if f"{dataset_name}/{img['image_name']}" in existing_map
        ]

    # Filter to exclude already-selected images
    exclude_selected = request.args.get('exclude_selected', '').lower() == 'true'
    if exclude_selected and study_id is not None:
        images = [
            img for img in images
            if f"{dataset_name}/{img['image_name']}" not in existing_map
        ]

    # Pagination
    total = len(images)
    return_all = request.args.get('all', '').lower() == 'true'
    if return_all:
        page = 1
        per_page = total or 1
        total_pages = 1
        page_images = images
    else:
        page = max(1, request.args.get('page', 1, type=int))
        per_page = max(1, min(request.args.get('per_page', 50, type=int), 200))
        total_pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        page_images = images[start:start + per_page]

    items = []
    for img in page_images:
        full_path = f"{dataset_name}/{img['image_name']}"
        ds_id = existing_map.get(full_path)
        items.append({
            'image_name': img['image_name'],
            'image_path': full_path,
            'attributes': img['attributes'],
            'in_dataset': ds_id is not None,
            'dataset_image_id': ds_id,
            'missing_file': img.get('missing_file', False),
            'xopat_slide_id': make_admin_slide_id(full_path),
            'xopat_microns': infer_microns(img['attributes']),
        })

    return jsonify({
        'items': items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
    })


@bp.route('/admin/datasets/<dataset_name>/attributes', methods=['GET'])
@api_admin_required
def api_dataset_attributes(dataset_name):
    """Return attribute metadata: names, types, and unique values."""
    datasets_dir = current_app.config['DATASETS_DIR']

    if not (Path(datasets_dir) / dataset_name).is_dir():
        return jsonify({'error': 'Dataset not found.'}), 404

    from app.services.image_scanner import get_attribute_schema
    schema = get_attribute_schema(datasets_dir, dataset_name)
    return jsonify(schema)


@bp.route('/admin/studies/<int:study_id>/dataset/toggle', methods=['POST'])
@api_admin_required
def api_toggle_image(study_id):
    """Toggle a single image in/out of the dataset.

    Request JSON:
        {"image_path": "...", "attributes": {...}}

    If already in dataset -> remove (cascade: clear last_viewed_image_id,
    cascade-delete ratings).
    If not -> add (auto-increment sequence_number, revert submitted users).
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    if study.status != 'draft':
        return jsonify({
            'error': 'Dataset can only be modified when the study is in draft status.',
        }), 403

    data = request.get_json(silent=True) or {}
    image_path = (data.get('image_path') or '').strip()
    if not image_path:
        return jsonify({'error': 'image_path is required.'}), 400

    existing = DatasetImage.query.filter_by(
        study_id=study_id, image_path=image_path,
    ).first()

    if existing:
        # Remove -- same side effects as api_remove_images
        affected_pus = StudyParticipant.query.filter(
            StudyParticipant.study_id == study_id,
            StudyParticipant.last_viewed_image_id == existing.id,
        ).all()
        for pu in affected_pus:
            pu.last_viewed_image_id = None

        # Revert submitted users (image set changed)
        submitted_pus = StudyParticipant.query.filter_by(
            study_id=study_id, submitted=True,
        ).all()
        for pu in submitted_pus:
            pu.submitted = False
            pu.submitted_at = None

        db.session.delete(existing)
        db.session.commit()

        return jsonify({
            'status': 'removed',
            'in_dataset': False,
            'dataset_image_id': None,
        })
    else:
        # Add -- same side effects as api_add_images
        max_seq = (
            db.session.query(db.func.max(DatasetImage.sequence_number))
            .filter_by(study_id=study_id)
            .scalar()
        ) or 0

        di = DatasetImage(
            study_id=study_id,
            image_path=image_path,
            attributes=data.get('attributes', {}),
            sequence_number=max_seq + 1,
        )
        db.session.add(di)

        # Revert submitted users
        submitted_pus = StudyParticipant.query.filter_by(
            study_id=study_id, submitted=True,
        ).all()
        for pu in submitted_pus:
            pu.submitted = False
            pu.submitted_at = None

        db.session.commit()

        return jsonify({
            'status': 'added',
            'in_dataset': True,
            'dataset_image_id': di.id,
        })


@bp.route('/admin/studies/<int:study_id>/dataset/add-bulk', methods=['POST'])
@api_admin_required
def api_add_images_bulk(study_id):
    """Add multiple images to the study dataset at once.

    Request JSON:
        {"images": [{"image_path": "...", "attributes": {...}}, ...]}
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    if study.status != 'draft':
        return jsonify({
            'error': 'Dataset can only be modified when the study is in draft status.',
        }), 403

    data = request.get_json(silent=True) or {}
    images = data.get('images', [])
    if not images:
        return jsonify({'error': 'No images provided.'}), 400

    max_seq = (
        db.session.query(db.func.max(DatasetImage.sequence_number))
        .filter_by(study_id=study_id)
        .scalar()
    ) or 0

    existing_paths = set(
        p for (p,) in db.session.query(DatasetImage.image_path)
        .filter_by(study_id=study_id)
        .all()
    )

    added = 0
    for img_data in images:
        image_path = (img_data.get('image_path') or '').strip()
        if not image_path or image_path in existing_paths:
            continue
        max_seq += 1
        di = DatasetImage(
            study_id=study_id,
            image_path=image_path,
            attributes=img_data.get('attributes', {}),
            sequence_number=max_seq,
        )
        db.session.add(di)
        existing_paths.add(image_path)
        added += 1

    if added > 0:
        submitted_pus = StudyParticipant.query.filter_by(
            study_id=study_id, submitted=True,
        ).all()
        for pu in submitted_pus:
            pu.submitted = False
            pu.submitted_at = None

    db.session.commit()

    return jsonify({'status': 'ok', 'added': added})


@bp.route('/admin/studies/<int:study_id>/dataset/remove', methods=['POST'])
@api_admin_required
def api_remove_images(study_id):
    """Remove images from the study dataset.

    Request JSON:
        {"image_ids": [1, 2, 3]}

    Associated ratings are cascade-deleted via the ORM relationship.
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    if study.status != 'draft':
        return jsonify({
            'error': 'Dataset can only be modified when the study is in draft status.',
        }), 403

    data = request.get_json(silent=True) or {}
    image_ids = data.get('image_ids', [])

    if not image_ids:
        return jsonify({'error': 'No image_ids provided.'}), 400

    # Cascade: clear last_viewed_image_id for users pointing to removed images
    affected_pus = StudyParticipant.query.filter(
        StudyParticipant.study_id == study_id,
        StudyParticipant.last_viewed_image_id.in_(image_ids),
    ).all()
    for pu in affected_pus:
        pu.last_viewed_image_id = None

    removed = 0
    for img_id in image_ids:
        di = db.session.get(DatasetImage, img_id)
        if di and di.study_id == study_id:
            db.session.delete(di)
            removed += 1

    db.session.commit()

    return jsonify({
        'status': 'ok',
        'removed': removed,
    })


@bp.route('/admin/studies/<int:study_id>/dataset/list', methods=['GET'])
@api_admin_required
def api_list_dataset_images(study_id):
    """List images in the study dataset with pagination and sorting.

    Query params:
        page: 1-based page number (default 1)
        per_page: items per page (default 50, max 500)
        sort_by: column to sort by (default sequence_number)
        sort_dir: asc or desc (default asc)

    Returns JSON object with ``items``, ``total``, ``page``, ``per_page``,
    and ``total_pages``.
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    page = max(1, request.args.get('page', 1, type=int))
    per_page = max(1, min(request.args.get('per_page', 50, type=int), 500))

    SORT_COLUMNS = {
        'sequence_number': DatasetImage.sequence_number,
        'image_path': DatasetImage.image_path,
    }
    sort_by = request.args.get('sort_by', 'sequence_number')
    if sort_by.startswith('attr:'):
        attr_name = sort_by[5:]
        sort_col = func.json_extract(DatasetImage.attributes, f'$.{attr_name}')
    else:
        sort_col = SORT_COLUMNS.get(sort_by, DatasetImage.sequence_number)

    sort_dir = request.args.get('sort_dir', 'asc').lower()
    order_fn = desc if sort_dir == 'desc' else asc

    base_query = DatasetImage.query.filter_by(study_id=study_id)
    total = base_query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)

    images = (
        base_query
        .order_by(order_fn(sort_col))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    items = []
    for img in images:
        items.append({
            'id': img.id,
            'image_path': img.image_path,
            'attributes': img.attributes or {},
            'sequence_number': img.sequence_number,
        })

    return jsonify({
        'items': items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
    })


@bp.route('/admin/studies/<int:study_id>/dataset/stats', methods=['GET'])
@api_admin_required
def api_dataset_stats(study_id):
    """Composition statistics with dynamic per-attribute breakdowns.

    Returns:
        {
            "total": int,
            "by_attribute": {"attr_name": {"value1": count, "value2": count}, ...}
        }
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    images = DatasetImage.query.filter_by(study_id=study_id).all()
    total = len(images)

    # Build per-attribute value counts
    by_attribute = {}
    for img in images:
        for key, val in (img.attributes or {}).items():
            if key not in by_attribute:
                by_attribute[key] = {}
            str_val = str(val)
            by_attribute[key][str_val] = by_attribute[key].get(str_val, 0) + 1

    return jsonify({
        'total': total,
        'by_attribute': by_attribute,
    })
