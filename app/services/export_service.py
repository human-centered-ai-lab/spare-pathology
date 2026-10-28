"""Service for exporting study ratings as CSV.

Provides generate_csv() which returns a CSV string with all ratings
for a study, excluding test users, with computed scores.
"""

import csv
import io

from app import db
from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import (
    compute_pass_fail,
    compute_total_score,
)


def _sanitize_csv_value(value):
    """Sanitize a value to prevent CSV injection in spreadsheet applications.

    Mark formula-like strings as text, including values with leading whitespace.
    """
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def generate_csv(study_id):
    """Generate a CSV export of all ratings for a study.

    Args:
        study_id: The ID of the study to export.

    Returns:
        A tuple of (csv_string, is_complete, warning_message).
        - csv_string: UTF-8 encoded CSV content as a string.
        - is_complete: True if all non-test users have submitted.
        - warning_message: A warning string if incomplete, else None.
    """
    study = db.session.get(Study, study_id)
    if study is None:
        raise ValueError(f"Study {study_id} not found")

    schema = study.rating_schema or {}
    pass_fail_config = study.pass_fail_config

    # Get question IDs from schema for column headers
    questions = schema.get("questions", [])
    question_ids = [q["id"] for q in questions]

    # Collect all attribute keys from dataset images
    images = DatasetImage.query.filter_by(study_id=study_id).all()
    all_attr_keys = set()
    for img in images:
        all_attr_keys.update((img.attributes or {}).keys())
    attr_keys = sorted(all_attr_keys)

    # Check completion status: count non-test study participants
    study_participants = (
        db.session.query(StudyParticipant, User)
        .join(User, StudyParticipant.user_id == User.id)
        .filter(
            StudyParticipant.study_id == study_id,
            User.is_test_user.is_(False),
        )
        .all()
    )

    total_users = len(study_participants)
    submitted_users = sum(1 for pu, _ in study_participants if pu.submitted)
    is_complete = total_users > 0 and submitted_users == total_users

    warning_message = None
    if not is_complete:
        warning_message = (
            f"Incomplete: {submitted_users} of {total_users} "
            f"non-test users have submitted."
        )

    # Query all ratings for non-test users, joined with user and image data
    rows = (
        db.session.query(Rating, User, DatasetImage, StudyParticipant)
        .join(User, Rating.user_id == User.id)
        .join(DatasetImage, Rating.dataset_image_id == DatasetImage.id)
        .join(
            StudyParticipant,
            db.and_(
                StudyParticipant.study_id == Rating.study_id,
                StudyParticipant.user_id == Rating.user_id,
            ),
        )
        .filter(
            Rating.study_id == study_id,
            User.is_test_user.is_(False),
        )
        .order_by(User.id, DatasetImage.sequence_number)
        .all()
    )

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    header = [
        "user_id",
        "user_name",
        "institution",
        "sequence_number",
        "image_path",
    ]
    header.extend(attr_keys)
    header.extend(question_ids)
    header.extend([
        "failure_reason",
        "uncertainty",
        "time_spent_seconds",
        "S_total",
        "pass_fail",
        "submitted",
        "updated_at",
    ])
    writer.writerow([_sanitize_csv_value(value) for value in header])

    # Data rows
    for rating, user, image, pu in rows:
        responses = rating.responses or {}
        s_total = compute_total_score(responses, schema, pass_fail_config)
        pf = compute_pass_fail(responses, schema, pass_fail_config)

        attrs = image.attributes or {}
        row = [
            user.id,
            _sanitize_csv_value(f"{user.first_name} {user.last_name}"),
            _sanitize_csv_value(user.institution or ""),
            image.sequence_number,
            _sanitize_csv_value(image.image_path),
        ]
        for key in attr_keys:
            row.append(_sanitize_csv_value(str(attrs.get(key, ''))))

        # Flatten question responses
        for qid in question_ids:
            val = responses.get(qid)
            row.append(_sanitize_csv_value(val) if val is not None else "")

        # Failure reason (may be string or list for multi-select)
        fr_val = responses.get("failure_reason")
        if isinstance(fr_val, list):
            row.append(_sanitize_csv_value("; ".join(fr_val)))
        elif fr_val is not None:
            row.append(_sanitize_csv_value(str(fr_val)))
        else:
            row.append("")

        row.extend([
            rating.uncertainty if rating.uncertainty is not None else "",
            rating.time_spent_seconds,
            s_total,
            1 if pf is True else (0 if pf is False else ""),
            pu.submitted,
            rating.updated_at.isoformat() if rating.updated_at else "",
        ])

        writer.writerow(row)

    csv_string = output.getvalue()
    output.close()

    return csv_string, is_complete, warning_message


def get_export_status(study_id):
    """Check completion status for CSV export.

    Args:
        study_id: The ID of the study.

    Returns:
        A dict with keys: complete, warning, total_users, submitted_users.
    """
    study = db.session.get(Study, study_id)
    if study is None:
        raise ValueError(f"Study {study_id} not found")

    study_participants = (
        db.session.query(StudyParticipant, User)
        .join(User, StudyParticipant.user_id == User.id)
        .filter(
            StudyParticipant.study_id == study_id,
            User.is_test_user.is_(False),
        )
        .all()
    )

    total_users = len(study_participants)
    submitted_users = sum(1 for pu, _ in study_participants if pu.submitted)
    is_complete = total_users > 0 and submitted_users == total_users

    warning = None
    if not is_complete:
        warning = (
            f"Incomplete: {submitted_users} of {total_users} "
            f"non-test users have submitted."
        )

    return {
        "complete": is_complete,
        "warning": warning,
        "total_users": total_users,
        "submitted_users": submitted_users,
    }
