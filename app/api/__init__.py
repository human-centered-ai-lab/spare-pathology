from urllib.parse import urlsplit

from flask import Blueprint, jsonify, request, session
from flask_login import login_user

bp = Blueprint('api', __name__, url_prefix='/api')


@bp.before_request
def validate_request():
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        origin = request.headers.get('Origin')
        if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (
            origin and urlsplit(origin).netloc != request.host
        ):
            return jsonify(error='Cross-origin requests are not allowed.'), 403
        if request.is_json and not isinstance(request.get_json(silent=True), dict):
            return jsonify(error='A JSON object is required.'), 400

# Endpoints that are allowed while impersonating (read-only evaluation views)
_IMPERSONATION_ALLOWED_ENDPOINTS = {
    'api.api_me',
    'api.api_list_studies',
    'api.api_image_list',
    'api.api_image_data',
    'api.api_serve_participant_image',
    'api.api_protocol_pdf',
    'api.completion_status',
    'api.api_unimpersonate',
    'api.api_xopat_proxy',
    'api.api_xopat_participant_dzi',
    'api.api_xopat_participant_tile',
}


@bp.before_request
def _auto_unimpersonate():
    """If the admin navigates away from evaluation endpoints while
    impersonating, silently restore the admin session."""
    impersonator_id = session.get('_impersonator_id')
    if impersonator_id is None:
        return

    if request.endpoint in _IMPERSONATION_ALLOWED_ENDPOINTS:
        return

    from app.models import User
    from app import db

    admin = db.session.get(User, impersonator_id)
    if admin is not None:
        session.pop('_impersonator_id', None)
        login_user(admin)


from app.api import auth  # noqa: E402, F401
from app.api import admin_users  # noqa: E402, F401
from app.api import ratings  # noqa: E402, F401
from app.api import admin_studies  # noqa: E402, F401
from app.api import admin_dataset  # noqa: E402, F401
from app.api import admin_participants  # noqa: E402, F401
from app.api import admin_images  # noqa: E402, F401
from app.api import admin_evaluation  # noqa: E402, F401
from app.api import admin_export  # noqa: E402, F401
from app.api import admin_notebook  # noqa: E402, F401
from app.api import studies  # noqa: E402, F401
from app.api import xopat  # noqa: E402, F401
