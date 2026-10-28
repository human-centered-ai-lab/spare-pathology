"""Tests for demo data initialization.

Validates that seed_database() creates the expected demo study,
images, participants, ratings, and study assignments, and that
it is idempotent.
"""

import pytest

from app import create_app, db as _db
from app.config import TestConfig
from app.models import User, Study, StudyParticipant, DatasetImage, Rating
from app.services.seed import STUDY_NAME, SEED_PARTICIPANTS, seed_database
from app.services.schema_service import (
    get_default_rating_schema,
    evaluate_condition,
)


@pytest.fixture()
def app(tmp_path):
    """Create a Flask application configured for testing (includes seed data)."""
    class IsolatedConfig(TestConfig):
        UPLOADS_DIR = str(tmp_path / 'uploads')
        DATASETS_DIR = str(tmp_path / 'uploads' / 'datasets')

    application = create_app(IsolatedConfig)
    yield application


@pytest.fixture()
def db(app):
    """Provide a database session with seed data explicitly loaded."""
    with app.app_context():
        _db.create_all()
        seed_database()
        yield _db
        _db.session.rollback()
        _db.drop_all()


# ---- Study Tests ----


def test_demo_study_exists(db):
    """Seed creates the 'Demo Evaluation Study' study."""
    study = Study.query.filter_by(name=STUDY_NAME).first()
    assert study is not None


def test_study_status_active(db):
    """Demo study has status 'active'."""
    study = Study.query.filter_by(name=STUDY_NAME).first()
    assert study.status == "active"


def test_study_has_schema_and_dataset_name(db):
    """Demo study has Tier-2 rating schema and dataset_name."""
    study = Study.query.filter_by(name=STUDY_NAME).first()
    assert study.rating_schema is not None
    assert "questions" in study.rating_schema
    assert len(study.rating_schema["questions"]) == 6
    assert study.dataset_name is not None


# ---- Image Tests ----


def test_80_images_created(db):
    """Seed creates exactly 80 dataset images."""
    study = Study.query.filter_by(name=STUDY_NAME).first()
    count = DatasetImage.query.filter_by(study_id=study.id).count()
    assert count == 80


def test_image_balance_real_synthetic(db):
    """40 real and 40 synthetic images."""
    study = Study.query.filter_by(name=STUDY_NAME).first()
    images = DatasetImage.query.filter_by(study_id=study.id).all()
    real = sum(1 for img in images if not (img.attributes or {}).get("synthetic", False))
    synth = sum(1 for img in images if (img.attributes or {}).get("synthetic", False))
    assert real == 40
    assert synth == 40


def test_images_balanced_across_mpp_levels(db):
    """10 real + 10 synthetic per MPP level (0.5, 1.0, 1.5, 2.0)."""
    study = Study.query.filter_by(name=STUDY_NAME).first()
    images = DatasetImage.query.filter_by(study_id=study.id).all()
    for mpp in [0.5, 1.0, 1.5, 2.0]:
        real = sum(
            1 for img in images
            if (img.attributes or {}).get("mpp_value") == mpp
            and not (img.attributes or {}).get("synthetic", False)
        )
        synth = sum(
            1 for img in images
            if (img.attributes or {}).get("mpp_value") == mpp
            and (img.attributes or {}).get("synthetic", False)
        )
        assert real == 10, f"Expected 10 real images at mpp={mpp}, got {real}"
        assert synth == 10, f"Expected 10 synthetic images at mpp={mpp}, got {synth}"


# ---- Participant Tests ----


def test_four_seed_participants_created(db):
    """Seed creates exactly 4 participant accounts (non-test)."""
    participants = User.query.filter(
        User.last_name == "Test",
        User.role == "participant",
        User.is_test_user.is_(False),
        User.email.like("%.test@example.com"),
    ).all()
    assert len(participants) == 4


