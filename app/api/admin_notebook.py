"""API endpoints for Jupyter notebook integration."""

import os
from urllib.parse import urlencode

from flask import current_app, jsonify

from app import db
from app.api import bp
from app.api.decorators import api_admin_required
from app.models import Study
from app.services.notebook_service import (
    export_csv_for_notebook,
    get_or_create_notebook,
    notebook_path,
)


@bp.route('/admin/studies/<int:study_id>/notebook', methods=['POST'])
@api_admin_required
def api_create_notebook(study_id):
    """Create or get the analysis notebook for a study.

    Returns the Jupyter URL to open the notebook.
    """
    if not current_app.config.get('ENABLE_JUPYTER'):
        return jsonify(error='Notebook integration is disabled on this server.'), 503
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    path = get_or_create_notebook(study_id)
    filename = os.path.basename(path)

    # Always refresh the CSV so the notebook has current data
    export_csv_for_notebook(study_id)

    jupyter_token = current_app.config.get('JUPYTER_TOKEN', '')

    url = f'/jupyter/notebooks/{filename}?{urlencode({"token": jupyter_token})}'

    return jsonify({
        'url': url,
        'filename': filename,
        'exists': True,
    })


@bp.route('/admin/studies/<int:study_id>/notebook', methods=['GET'])
@api_admin_required
def api_get_notebook(study_id):
    """Check if a notebook exists for this study."""
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    path = notebook_path(study_id)
    exists = os.path.isfile(path)

    if exists:
        filename = os.path.basename(path)
        jupyter_token = current_app.config.get('JUPYTER_TOKEN', '')
        url = f'/jupyter/notebooks/{filename}?{urlencode({"token": jupyter_token})}'
    else:
        url = None
        filename = None

    return jsonify({
        'enabled': current_app.config.get('ENABLE_JUPYTER', False),
        'url': url,
        'filename': filename,
        'exists': exists,
    })
