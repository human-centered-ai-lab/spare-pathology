"""Proxy XOpat viewer assets and serve authenticated Deep Zoom tiles."""

from __future__ import annotations

import urllib.error
import urllib.request
from io import BytesIO

from flask import Response, abort, current_app, jsonify, make_response, request, session
from flask_login import current_user

from app import db
from app.api import bp
from app.api.decorators import api_login_required
from app.models import DatasetImage, Study, StudyParticipant
from app.services.xopat import (
    decode_slide_id,
    get_deepzoom_generator,
    resolve_dataset_file_path,
    xopat_is_available,
)


def _tile_settings() -> dict[str, int | bool]:
    return {
        'tile_size': 254,
        'overlap': 1,
        'limit_bounds': True,
    }


def _resolve_participant_slide(slide_id: str) -> tuple[str, DatasetImage]:
    payload = decode_slide_id(slide_id)
    if payload.get('kind') != 'study_image':
        raise ValueError('Unsupported participant slide identifier.')

    try:
        study_id = int(payload.get('study_id'))
        dataset_image_id = int(payload.get('dataset_image_id'))
    except (ValueError, TypeError) as exc:
        raise ValueError('Invalid study image identifier.') from exc
    img = db.session.get(DatasetImage, dataset_image_id)
    if img is None or img.study_id != study_id:
        raise FileNotFoundError('Study image not found.')

    query = (
        db.session.query(DatasetImage.id)
        .join(Study, DatasetImage.study_id == Study.id)
        .join(StudyParticipant, DatasetImage.study_id == StudyParticipant.study_id)
        .filter(
            DatasetImage.id == dataset_image_id,
            StudyParticipant.user_id == current_user.id,
        )
    )

    is_impersonating = session.get('_impersonator_id') is not None
    if not current_user.is_test_user and not is_impersonating:
        query = query.filter(Study.status.in_(('active', 'finished')))

    if not current_user.is_test_user and query.first() is None:
        abort(403)

    datasets_dir = current_app.config['DATASETS_DIR']
    return resolve_dataset_file_path(datasets_dir, img.image_path), img


def _resolve_admin_slide(slide_id: str) -> str:
    payload = decode_slide_id(slide_id)
    if payload.get('kind') != 'admin_dataset':
        raise ValueError('Unsupported admin slide identifier.')

    image_path = str(payload.get('image_path') or '').strip()
    if not image_path:
        raise ValueError('Missing admin slide path.')

    datasets_dir = current_app.config['DATASETS_DIR']
    return resolve_dataset_file_path(datasets_dir, image_path)


def _render_dzi(slide_id: str, file_path: str) -> Response:
    settings = _tile_settings()
    generator = get_deepzoom_generator(slide_id, file_path, **settings)
    response = make_response(generator.get_dzi('png'))
    response.mimetype = 'application/xml'
    return response


def _render_tile(slide_id: str, file_path: str, level: int, col: int, row: int, image_format: str) -> Response:
    image_format = image_format.lower()
    if image_format not in {'png', 'jpeg', 'jpg'}:
        abort(404)

    settings = _tile_settings()
    generator = get_deepzoom_generator(slide_id, file_path, **settings)
    try:
        tile = generator.get_tile(level, (col, row))
    except (KeyError, ValueError):
        abort(404)

    save_format = 'PNG' if image_format == 'png' else 'JPEG'
    buffer = BytesIO()
    save_kwargs = {}
    if save_format == 'JPEG':
        save_kwargs['quality'] = 90
    tile.save(buffer, save_format, **save_kwargs)
    response = make_response(buffer.getvalue())
    response.mimetype = f'image/{image_format if image_format != "jpg" else "jpeg"}'
    response.headers['Cache-Control'] = 'private, max-age=3600'
    return response


def _proxy_xopat_request(proxy_path: str = '') -> Response:
    if not xopat_is_available(current_app.config.get('XOPAT_DIR')):
        return jsonify({'error': 'XOpat is not configured on this server.'}), 503

    base_url = current_app.config['XOPAT_SERVER_URL'].rstrip('/')
    target = f'{base_url}/{proxy_path.lstrip("/")}'
    if request.query_string:
        target = f'{target}?{request.query_string.decode("utf-8")}'

    data = None
    if request.method not in {'GET', 'HEAD'}:
        data = request.get_data()

    proxied = urllib.request.Request(
        target,
        data=data,
        method=request.method,
    )
    for header in ('Content-Type', 'Accept'):
        value = request.headers.get(header)
        if value:
            proxied.add_header(header, value)

    try:
        with urllib.request.urlopen(proxied, timeout=10) as upstream:
            body = upstream.read()
            response = make_response(body, upstream.status)
            for header, value in upstream.headers.items():
                key = header.lower()
                if key in {'connection', 'content-length', 'transfer-encoding', 'content-encoding'}:
                    continue
                response.headers[header] = value
            return response
    except urllib.error.HTTPError as exc:
        body = exc.read()
        response = make_response(body, exc.code)
        content_type = exc.headers.get('Content-Type')
        if content_type:
            response.headers['Content-Type'] = content_type
        return response
    except urllib.error.URLError:
        return jsonify({
            'error': 'XOpat viewer service is unavailable. Start the XOpat server and try again.',
        }), 503


@bp.route('/xopat/slides/<slide_id>.dzi', methods=['GET'])
@api_login_required
def api_xopat_participant_dzi(slide_id):
    try:
        payload = decode_slide_id(slide_id)
        kind = payload.get('kind')
        if kind == 'admin_dataset':
            if current_user.role != 'admin':
                abort(403)
            file_path = _resolve_admin_slide(slide_id)
        elif kind == 'study_image':
            file_path, _ = _resolve_participant_slide(slide_id)
        else:
            abort(404)
        return _render_dzi(slide_id, file_path)
    except FileNotFoundError:
        abort(404)
    except ValueError:
        abort(404)


@bp.route('/xopat/slides/<slide_id>_files/<int:level>/<int:col>_<int:row>.<image_format>', methods=['GET'])
@api_login_required
def api_xopat_participant_tile(slide_id, level, col, row, image_format):
    try:
        payload = decode_slide_id(slide_id)
        kind = payload.get('kind')
        if kind == 'admin_dataset':
            if current_user.role != 'admin':
                abort(403)
            file_path = _resolve_admin_slide(slide_id)
        elif kind == 'study_image':
            file_path, _ = _resolve_participant_slide(slide_id)
        else:
            abort(404)
        return _render_tile(slide_id, file_path, level, col, row, image_format)
    except FileNotFoundError:
        abort(404)
    except ValueError:
        abort(404)


@bp.route(
    '/xopat',
    defaults={'proxy_path': ''},
    methods=['GET', 'POST'],
    strict_slashes=False,
)
@bp.route('/xopat/<path:proxy_path>', methods=['GET', 'POST'], strict_slashes=False)
@api_login_required
def api_xopat_proxy(proxy_path):
    return _proxy_xopat_request(proxy_path)