def test_participants_from_different_institutions(db):
    """Each seed participant has a unique institution."""
    participants = User.query.filter(
        User.last_name == "Test",
        User.email.like("%.test@example.com"),
    ).all()
    institutions = {p.institution for p in participants}
    assert len(institutions) == 4


def test_participants_can_authenticate(db):
    """Seed participants can log in with 'password123'."""
    for first_name, _ in SEED_PARTICIPANTS:
        email = f"{first_name.lower()}.test@example.com"
        user = User.query.filter_by(email=email).first()
        assert user is not None, f"Participant {email} not found"
        assert user.check_password("password123"), f"{email} password check failed"


# ---- Rating Tests ----


def test_all_ratings_created(db):
    """4 participants x 80 images = 320 ratings total."""
    study = Study.query.filter_by(name=STUDY_NAME).first()
    count = Rating.query.filter_by(study_id=study.id).count()
    assert count == 320


def test_ratings_have_plausible_scores(db):
    """Rating responses contain F1-F6 with values in [0, 2]."""
    study = Study.query.filter_by(name=STUDY_NAME).first()
    ratings = Rating.query.filter_by(study_id=study.id).limit(50).all()
    question_ids = ["F1", "F2", "F3", "F4", "F5", "F6"]
    for r in ratings:
        for qid in question_ids:
            assert qid in r.responses, f"Missing {qid} in rating {r.id}"
            assert r.responses[qid] in (0, 1, 2), f"Invalid score for {qid} in rating {r.id}"


def test_ratings_time_spent_in_range(db):
    """All ratings have time_spent_seconds between 5 and 30."""
    study = Study.query.filter_by(name=STUDY_NAME).first()
    ratings = Rating.query.filter_by(study_id=study.id).all()
    for r in ratings:
        assert 5.0 <= r.time_spent_seconds <= 30.0, (
            f"Rating {r.id} time_spent={r.time_spent_seconds} out of range"
        )


def test_failure_reasons_when_score_zero(db):
    """Ratings with any ordinal score of 0 have a failure_reason set."""
    study = Study.query.filter_by(name=STUDY_NAME).first()
    schema = get_default_rating_schema()
    failure_condition = schema.get("failure_reason", {}).get("condition", {})
    ratings = Rating.query.filter_by(study_id=study.id).all()

    for r in ratings:
        has_zero = evaluate_condition(failure_condition, r.responses, schema)
        if has_zero:
            assert "failure_reason" in r.responses, (
                f"Rating {r.id} has score 0 but no failure_reason"
            )


# ---- StudyParticipant / Submission Tests ----


def test_seed_participants_submitted(db):
    """All 4 seed participants are marked as submitted with a timestamp."""
    study = Study.query.filter_by(name=STUDY_NAME).first()
    for first_name, _ in SEED_PARTICIPANTS:
        email = f"{first_name.lower()}.test@example.com"
        user = User.query.filter_by(email=email).first()
        sp = StudyParticipant.query.filter_by(
            study_id=study.id, user_id=user.id
        ).first()
        assert sp is not None, f"StudyParticipant missing for {email}"
        assert sp.submitted is True, f"{email} not submitted"
        assert sp.submitted_at is not None, f"{email} missing submitted_at"


def test_test_user_assigned_not_submitted(db):
    """The test user is assigned to the study but not submitted."""
    study = Study.query.filter_by(name=STUDY_NAME).first()
    test_user = User.query.filter_by(email="test").first()
    sp = StudyParticipant.query.filter_by(
        study_id=study.id, user_id=test_user.id
    ).first()
    assert sp is not None, "Test user not assigned to study"
    assert sp.submitted is False


# ---- Idempotency Test ----


def test_idempotent_no_duplicate(db):
    """Calling seed_database() again does not create duplicates."""
    # seed_database was already called during create_app; call it again
    seed_database()

    study_count = Study.query.filter_by(name=STUDY_NAME).count()
    assert study_count == 1

    image_count = DatasetImage.query.join(Study).filter(
        Study.name == STUDY_NAME
    ).count()
    assert image_count == 80
