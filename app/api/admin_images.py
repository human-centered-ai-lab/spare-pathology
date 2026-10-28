"""API endpoints for admin image management: upload, overview, deletion."""

import os
import re
import shutil
import fcntl
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

from flask import abort, current_app, jsonify, request, send_file, send_from_directory
from flask_login import current_user
from PIL import Image, ImageOps
from werkzeug.utils import safe_join

from app.api import bp
from app.api.decorators import api_admin_required
from app.models import Study
from app.services.image_scanner import scan_datasets

_THUMBNAIL_SIZE = (512, 512)
_THUMBNAIL_MAX_AGE_SECONDS = 3600

def _sanitize_dataset_name(name: str) -> str:
    """Make a dataset name safe for use as a folder name.

    Lowercases, replaces spaces/hyphens with underscores, strips non-alphanum
    characters (except underscores), and collapses consecutive underscores.
    """
    s = name.strip().lower()
    s = s.replace(' ', '_').replace('-', '_')
    s = re.sub(r'[^a-z0-9_]', '', s)
    s = re.sub(r'_+', '_', s)
    s = s.strip('_')
    return s or 'dataset'


@contextmanager
def _upload_session(upload_id):
    """Lock persistent upload state across application workers and restarts."""
    if not isinstance(upload_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', upload_id):
        abort(400, description='Invalid upload_id.')
    root = Path(current_app.config['DATASETS_DIR']).parent / '.uploads'
    root.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f'{current_user.id}:{upload_id}'.encode()).hexdigest()
    with (root / f'{key}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        directory = root / key
        directory.mkdir(exist_ok=True)
        metadata = directory / 'session.json'
        state = json.loads(metadata.read_text()) if metadata.exists() else {}
        yield directory, state
        if directory.exists():
            temp = directory / 'session.json.tmp'
            temp.write_text(json.dumps(state), encoding='utf-8')
            temp.replace(metadata)


@bp.route('/admin/images/datasets-overview', methods=['GET'])
@api_admin_required
def api_datasets_overview():
    """Return summary info for every dataset in the datasets directory."""
    datasets_dir = current_app.config['DATASETS_DIR']
    datasets = scan_datasets(datasets_dir)
    result = []
    for d in datasets:
        # Check if any study references this dataset
        ref_count = Study.query.filter_by(dataset_name=d['name']).count()
        result.append({
            'dataset_name': d['name'],
            'image_count': d['image_count'],
            'attribute_names': d['attribute_names'],
            'referenced_by_studies': ref_count,
        })
    return jsonify(result)


@bp.route('/admin/images/check-dataset-name', methods=['POST'])
@api_admin_required
def api_check_dataset_name():
    """Check if a dataset name already exists in the datasets directory.

    Request JSON:
        {"dataset_name": "..."}
    """
    data = request.get_json(silent=True) or {}
    raw_name = data.get('dataset_name', '').strip()

    if not raw_name:
        return jsonify({'error': 'Dataset name is required.'}), 400

    dataset_name = _sanitize_dataset_name(raw_name)
    datasets_dir = current_app.config['DATASETS_DIR']
    dataset_path = os.path.join(datasets_dir, dataset_name)
    exists = os.path.isdir(dataset_path)

    return jsonify({
        'exists': exists,
        'dataset_name': dataset_name,
    })


@bp.route('/admin/images/upload-chunk', methods=['POST'])
@api_admin_required
def api_upload_chunk():
    """Receive a single file chunk for an ongoing upload.

    Expected form fields (multipart):
        upload_id: unique upload session identifier
        dataset_name: target dataset name
        file_path: relative path within the dataset folder
        chunk_index: 0-based index of this chunk
        total_chunks: total number of chunks for this file
        chunk: the binary file data (as file upload)
    """
    upload_id = request.form.get('upload_id', '').strip()
    dataset_name = _sanitize_dataset_name(
        request.form.get('dataset_name', ''),
    )
    file_path = request.form.get('file_path', '').strip()
    chunk_index = request.form.get('chunk_index', '')
    total_chunks = request.form.get('total_chunks', '')
    chunk = request.files.get('chunk')

    if not all([upload_id, dataset_name, file_path, chunk_index is not None, chunk]):
        return jsonify({'error': 'Missing required fields.'}), 400

    try:
        chunk_index = int(chunk_index)
        total_chunks = int(total_chunks)
    except (ValueError, TypeError):
        return jsonify({'error': 'chunk_index and total_chunks must be integers.'}), 400

    relative = Path(file_path)
    if (relative.is_absolute() or '..' in relative.parts or '\\' in file_path
            or '\x00' in file_path or file_path in ('', '.')
            or file_path != relative.as_posix()):
        return jsonify({'error': 'Invalid file path.'}), 400
    if not 0 <= chunk_index < total_chunks <= 100000:
        return jsonify({'error': 'Invalid chunk index or total.'}), 400

    dataset_path = Path(current_app.config['DATASETS_DIR']) / dataset_name
    if dataset_path.exists():
        return jsonify({'error': f'Dataset "{dataset_name}" already exists.'}), 409

    with _upload_session(upload_id) as (directory, state):
        if state and state['dataset_name'] != dataset_name:
            return jsonify({'error': 'Upload belongs to a different dataset.'}), 409
        state.setdefault('dataset_name', dataset_name)
        files = state.setdefault('files', {})
        info = files.setdefault(file_path, {'total_chunks': total_chunks, 'received_chunks': []})
        if info['total_chunks'] != total_chunks:
            return jsonify({'error': 'Chunk count changed during upload.'}), 409
        chunk_dir = directory / 'chunks' / file_path
        chunk_dir.mkdir(parents=True, exist_ok=True)
        chunk_path = chunk_dir / f'chunk_{chunk_index:06d}'
        temporary = chunk_path.with_suffix('.tmp')
        chunk.save(temporary)
        temporary.replace(chunk_path)
        if chunk_index not in info['received_chunks']:
            info['received_chunks'].append(chunk_index)
        received = len(info['received_chunks'])

    return jsonify({
        'status': 'ok',
        'file_path': file_path,
        'chunk_index': chunk_index,
        'received': received,
        'total': total_chunks,
    })


@bp.route('/admin/images/upload-complete', methods=['POST'])
@api_admin_required
def api_upload_complete():
    """Finalize an upload: assemble chunks into the dataset folder.

    Request JSON:
        {"upload_id": "...", "dataset_name": "..."}
    """
    data = request.get_json(silent=True) or {}
    upload_id = data.get('upload_id', '').strip()
    dataset_name = _sanitize_dataset_name(data.get('dataset_name', ''))

    if not upload_id or not dataset_name:
        return jsonify({'error': 'upload_id and dataset_name are required.'}), 400

    with _upload_session(upload_id) as (directory, state):
        if not state:
            return jsonify({'error': 'Upload session not found.'}), 404
        if state['dataset_name'] != dataset_name:
            return jsonify({'error': 'Upload belongs to a different dataset.'}), 409
        if not state['files'] or any(
            len(info['received_chunks']) != info['total_chunks']
            for info in state['files'].values()
        ):
            return jsonify({'error': 'Upload is incomplete. Send the missing chunks and retry.'}), 409

        dataset_path = Path(current_app.config['DATASETS_DIR']) / dataset_name
        if dataset_path.exists():
            return jsonify({'error': f'Dataset "{dataset_name}" already exists.'}), 409

        assembled = directory / 'assembled'
        try:
            for file_path, info in state['files'].items():
                dest = assembled / file_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open('wb') as output:
                    for i in range(info['total_chunks']):
                        chunk_path = directory / 'chunks' / file_path / f'chunk_{i:06d}'
                        with chunk_path.open('rb') as source:
                            shutil.copyfileobj(source, output)
            validation = _validate_dataset(str(assembled))
            # Publish only fully assembled files, on the same filesystem.
            assembled.rename(dataset_path)
        except FileExistsError:
            return jsonify({'error': f'Dataset "{dataset_name}" already exists.'}), 409
        except OSError:
            current_app.logger.exception('Failed to assemble upload %s', upload_id)
            return jsonify({'error': 'Failed to assemble uploaded files. Please retry.'}), 500
        shutil.rmtree(directory)

    return jsonify({
        'status': 'ok',
        'dataset_name': dataset_name,
        'validation': validation,
    })


@bp.route('/admin/images/delete-dataset', methods=['POST'])
@api_admin_required
def api_delete_dataset():
    """Delete a dataset directory. Blocked if any study references it.

    Request JSON:
        {"dataset_name": "..."}
    """
    data = request.get_json(silent=True) or {}
    dataset_name = data.get('dataset_name', '').strip()

    if not dataset_name:
        return jsonify({'error': 'dataset_name is required.'}), 400

    # Reject path traversal attempts
    if '..' in dataset_name or '/' in dataset_name or '\\' in dataset_name or dataset_name.startswith('.'):
        return jsonify({'error': 'Invalid dataset name.'}), 400

    datasets_dir = current_app.config['DATASETS_DIR']
    dataset_path = os.path.join(datasets_dir, dataset_name)

    # Verify resolved path is under DATASETS_DIR
    real_dataset_path = os.path.realpath(dataset_path)
    real_datasets_dir = os.path.realpath(datasets_dir)
    if not real_dataset_path.startswith(real_datasets_dir + os.sep):
        return jsonify({'error': 'Invalid dataset name.'}), 400

    if not os.path.isdir(dataset_path):
        return jsonify({'error': f'Dataset "{dataset_name}" not found.'}), 404

    # Check if any studies reference this dataset
    referencing_studies = (
        Study.query
        .filter_by(dataset_name=dataset_name)
        .all()
    )
    if referencing_studies:
        study_names = [s.name for s in referencing_studies]
        return jsonify({
            'error': 'Cannot delete dataset -- it is referenced by studies.',
            'studies': study_names,
        }), 409

    # Delete the directory
    shutil.rmtree(dataset_path)

    return jsonify({'status': 'ok', 'dataset_name': dataset_name})


@bp.route('/admin/images/serve/<path:image_path>')
@api_admin_required
def api_serve_admin_image(image_path):
    """Serve an image file from the datasets directory for admin preview."""
    datasets_dir = current_app.config.get('DATASETS_DIR', 'uploads/datasets')
    return send_from_directory(datasets_dir, image_path)


def _resolve_admin_source_path(image_path: str) -> Path:
    """Resolve an admin dataset image path safely under DATASETS_DIR."""
    datasets_dir = current_app.config.get('DATASETS_DIR', 'uploads/datasets')
    resolved = safe_join(datasets_dir, image_path)
    if resolved is None:
        abort(404)

    source_path = Path(resolved)
    if not source_path.resolve().is_relative_to(Path(datasets_dir).resolve()):
        abort(404)
    if not source_path.is_file():
        abort(404)

    return source_path


def _thumbnail_cache_path(image_path: str, source_path: Path) -> Path:
    """Return the cached thumbnail path for a dataset image."""
    cache_root = Path(current_app.instance_path) / 'thumb_cache' / 'admin' / '512'
    relative = Path(image_path)
    suffix = source_path.suffix.lower()
    cache_suffix = '.png' if suffix in {'.png', '.webp'} else '.jpg'
    return cache_root / relative.parent / (relative.name + cache_suffix)


def _write_thumbnail(source_path: Path, cache_path: Path) -> None:
    """Generate and persist a 512x512 thumbnail for an image."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail(_THUMBNAIL_SIZE, Image.Resampling.LANCZOS)

        if cache_path.suffix.lower() == '.png':
            image.save(cache_path, format='PNG', optimize=True)
            return

        if image.mode not in {'RGB', 'L'}:
            image = image.convert('RGB')
        image.save(cache_path, format='JPEG', quality=85, optimize=True)


@bp.route('/admin/images/thumb/<path:image_path>')
@api_admin_required
def api_serve_admin_thumbnail(image_path):
    """Serve a cached 512x512 thumbnail for an admin dataset image."""
    source_path = _resolve_admin_source_path(image_path)
    cache_path = _thumbnail_cache_path(image_path, source_path)

    regenerate = (
        not cache_path.exists() or
        cache_path.stat().st_mtime < source_path.stat().st_mtime
    )
    if regenerate:
        try:
            _write_thumbnail(source_path, cache_path)
        except OSError:
            abort(404)

    response = send_file(cache_path, conditional=True, max_age=_THUMBNAIL_MAX_AGE_SECONDS)
    response.cache_control.public = False
    response.cache_control.private = True
    response.cache_control.no_cache = False
    return response


_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'}


def _validate_dataset(dataset_path: str) -> dict:
    """Validate a dataset directory after upload.

    Checks:
    - metadata.csv exists
    - metadata.csv has an 'image_name' column
    - Referenced image files exist on disk (with or without extension)
    - All image files on disk are referenced in metadata.csv
    """
    import csv
    from pathlib import Path
    from app.services.image_scanner import resolve_image_name

    errors = []
    csv_path = os.path.join(dataset_path, 'metadata.csv')

    if not os.path.isfile(csv_path):
        return {
            'valid': False,
            'errors': ['No metadata.csv found in dataset.'],
        }

    ds_path = Path(dataset_path)

    try:
        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []

            if 'image_name' not in fieldnames:
                errors.append(
                    'metadata.csv is missing the required "image_name" column.'
                )
                return {'valid': False, 'errors': errors}

            row_count = 0
            missing_files = []
            referenced_files = set()
            for row in reader:
                row_count += 1
                image_name = (row.get('image_name') or '').strip()
                if not image_name:
                    continue
                resolved = resolve_image_name(ds_path, image_name)
                if resolved is None:
                    missing_files.append(image_name)
                else:
                    referenced_files.add(resolved)

            if row_count == 0:
                errors.append('metadata.csv contains no data rows.')

            if missing_files:
                sample = missing_files[:5]
                suffix = (
                    f' and {len(missing_files) - 5} more'
                    if len(missing_files) > 5
                    else ''
                )
                errors.append(
                    f'{len(missing_files)} image(s) referenced in metadata.csv '
                    f'not found: {", ".join(sample)}{suffix}'
                )

            # Check for image files on disk not referenced in metadata.csv
            all_image_files = {
                f.relative_to(ds_path).as_posix() for f in ds_path.rglob('*')
                if f.is_file() and f.suffix.lower() in _IMAGE_EXTENSIONS
            }
            unreferenced = sorted(all_image_files - referenced_files)
            if unreferenced:
                sample = unreferenced[:5]
                suffix = (
                    f' and {len(unreferenced) - 5} more'
                    if len(unreferenced) > 5
                    else ''
                )
                errors.append(
                    f'{len(unreferenced)} image(s) on disk not referenced in '
                    f'metadata.csv: {", ".join(sample)}{suffix}'
                )
    except Exception as exc:
        errors.append(f'Failed to parse metadata.csv: {exc}')

    return {
        'valid': len(errors) == 0,
        'errors': errors,
    }
