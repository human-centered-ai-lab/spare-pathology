"""API endpoints for admin CSV export: download and completion check."""

from flask import Response, jsonify

from app import db
from app.api import bp
from app.api.decorators import api_admin_required
from app.models import Study
from app.services.export_service import generate_csv, get_export_status


@bp.route('/admin/studies/<int:study_id>/export', methods=['GET'])
@api_admin_required
def api_export_csv(study_id):
    """Download all ratings for a study as a CSV file.

    Returns a CSV file with Content-Disposition: attachment.
    Test users are excluded from the export.
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    csv_string, is_complete, warning = generate_csv(study_id)

    filename = f'study_{study_id}_ratings.csv'

    response = Response(
        csv_string,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
        },
    )
    return response


@bp.route('/admin/studies/<int:study_id>/export/check', methods=['GET'])
@api_admin_required
def api_export_check(study_id):
    """Check completion status before export.

    Returns JSON with:
    - complete: bool
    - warning: str or null
    - total_users: int
    - submitted_users: int
    """
    study = db.session.get(Study, study_id)
    if study is None:
        return jsonify({'error': 'Study not found.'}), 404

    status = get_export_status(study_id)
    return jsonify(status)
