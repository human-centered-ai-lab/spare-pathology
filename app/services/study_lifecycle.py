"""Study lifecycle helpers: auto-finish detection."""

from app import db
from app.models import StudyParticipant, User


def check_auto_finish(study):
    """Transition *study* to 'finished' if all non-test participants have submitted.

    Guards:
    - Only runs when ``study.status == 'active'``.
    - Returns False when there are zero non-test participants (no vacuous-truth finish).

    Returns True and commits if the study was transitioned, False otherwise.
    """
    if study.status != 'active':
        return False

    non_test_pus = (
        db.session.query(StudyParticipant)
        .join(User, StudyParticipant.user_id == User.id)
        .filter(
            StudyParticipant.study_id == study.id,
            User.is_test_user.is_(False),
            User.role == 'participant',
        )
        .all()
    )

    if not non_test_pus:
        return False

    if all(pu.submitted for pu in non_test_pus):
        study.status = 'finished'
        db.session.commit()
        return True

    return False
