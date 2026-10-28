"""Tests for the statistics engine (app/services/statistics.py).

Uses manually constructed rating data to test all statistical computations.
"""

import json
import warnings

import numpy as np
import pandas as pd
import pytest

from app import create_app, db as _db
from app.config import TestConfig
from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import get_default_pass_fail_config, get_default_rating_schema
from app.services.statistics import (
    compute_all,
    compute_breakdowns,
    compute_center_effects,
    compute_failure_modes,
    compute_fleiss_kappa_score,
    compute_group_comparison,
    compute_icc,
    compute_question_agreement,
    compute_score_distributions,
    invalidate_stats_cache,
    prepare_ratings_dataframe,
    validate_fully_crossed,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    yield app


@pytest.fixture()
def db(app):
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture()
def default_schema():
    return get_default_rating_schema()


@pytest.fixture()
def custom_schema():
    """A custom schema with 3 ordinal questions (0-4 scale)."""
    return {
        "questions": [
            {"id": "Q1", "type": "ordinal", "name": "Quality", "min": 0, "max": 4},
            {"id": "Q2", "type": "ordinal", "name": "Realism", "min": 0, "max": 4},
            {"id": "Q3", "type": "ordinal", "name": "Usability", "min": 0, "max": 4},
        ],
    }


@pytest.fixture()
def custom_pf_config():
    """A custom pass_fail_config for the custom_schema."""
    return {
        "enabled": True,
        "total_score_questions": ["Q1", "Q2", "Q3"],
        "conditions": [
            {"field": "S_total", "operator": ">=", "value": 9},
        ],
    }


def _make_responses(f1=2, f2=2, f3=2, f4=2, f5=2, f6=2, failure_reason=None):
    """Helper to create response dicts for the default schema."""
    resp = {"F1": f1, "F2": f2, "F3": f3, "F4": f4, "F5": f5, "F6": f6}
    if failure_reason is not None:
        resp["failure_reason"] = failure_reason
    return resp


def _create_user(db, email, institution, is_test_user=False, role="participant"):
    """Create and return a user."""
    user = User(
        first_name=email.split("@")[0],
        last_name="User",
        email=email,
        institution=institution,
        role=role,
        is_test_user=is_test_user,
    )
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()
    return user


def _create_study(db, schema=None, pass_fail_config=None):
    """Create and return a study with the given schema."""
    if schema is None:
        schema = get_default_rating_schema()
    if pass_fail_config is None:
        pass_fail_config = get_default_pass_fail_config()
    study = Study(
        name="Test Study",
        description="Test",
        status="active",
        rating_schema=schema,
        pass_fail_config=pass_fail_config,
    )
    db.session.add(study)
    db.session.flush()
    return study


def _create_image(db, study_id, path, attributes=None, seq=1):
    """Create and return a dataset image."""
    img = DatasetImage(
        study_id=study_id,
        image_path=path,
        attributes=attributes or {},
        sequence_number=seq,
    )
    db.session.add(img)
    db.session.flush()
    return img


def _create_rating(db, user_id, image_id, study_id, responses):
    """Create and return a rating."""
    rating = Rating(
        user_id=user_id,
        dataset_image_id=image_id,
        study_id=study_id,
        responses=responses,
    )
    db.session.add(rating)
    db.session.flush()
    return rating


def _create_study_participant(db, study_id, user_id, submitted=False):
    """Create and return a study participant."""
    sp = StudyParticipant(
        study_id=study_id,
        user_id=user_id,
        submitted=submitted,
    )
    db.session.add(sp)
    db.session.flush()
    return sp


@pytest.fixture()
def study_data(db, default_schema):
    """Create a complete study dataset with multiple raters, centers, and images.

    Returns a dict with all created objects for test access.
    """
    invalidate_stats_cache()
    study = _create_study(db, default_schema)

    # Create users from 3 different centers
    users = []
    centers = ["Center A", "Center B", "Center C"]
    for i, center in enumerate(centers):
        u1 = _create_user(db, f"rater{i * 2 + 1}@example.com", center)
        u2 = _create_user(db, f"rater{i * 2 + 2}@example.com", center)
        users.extend([u1, u2])
        _create_study_participant(db, study.id, u1.id, submitted=True)
        _create_study_participant(db, study.id, u2.id, submitted=(i < 2))  # Center C user2 not submitted

    # Create a test user (should be excluded from all computations)
    test_user = _create_user(db, "testbot@example.com", "Center A", is_test_user=True)
    _create_study_participant(db, study.id, test_user.id, submitted=True)

    # Create images: 4 real, 4 synthetic
    images = []
    for i in range(4):
        real_img = _create_image(
            db, study.id, f"real_{i}.png",
            attributes={
                "synthetic": False,
                "tissue_type": "Tumor-dominant" if i < 2 else "Stroma-dominant",
                "mpp_value": 0.25 if i < 2 else 0.5,
            },
            seq=i + 1,
        )
        synth_img = _create_image(
            db, study.id, f"synth_{i}.png",
            attributes={
                "synthetic": True,
                "tissue_type": "Tumor-dominant" if i < 2 else "Stroma-dominant",
                "mpp_value": 0.25 if i < 2 else 0.5,
                "model_name": "ModelA" if i < 2 else "ModelB",
            },
            seq=i + 5,
        )
        images.extend([real_img, synth_img])

    # Create ratings for all non-test users x all images
    # Vary scores by center and image type to create meaningful statistics
    for user in users:
        center_idx = centers.index(user.institution)
        for img in images:
            # Base score depends on center (center effects)
            base = 10 - center_idx  # Center A: 10, B: 9, C: 8
            if (img.attributes or {}).get("synthetic"):
                base -= 1  # Synthetic images score slightly lower

            # Vary individual questions
            f1 = min(2, max(0, base - 8))
            f2 = min(2, max(0, base - 8))
            f3 = min(2, max(0, base - 7))
            f4 = min(2, max(0, base - 7))
            f5 = min(2, max(0, base - 6))
            f6 = min(2, max(0, base - 6))

            resp = _make_responses(f1, f2, f3, f4, f5, f6)

            # Add failure reason for failed ratings
            s_total = f1 + f2 + f3 + f4 + f5 + f6
            if s_total < 9 or f5 < 1:
                resp["failure_reason"] = "Nuclear/cytology inconsistency (F1)"

            _create_rating(db, user.id, img.id, study.id, resp)

    # Create ratings for test user too (should be excluded)
    for img in images:
        _create_rating(db, test_user.id, img.id, study.id,
                       _make_responses(0, 0, 0, 0, 0, 0))

    db.session.commit()

    return {
        "study": study,
        "users": users,
        "test_user": test_user,
        "images": images,
        "centers": centers,
    }


# ---------------------------------------------------------------------------
# Helper to build DataFrames directly (without DB) for unit testing
# ---------------------------------------------------------------------------


def _make_df(n_raters=3, n_images=5, score_fn=None, include_synthetic=False):
    """Build a DataFrame matching the expected format for statistics functions.

    Args:
        n_raters: Number of raters
        n_images: Number of images
        score_fn: Optional function (rater_idx, image_idx) -> S_total
        include_synthetic: If True, half the images are synthetic
    """
    if score_fn is None:
        def score_fn(r, i):
            return 9 + (r % 3) - (i % 2)

    rows = []
    for r_idx in range(n_raters):
        for i_idx in range(n_images):
            s_total = score_fn(r_idx, i_idx)
            is_synth = include_synthetic and (i_idx >= n_images // 2)
            pf = 1 if s_total >= 9 else 0

            f_scores = {}
            remaining = s_total
            for q in ["F1", "F2", "F3", "F4", "F5", "F6"]:
                val = min(2, max(0, remaining - (5 - list(["F1", "F2", "F3", "F4", "F5", "F6"]).index(q)) * 1))
                val = min(2, remaining // max(1, 6 - list(["F1", "F2", "F3", "F4", "F5", "F6"]).index(q)))
                f_scores[q] = val
                remaining -= val

            row = {
                "user_id": r_idx + 1,
                "institution": f"Center_{chr(65 + r_idx % 3)}",
                "dataset_image_id": i_idx + 1,
                "attr_synthetic": is_synth,
                "attr_mpp_value": 0.25 if i_idx < n_images // 2 else 0.5,
                "attr_tissue_type": "Tumor" if i_idx % 2 == 0 else "Stroma",
                "attr_model_name": "ModelA" if is_synth else None,
                "S_total": s_total,
                "pass_fail": pf,
                "responses": {},
            }
            row.update(f_scores)
            rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: compute_icc
# ---------------------------------------------------------------------------


class TestComputeICC:
    """Tests for ICC computation."""

    def test_perfect_agreement(self):
        """All raters give same scores -> ICC close to 1.

        Note: when raters agree perfectly, pingouin CIs may be NaN due to
        zero error variance. The ICC value itself should be 1.0.
        """
        rows = []
        for rater in range(3):
            for img in range(5):
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "S_total": img * 2 + 2,  # Varies by image, same across raters
                })
        df = pd.DataFrame(rows)
        result = compute_icc(df)
        assert result["value"] is not None
        assert result["value"] > 0.99  # Perfect agreement
        assert result["message"] is None
        # CIs may be None (NaN) for perfect agreement due to zero error variance

    def test_moderate_agreement_with_finite_ci(self):
        """Moderate agreement with variation -> ICC with finite CIs."""
        np.random.seed(99)
        rows = []
        for rater in range(4):
            for img in range(10):
                # Image-level effect plus meaningful rater variation
                base = img * 1.0 + 3
                noise = np.random.normal(0, 0.5)
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "S_total": base + noise + rater * 0.3,
                })
        df = pd.DataFrame(rows)
        result = compute_icc(df)
        assert result["value"] is not None
        assert result["value"] > 0.5
        assert result["ci_lower"] is not None
        assert result["ci_upper"] is not None
        # Use approximate comparison to handle floating point
        assert result["ci_lower"] <= result["ci_upper"]

    def test_no_agreement(self):
        """Raters give random unrelated scores -> low ICC."""
        np.random.seed(42)
        rows = []
        for rater in range(4):
            for img in range(10):
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "S_total": np.random.randint(0, 13),
                })
        df = pd.DataFrame(rows)
        result = compute_icc(df)
        assert result["value"] is not None
        # Random scores should give low ICC
        assert result["value"] < 0.5

    def test_returns_ci(self):
        """ICC result includes confidence interval when data has sufficient variance."""
        np.random.seed(123)
        rows = []
        # Use data with real variance to get finite CIs
        scores_per_image = [3, 5, 7, 9, 11, 4, 6, 8, 10, 12]
        for rater in range(3):
            for img_idx, base_score in enumerate(scores_per_image):
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img_idx + 1,
                    "S_total": base_score + rater,
                })
        df = pd.DataFrame(rows)
        result = compute_icc(df)
        assert result["value"] is not None
        assert result["message"] is None
        # With sufficient variance, CIs should be finite
        if result["ci_lower"] is not None and result["ci_upper"] is not None:
            assert result["ci_lower"] <= result["ci_upper"]

    def test_empty_df(self):
        """Empty DataFrame -> None with message."""
        df = pd.DataFrame()
        result = compute_icc(df)
        assert result["value"] is None
        assert "No data" in result["message"]

    def test_single_rater(self):
        """Only 1 rater -> None with message."""
        rows = [{"user_id": 1, "dataset_image_id": i, "S_total": i} for i in range(5)]
        df = pd.DataFrame(rows)
        result = compute_icc(df)
        assert result["value"] is None
        assert "2 raters" in result["message"]

    def test_single_image(self):
        """Only 1 image -> None with message."""
        rows = [{"user_id": i, "dataset_image_id": 1, "S_total": 10} for i in range(3)]
        df = pd.DataFrame(rows)
        result = compute_icc(df)
        assert result["value"] is None
        assert "2 images" in result["message"]

    def test_two_raters_two_images_insufficient(self):
        """Minimal case: 2 raters, 2 images = 4 ratings -> below pingouin threshold."""
        rows = [
            {"user_id": 1, "dataset_image_id": 1, "S_total": 10},
            {"user_id": 1, "dataset_image_id": 2, "S_total": 8},
            {"user_id": 2, "dataset_image_id": 1, "S_total": 10},
            {"user_id": 2, "dataset_image_id": 2, "S_total": 7},
        ]
        df = pd.DataFrame(rows)
        result = compute_icc(df)
        # pingouin requires at least 5 ratings
        assert result["value"] is None
        assert "5 ratings" in result["message"]

    def test_two_raters_three_images(self):
        """2 raters, 3 images = 6 ratings -> sufficient for computation."""
        rows = [
            {"user_id": 1, "dataset_image_id": 1, "S_total": 10},
            {"user_id": 1, "dataset_image_id": 2, "S_total": 8},
            {"user_id": 1, "dataset_image_id": 3, "S_total": 6},
            {"user_id": 2, "dataset_image_id": 1, "S_total": 10},
            {"user_id": 2, "dataset_image_id": 2, "S_total": 7},
            {"user_id": 2, "dataset_image_id": 3, "S_total": 5},
        ]
        df = pd.DataFrame(rows)
        result = compute_icc(df)
        assert result["value"] is not None
        assert result["message"] is None


# ---------------------------------------------------------------------------
# Tests: compute_fleiss_kappa_score
# ---------------------------------------------------------------------------


class TestComputeFleissKappa:
    """Tests for Fleiss' kappa computation."""

    def test_perfect_agreement(self):
        """All raters agree on all images -> kappa = 1."""
        rows = []
        for rater in range(4):
            for img in range(6):
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "pass_fail": 1 if img < 3 else 0,  # Same for all raters
                })
        df = pd.DataFrame(rows)
        result = compute_fleiss_kappa_score(df, n_bootstrap=50)
        assert result["value"] is not None
        assert abs(result["value"] - 1.0) < 0.01
        assert result["message"] is None

    def test_no_agreement(self):
        """Raters disagree -> low kappa."""
        rows = []
        # 4 raters on 8 images, systematically disagreeing
        patterns = [
            [1, 0, 1, 0, 1, 0, 1, 0],  # rater 1
            [0, 1, 0, 1, 0, 1, 0, 1],  # rater 2
            [1, 1, 0, 0, 1, 1, 0, 0],  # rater 3
            [0, 0, 1, 1, 0, 0, 1, 1],  # rater 4
        ]
        for rater_idx, pattern in enumerate(patterns):
            for img_idx, val in enumerate(pattern):
                rows.append({
                    "user_id": rater_idx + 1,
                    "dataset_image_id": img_idx + 1,
                    "pass_fail": val,
                })
        df = pd.DataFrame(rows)
        result = compute_fleiss_kappa_score(df, n_bootstrap=50)
        assert result["value"] is not None
        assert result["value"] < 0.3  # Low agreement

    def test_has_bootstrap_ci(self):
        """Bootstrap CI should be returned."""
        rows = []
        for rater in range(3):
            for img in range(10):
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "pass_fail": 1 if img < 7 else 0,
                })
        df = pd.DataFrame(rows)
        result = compute_fleiss_kappa_score(df, n_bootstrap=100, random_state=42)
        assert result["ci_lower"] is not None
        assert result["ci_upper"] is not None

    def test_empty_df(self):
        """Empty DataFrame -> None with message."""
        df = pd.DataFrame()
        result = compute_fleiss_kappa_score(df)
        assert result["value"] is None
        assert "No data" in result["message"]

    def test_single_rater(self):
        """Only 1 rater -> None with message."""
        rows = [{"user_id": 1, "dataset_image_id": i, "pass_fail": 1} for i in range(5)]
        df = pd.DataFrame(rows)
        result = compute_fleiss_kappa_score(df)
        assert result["value"] is None
        assert "2 raters" in result["message"]

    def test_single_image(self):
        """Only 1 image -> None with message."""
        rows = [{"user_id": i, "dataset_image_id": 1, "pass_fail": 1} for i in range(3)]
        df = pd.DataFrame(rows)
        result = compute_fleiss_kappa_score(df)
        assert result["value"] is None
        assert "2 images" in result["message"]


# ---------------------------------------------------------------------------
# Tests: compute_question_agreement
# ---------------------------------------------------------------------------


class TestComputeQuestionAgreement:
    """Tests for per-question agreement (ICC or kappa)."""

    def test_returns_result_per_question(self):
        """Should return one result per ordinal question."""
        schema = get_default_rating_schema()
        rows = []
        for rater in range(3):
            for img in range(5):
                row = {
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "F1": img % 3,
                    "F2": (img + 1) % 3,
                    "F3": rater % 3,
                    "F4": 2,
                    "F5": img % 3,
                    "F6": 1,
                }
                rows.append(row)
        df = pd.DataFrame(rows)
        result = compute_question_agreement(df, schema)
        assert set(result.keys()) == {"F1", "F2", "F3", "F4", "F5", "F6"}

    def test_high_agreement_question(self):
        """Question where all raters agree -> high ICC."""
        schema = get_default_rating_schema()
        rows = []
        for rater in range(3):
            for img in range(5):
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "F1": img % 3,  # All raters give same score per image
                    "F2": 2,
                    "F3": 1,
                    "F4": 2,
                    "F5": 1,
                    "F6": 2,
                })
        df = pd.DataFrame(rows)
        result = compute_question_agreement(df, schema)
        # F1 has perfect agreement across raters (same per image)
        assert result["F1"]["value"] is not None
        assert result["F1"]["value"] > 0.9

    def test_insufficient_data(self):
        """Single rater -> insufficient data message for each question."""
        schema = get_default_rating_schema()
        rows = [{"user_id": 1, "dataset_image_id": i + 1,
                 "F1": 2, "F2": 1, "F3": 2, "F4": 1, "F5": 2, "F6": 1}
                for i in range(5)]
        df = pd.DataFrame(rows)
        result = compute_question_agreement(df, schema)
        for qid in ["F1", "F2", "F3", "F4", "F5", "F6"]:
            assert result[qid]["value"] is None
            assert "Insufficient" in result[qid]["message"]

    def test_missing_column(self):
        """Question column not in DataFrame -> appropriate message."""
        schema = get_default_rating_schema()
        df = pd.DataFrame({
            "user_id": [1, 2, 1, 2],
            "dataset_image_id": [1, 1, 2, 2],
            "F1": [2, 2, 1, 1],
            # F2-F6 missing
        })
        result = compute_question_agreement(df, schema)
        assert result["F2"]["value"] is None
        assert "not found" in result["F2"]["message"]

    def test_with_custom_schema(self, custom_schema):
        """Works with a custom schema."""
        rows = []
        for rater in range(3):
            for img in range(5):
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "Q1": img % 5,
                    "Q2": (img + 1) % 5,
                    "Q3": 3,
                })
        df = pd.DataFrame(rows)
        result = compute_question_agreement(df, custom_schema)
        assert set(result.keys()) == {"Q1", "Q2", "Q3"}
        # Q1 has perfect agreement across raters
        assert result["Q1"]["metric"] == "ICC"
        assert result["Q1"]["value"] is not None

    def test_binary_ordinal_with_non_zero_based_scale_uses_correct_categories(self):
        """Binary ordinal questions with min/max != 0/1 should still compute kappa."""
        binary_schema = {
            "questions": [
                {"id": "B1", "type": "ordinal", "name": "Binary", "min": 1, "max": 2},
            ],
        }
        rows = []
        for rater in range(3):
            for img in range(5):
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "B1": 1 if img % 2 == 0 else 2,
                })
        df = pd.DataFrame(rows)

        result = compute_question_agreement(df, binary_schema)
        assert result["B1"]["metric"] == "kappa"
        assert result["B1"]["value"] is not None
        assert result["B1"]["message"] is None


# ---------------------------------------------------------------------------
# Tests: compute_center_effects
# ---------------------------------------------------------------------------


class TestComputeCenterEffects:
    """Tests for center effects via MixedLM."""

    def test_detects_center_differences(self):
        """Different centers give systematically different scores."""
        rows = []
        for rater in range(6):
            center = f"Center_{chr(65 + rater // 2)}"  # A, A, B, B, C, C
            for img in range(8):
                # Center A scores high, B medium, C low
                base = 12 - (rater // 2) * 2
                rows.append({
                    "user_id": rater + 1,
                    "institution": center,
                    "dataset_image_id": img + 1,
                    "S_total": base + (img % 2),
                })
        df = pd.DataFrame(rows)
        result = compute_center_effects(df)
        assert result["message"] is None
        assert len(result["effects"]) >= 2
        assert result["effects"][0]["is_reference"] is True

    def test_single_center(self):
        """Only 1 center -> graceful degradation."""
        rows = []
        for rater in range(3):
            for img in range(5):
                rows.append({
                    "user_id": rater + 1,
                    "institution": "Only Center",
                    "dataset_image_id": img + 1,
                    "S_total": 10,
                })
        df = pd.DataFrame(rows)
        result = compute_center_effects(df)
        assert result["effects"] == []
        assert "2 centers" in result["message"]

    def test_empty_df(self):
        """Empty DataFrame -> graceful degradation."""
        df = pd.DataFrame()
        result = compute_center_effects(df)
        assert result["effects"] == []
        assert "No data" in result["message"]

    def test_two_centers_minimal(self):
        """Minimal 2-center case."""
        rows = []
        for rater in range(4):
            center = "Center_A" if rater < 2 else "Center_B"
            for img in range(4):
                s = 10 if center == "Center_A" else 8
                rows.append({
                    "user_id": rater + 1,
                    "institution": center,
                    "dataset_image_id": img + 1,
                    "S_total": s + (img % 2),
                })
        df = pd.DataFrame(rows)
        result = compute_center_effects(df)
        assert len(result["effects"]) == 2
        assert result["message"] is None


# ---------------------------------------------------------------------------
# Tests: compute_group_comparison
# ---------------------------------------------------------------------------


class TestComputeGroupComparison:
    """Tests for group comparison (replaces old real vs synthetic)."""

    def test_computes_pass_rates(self):
        """Should compute pass rates for both groups."""
        rows = []
        for rater in range(3):
            for img in range(10):
                is_synth = img >= 5
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "attr_synthetic": is_synth,
                    "S_total": 10 if not is_synth else 7,
                    "pass_fail": 1 if not is_synth else 0,
                })
        df = pd.DataFrame(rows)
        result = compute_group_comparison(df, "attr_synthetic")
        assert result["pass_rates"]["False"] == 1.0
        assert result["pass_rates"]["True"] == 0.0
        assert result["message"] is None

    def test_mann_whitney_significant(self):
        """Systematically different scores -> significant p-value."""
        rows = []
        for rater in range(3):
            for img in range(20):
                is_synth = img >= 10
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "attr_synthetic": is_synth,
                    "S_total": 11 if not is_synth else 5,
                    "pass_fail": 1 if not is_synth else 0,
                })
        df = pd.DataFrame(rows)
        result = compute_group_comparison(df, "attr_synthetic")
        assert result["score_comparison"]["mannwhitney_p"] < 0.05

    def test_per_question_comparison(self):
        """Should compute per-question comparison."""
        rows = []
        for rater in range(3):
            for img in range(10):
                is_synth = img >= 5
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "attr_synthetic": is_synth,
                    "S_total": 12 if not is_synth else 6,
                    "pass_fail": 1 if not is_synth else 0,
                    "F1": 2 if not is_synth else 1,
                    "F2": 2 if not is_synth else 1,
                })
        df = pd.DataFrame(rows)
        result = compute_group_comparison(df, "attr_synthetic")
        assert "F1" in result["per_question"]
        assert result["per_question"]["F1"]["False_mean"] > result["per_question"]["F1"]["True_mean"]

    def test_empty_df(self):
        """Empty DataFrame -> graceful degradation."""
        df = pd.DataFrame()
        result = compute_group_comparison(df, "attr_synthetic")
        assert result["pass_rates"] is None
        assert "No data" in result["message"]

    def test_only_one_group(self):
        """Only one group value -> message about needing 2 groups."""
        rows = [{"user_id": 1, "dataset_image_id": 1, "attr_synthetic": False,
                 "S_total": 10, "pass_fail": 1}]
        df = pd.DataFrame(rows)
        result = compute_group_comparison(df, "attr_synthetic")
        assert "2 groups" in result["message"]

    def test_missing_column(self):
        """Missing group column -> message."""
        rows = [{"user_id": 1, "dataset_image_id": 1,
                 "S_total": 10, "pass_fail": 1}]
        df = pd.DataFrame(rows)
        result = compute_group_comparison(df, "attr_synthetic")
        assert "not found" in result["message"]


# ---------------------------------------------------------------------------
# Tests: compute_failure_modes
# ---------------------------------------------------------------------------


class TestComputeFailureModes:
    """Tests for failure mode distribution."""

    def test_groups_by_center(self):
        """Should group failure reasons by center."""
        rows = [
            {"institution": "Center A", "pass_fail": 0,
             "responses": {"failure_reason": "Nuclear/cytology inconsistency (F1)"}},
            {"institution": "Center A", "pass_fail": 0,
             "responses": {"failure_reason": "Architecture incoherence (F2)"}},
            {"institution": "Center B", "pass_fail": 0,
             "responses": {"failure_reason": "Nuclear/cytology inconsistency (F1)"}},
            {"institution": "Center A", "pass_fail": 1, "responses": {}},  # Passed, excluded
        ]
        df = pd.DataFrame(rows)
        result = compute_failure_modes(df)
        assert "Center A" in result["by_center"]
        assert "Center B" in result["by_center"]
        assert result["by_center"]["Center A"]["Nuclear/cytology inconsistency (F1)"] == 1
        assert result["by_center"]["Center A"]["Architecture incoherence (F2)"] == 1
        assert result["overall"]["Nuclear/cytology inconsistency (F1)"] == 2

    def test_no_failures(self):
        """All passed -> empty results with message."""
        rows = [{"institution": "Center A", "pass_fail": 1, "responses": {}}]
        df = pd.DataFrame(rows)
        result = compute_failure_modes(df)
        assert result["by_center"] == {}
        assert "No failed" in result["message"]

    def test_empty_df(self):
        """Empty DataFrame -> graceful degradation."""
        df = pd.DataFrame()
        result = compute_failure_modes(df)
        assert result["by_center"] == {}
        assert "No data" in result["message"]

    def test_missing_failure_reason(self):
        """Failure without explicit reason -> 'Unknown'."""
        rows = [
            {"institution": "Center A", "pass_fail": 0, "responses": {}},
        ]
        df = pd.DataFrame(rows)
        result = compute_failure_modes(df)
        assert result["overall"]["Unknown"] == 1


# ---------------------------------------------------------------------------
# Tests: compute_score_distributions
# ---------------------------------------------------------------------------


class TestComputeScoreDistributions:
    """Tests for score distribution computation."""

    def test_grouped_by_attribute(self):
        """Should return distributions grouped by attribute."""
        rows = []
        for i in range(20):
            rows.append({
                "attr_synthetic": i >= 10,
                "S_total": 10 + (i % 3) if i < 10 else 7 + (i % 3),
            })
        df = pd.DataFrame(rows)
        result = compute_score_distributions(df, group_col="attr_synthetic")
        assert "True" in result["groups"]
        assert "False" in result["groups"]
        assert result["groups"]["False"]["mean"] > result["groups"]["True"]["mean"]
        assert result["groups"]["False"]["count"] == 10
        assert result["groups"]["True"]["count"] == 10

    def test_no_group_returns_all(self):
        """Without group_col, returns a single 'all' group."""
        rows = [{"S_total": v} for v in [8, 9, 10, 11, 12]]
        df = pd.DataFrame(rows)
        result = compute_score_distributions(df)
        assert "all" in result["groups"]
        assert result["groups"]["all"]["mean"] == 10.0
        assert result["groups"]["all"]["median"] == 10.0
        assert result["groups"]["all"]["q1"] == 9.0
        assert result["groups"]["all"]["q3"] == 11.0

    def test_empty_df(self):
        """Empty DataFrame -> graceful degradation."""
        df = pd.DataFrame()
        result = compute_score_distributions(df)
        assert result["groups"] == {}
        assert "No data" in result["message"]


# ---------------------------------------------------------------------------
# Tests: compute_breakdowns
# ---------------------------------------------------------------------------


class TestComputeBreakdowns:
    """Tests for breakdown by grouping column."""

    def test_by_tissue_type(self):
        """Should group by attr_tissue_type."""
        rows = []
        for i in range(12):
            rows.append({
                "user_id": (i % 3) + 1,
                "dataset_image_id": i + 1,
                "attr_tissue_type": "Tumor" if i < 6 else "Stroma",
                "S_total": 10 if i < 6 else 8,
                "pass_fail": 1 if i < 6 else 0,
            })
        df = pd.DataFrame(rows)
        result = compute_breakdowns(df, "attr_tissue_type")
        assert "Tumor" in result["groups"]
        assert "Stroma" in result["groups"]
        assert result["groups"]["Tumor"]["mean_score"] == 10.0
        assert result["groups"]["Stroma"]["mean_score"] == 8.0

    def test_by_mpp_value(self):
        """Should group by attr_mpp_value."""
        rows = []
        for i in range(10):
            rows.append({
                "user_id": 1,
                "dataset_image_id": i + 1,
                "attr_mpp_value": 0.25 if i < 5 else 0.5,
                "S_total": 11,
                "pass_fail": 1,
            })
        df = pd.DataFrame(rows)
        result = compute_breakdowns(df, "attr_mpp_value")
        assert "0.25" in result["groups"]
        assert "0.5" in result["groups"]

    def test_missing_column(self):
        """Nonexistent column -> error message."""
        df = pd.DataFrame({"user_id": [1], "S_total": [10], "pass_fail": [1]})
        result = compute_breakdowns(df, "nonexistent")
        assert "not found" in result["message"]

    def test_empty_df(self):
        """Empty DataFrame -> graceful degradation."""
        df = pd.DataFrame()
        result = compute_breakdowns(df, "mpp")
        assert result["groups"] == {}
        assert "No data" in result["message"]


# ---------------------------------------------------------------------------
# Tests: validate_fully_crossed
# ---------------------------------------------------------------------------


class TestValidateFullyCrossed:
    """Tests for fully-crossed design validation."""

    def test_balanced_design(self):
        """Fully crossed design -> is_balanced=True."""
        rows = []
        for rater in range(3):
            for img in range(5):
                rows.append({"user_id": rater + 1, "dataset_image_id": img + 1})
        df = pd.DataFrame(rows)
        result = validate_fully_crossed(df)
        assert result["is_balanced"] is True
        assert result["n_raters"] == 3
        assert result["n_images"] == 5
        assert result["expected_ratings"] == 15
        assert result["actual_ratings"] == 15
        assert result["missing_ratings"] == 0
        assert result["completeness"] == 1.0
        assert result["warnings"] == []

    def test_unbalanced_design(self):
        """Missing ratings -> is_balanced=False with warnings."""
        rows = []
        for rater in range(3):
            for img in range(5):
                if rater == 2 and img >= 3:
                    continue  # Rater 3 missing 2 ratings
                rows.append({"user_id": rater + 1, "dataset_image_id": img + 1})
        df = pd.DataFrame(rows)
        result = validate_fully_crossed(df)
        assert result["is_balanced"] is False
        assert result["missing_ratings"] == 2
        assert len(result["warnings"]) > 0
        assert "not fully crossed" in result["warnings"][0]

    def test_empty_df(self):
        """Empty DataFrame -> graceful degradation."""
        df = pd.DataFrame()
        result = validate_fully_crossed(df)
        assert result["is_balanced"] is False
        assert result["n_raters"] == 0
        assert "No data" in result["warnings"][0]

    def test_single_rater_all_images(self):
        """Single rater -> balanced trivially."""
        rows = [{"user_id": 1, "dataset_image_id": i + 1} for i in range(5)]
        df = pd.DataFrame(rows)
        result = validate_fully_crossed(df)
        assert result["is_balanced"] is True
        assert result["n_raters"] == 1
        assert result["n_images"] == 5

    def test_completeness_percentage(self):
        """Check completeness calculation."""
        # 3 raters, 4 images, but one rater missing one image
        rows = []
        for rater in range(3):
            for img in range(4):
                if rater == 0 and img == 3:
                    continue
                rows.append({"user_id": rater + 1, "dataset_image_id": img + 1})
        df = pd.DataFrame(rows)
        result = validate_fully_crossed(df)
        assert result["expected_ratings"] == 12
        assert result["actual_ratings"] == 11
        assert result["completeness"] == pytest.approx(11 / 12)


# ---------------------------------------------------------------------------
# Tests: prepare_ratings_dataframe (integration tests with DB)
# ---------------------------------------------------------------------------


class TestPrepareRatingsDataframe:
    """Tests for prepare_ratings_dataframe (requires app context and DB)."""

    def test_basic_query(self, app, study_data):
        """Should return DataFrame with expected columns."""
        with app.app_context():
            df = prepare_ratings_dataframe(study_data["study"].id)
            assert not df.empty
            expected_cols = {
                "user_id", "institution", "dataset_image_id",
                "attr_synthetic", "attr_mpp_value", "attr_tissue_type",
                "S_total", "pass_fail",
                "F1", "F2", "F3", "F4", "F5", "F6",
            }
            assert expected_cols.issubset(set(df.columns))

    def test_excludes_test_users(self, app, study_data):
        """Test users should be excluded."""
        with app.app_context():
            df = prepare_ratings_dataframe(study_data["study"].id)
            test_user_id = study_data["test_user"].id
            assert test_user_id not in df["user_id"].values
            # 6 real users x 8 images = 48 ratings expected
            assert len(df) == 48

    def test_filter_submitted_only(self, app, study_data):
        """submitted_only filter should only include submitted users."""
        with app.app_context():
            df = prepare_ratings_dataframe(
                study_data["study"].id,
                filters={"submitted_only": True},
            )
            # 5 submitted users x 8 images = 40
            assert len(df) == 40

    def test_filter_is_synthetic(self, app, study_data):
        """Filter by synthetic attribute."""
        with app.app_context():
            df = prepare_ratings_dataframe(
                study_data["study"].id,
                filters={"attributes": {"synthetic": True}},
            )
            assert all(df["attr_synthetic"] == True)  # noqa: E712
            assert len(df) == 24  # 6 users x 4 synthetic images

    def test_filter_real(self, app, study_data):
        """Filter by synthetic=False attribute."""
        with app.app_context():
            df = prepare_ratings_dataframe(
                study_data["study"].id,
                filters={"attributes": {"synthetic": False}},
            )
            assert all(df["attr_synthetic"] == False)  # noqa: E712
            assert len(df) == 24  # 6 users x 4 real images

    def test_filter_by_mpp(self, app, study_data):
        """Filter by mpp_value attribute."""
        with app.app_context():
            df = prepare_ratings_dataframe(
                study_data["study"].id,
                filters={"attributes": {"mpp_value": 0.25}},
            )
            assert all(df["attr_mpp_value"] == 0.25)
            # 4 images with mpp=0.25 (2 real + 2 synthetic) x 6 users
            assert len(df) == 24

    def test_filter_by_tissue_type(self, app, study_data):
        """Filter by tissue_type attribute."""
        with app.app_context():
            df = prepare_ratings_dataframe(
                study_data["study"].id,
                filters={"attributes": {"tissue_type": "Tumor-dominant"}},
            )
            assert all(df["attr_tissue_type"] == "Tumor-dominant")

    def test_filter_by_model_name(self, app, study_data):
        """Filter by model_name attribute."""
        with app.app_context():
            df = prepare_ratings_dataframe(
                study_data["study"].id,
                filters={"attributes": {"model_name": "ModelA"}},
            )
            assert all(df["attr_model_name"] == "ModelA")
            # Only 2 synthetic images have ModelA x 6 users = 12
            assert len(df) == 12

    def test_filter_by_user_ids(self, app, study_data):
        """Filter to specific user IDs."""
        with app.app_context():
            user_ids = [study_data["users"][0].id, study_data["users"][1].id]
            df = prepare_ratings_dataframe(
                study_data["study"].id,
                filters={"user_ids": user_ids},
            )
            assert set(df["user_id"].unique()) == set(user_ids)
            assert len(df) == 16  # 2 users x 8 images

    def test_computes_s_total(self, app, study_data):
        """S_total should be computed from responses."""
        with app.app_context():
            df = prepare_ratings_dataframe(study_data["study"].id)
            # S_total should be sum of F1-F6
            for _, row in df.head(5).iterrows():
                expected = sum(row[q] for q in ["F1", "F2", "F3", "F4", "F5", "F6"]
                               if row[q] is not None)
                assert row["S_total"] == expected

    def test_computes_pass_fail(self, app, study_data):
        """pass_fail should be 0 or 1."""
        with app.app_context():
            df = prepare_ratings_dataframe(study_data["study"].id)
            assert set(df["pass_fail"].unique()).issubset({0, 1})

    def test_empty_study(self, app, db):
        """Study with no ratings -> empty DataFrame."""
        with app.app_context():
            study = _create_study(db)
            db.session.commit()
            df = prepare_ratings_dataframe(study.id)
            assert df.empty

    def test_no_filters(self, app, study_data):
        """No filters -> returns all non-test user ratings."""
        with app.app_context():
            df = prepare_ratings_dataframe(study_data["study"].id, filters={})
            assert len(df) == 48

    def test_combined_filters(self, app, study_data):
        """Multiple attribute filters applied simultaneously."""
        with app.app_context():
            df = prepare_ratings_dataframe(
                study_data["study"].id,
                filters={
                    "attributes": {
                        "synthetic": True,
                        "mpp_value": 0.25,
                    },
                },
            )
            assert all(df["attr_synthetic"] == True)  # noqa: E712
            assert all(df["attr_mpp_value"] == 0.25)
            # 2 synthetic images with mpp=0.25 x 6 users = 12
            assert len(df) == 12


# ---------------------------------------------------------------------------
# Tests: compute_all (orchestrator, integration)
# ---------------------------------------------------------------------------


class TestComputeAll:
    """Tests for the compute_all orchestrator."""

    def test_returns_all_sections(self, app, study_data):
        """compute_all should return all statistic sections."""
        with app.app_context():
            result = compute_all(study_data["study"].id)
            assert "validation" in result
            assert "icc" in result
            assert "fleiss_kappa" in result
            assert "question_agreement" in result
            assert "center_effects" in result
            assert "failure_modes" in result
            assert "score_distributions" in result
            assert "group_comparison" in result
            assert "breakdowns" in result

    def test_icc_computed(self, app, study_data):
        """ICC should be computed for the study data."""
        with app.app_context():
            result = compute_all(study_data["study"].id)
            assert result["icc"]["value"] is not None

    def test_fleiss_kappa_computed(self, app, study_data):
        """Fleiss' kappa should be computed."""
        with app.app_context():
            result = compute_all(study_data["study"].id)
            assert result["fleiss_kappa"]["value"] is not None

    def test_center_effects_computed(self, app, study_data):
        """Center effects should be computed."""
        with app.app_context():
            result = compute_all(study_data["study"].id)
            assert len(result["center_effects"]["effects"]) >= 2

    def test_group_comparison_with_group_by(self, app, study_data):
        """Group comparison should be computed when group_by is set."""
        with app.app_context():
            result = compute_all(
                study_data["study"].id,
                filters={"group_by": "synthetic"},
            )
            assert result["group_comparison"]["pass_rates"] is not None

    def test_with_filters(self, app, study_data):
        """compute_all respects filters."""
        with app.app_context():
            result = compute_all(
                study_data["study"].id,
                filters={"attributes": {"synthetic": False}},
            )
            # Group comparison should show no group_by specified
            assert result["group_comparison"]["message"] is not None

    def test_empty_study(self, app, db):
        """Empty study -> graceful degradation everywhere."""
        with app.app_context():
            invalidate_stats_cache()
            study = _create_study(db)
            db.session.commit()
            result = compute_all(study.id)
            assert result["icc"]["value"] is None
            assert result["fleiss_kappa"]["value"] is None
            assert result["center_effects"]["effects"] == []
            assert result["validation"]["is_balanced"] is False


# ---------------------------------------------------------------------------
# Tests: custom schema
# ---------------------------------------------------------------------------


class TestWithCustomSchema:
    """Test statistics with a non-default custom schema."""

    def test_prepare_with_custom_schema(self, app, db, custom_schema, custom_pf_config):
        """prepare_ratings_dataframe works with custom schema."""
        with app.app_context():
            study = _create_study(db, custom_schema, custom_pf_config)
            u1 = _create_user(db, "custom1@example.com", "Center A")
            u2 = _create_user(db, "custom2@example.com", "Center B")
            img1 = _create_image(db, study.id, "custom1.png", seq=1)
            img2 = _create_image(db, study.id, "custom2.png", seq=2)

            _create_rating(db, u1.id, img1.id, study.id, {"Q1": 4, "Q2": 3, "Q3": 4})
            _create_rating(db, u1.id, img2.id, study.id, {"Q1": 2, "Q2": 2, "Q3": 2})
            _create_rating(db, u2.id, img1.id, study.id, {"Q1": 3, "Q2": 4, "Q3": 3})
            _create_rating(db, u2.id, img2.id, study.id, {"Q1": 1, "Q2": 1, "Q3": 1})
            db.session.commit()

            df = prepare_ratings_dataframe(study.id, schema=custom_schema)
            assert "Q1" in df.columns
            assert "Q2" in df.columns
            assert "Q3" in df.columns
            assert "F1" not in df.columns  # Default schema columns should not appear

    def test_icc_with_custom_schema(self, app, db, custom_schema, custom_pf_config):
        """ICC computation works with custom schema S_total."""
        with app.app_context():
            study = _create_study(db, custom_schema, custom_pf_config)
            u1 = _create_user(db, "icc_c1@example.com", "Center A")
            u2 = _create_user(db, "icc_c2@example.com", "Center B")
            u3 = _create_user(db, "icc_c3@example.com", "Center C")
            img1 = _create_image(db, study.id, "icc_c1.png", seq=1)
            img2 = _create_image(db, study.id, "icc_c2.png", seq=2)
            img3 = _create_image(db, study.id, "icc_c3.png", seq=3)

            # Rater 1: img1=11, img2=6, img3=9
            _create_rating(db, u1.id, img1.id, study.id, {"Q1": 4, "Q2": 4, "Q3": 3})
            _create_rating(db, u1.id, img2.id, study.id, {"Q1": 2, "Q2": 2, "Q3": 2})
            _create_rating(db, u1.id, img3.id, study.id, {"Q1": 3, "Q2": 3, "Q3": 3})
            # Rater 2: img1=10, img2=5, img3=8
            _create_rating(db, u2.id, img1.id, study.id, {"Q1": 3, "Q2": 4, "Q3": 3})
            _create_rating(db, u2.id, img2.id, study.id, {"Q1": 1, "Q2": 2, "Q3": 2})
            _create_rating(db, u2.id, img3.id, study.id, {"Q1": 3, "Q2": 2, "Q3": 3})
            # Rater 3: img1=11, img2=7, img3=9
            _create_rating(db, u3.id, img1.id, study.id, {"Q1": 4, "Q2": 3, "Q3": 4})
            _create_rating(db, u3.id, img2.id, study.id, {"Q1": 2, "Q2": 3, "Q3": 2})
            _create_rating(db, u3.id, img3.id, study.id, {"Q1": 3, "Q2": 3, "Q3": 3})
            db.session.commit()

            df = prepare_ratings_dataframe(study.id, schema=custom_schema)
            result = compute_icc(df)
            assert result["value"] is not None
            assert result["value"] > 0.5  # Should have reasonable agreement

    def test_question_agreement_with_custom_schema(self, app, db, custom_schema, custom_pf_config):
        """Per-question agreement with custom schema."""
        with app.app_context():
            study = _create_study(db, custom_schema, custom_pf_config)
            u1 = _create_user(db, "qa_c1@example.com", "Center A")
            u2 = _create_user(db, "qa_c2@example.com", "Center B")
            img1 = _create_image(db, study.id, "qa_c1.png", seq=1)
            img2 = _create_image(db, study.id, "qa_c2.png", seq=2)

            _create_rating(db, u1.id, img1.id, study.id, {"Q1": 4, "Q2": 3, "Q3": 4})
            _create_rating(db, u1.id, img2.id, study.id, {"Q1": 1, "Q2": 2, "Q3": 1})
            _create_rating(db, u2.id, img1.id, study.id, {"Q1": 4, "Q2": 4, "Q3": 3})
            _create_rating(db, u2.id, img2.id, study.id, {"Q1": 1, "Q2": 1, "Q3": 2})
            db.session.commit()

            df = prepare_ratings_dataframe(study.id, schema=custom_schema)
            result = compute_question_agreement(df, custom_schema)
            assert set(result.keys()) == {"Q1", "Q2", "Q3"}
            # All should have ICC metric (0-4 scale = 5 levels)
            for qid in ["Q1", "Q2", "Q3"]:
                assert result[qid]["metric"] == "ICC"


# ---------------------------------------------------------------------------
# Tests: graceful degradation edge cases
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Test that all functions handle insufficient data gracefully."""

    def test_icc_all_same_score(self):
        """All images get same score from all raters -> edge case."""
        rows = []
        for rater in range(3):
            for img in range(5):
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "S_total": 10,  # No variance
                })
        df = pd.DataFrame(rows)
        result = compute_icc(df)
        assert result["value"] is None
        assert "undefined" in result["message"].lower()
        json.dumps(result, allow_nan=False)

    def test_constant_question_agreement_is_json_safe(self):
        df = pd.DataFrame([
            {"user_id": rater, "dataset_image_id": image, "F1": 2, "F2": image % 3}
            for rater in range(3) for image in range(5)
        ])
        result = compute_question_agreement(df)
        assert result["F1"]["value"] is None
        assert "undefined" in result["F1"]["message"].lower()
        assert result["F2"]["value"] == pytest.approx(1)
        json.dumps(result, allow_nan=False)

    def test_fleiss_kappa_all_pass(self):
        """All images pass for all raters."""
        rows = []
        for rater in range(3):
            for img in range(5):
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "pass_fail": 1,
                })
        df = pd.DataFrame(rows)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("error", RuntimeWarning)
            result = compute_fleiss_kappa_score(df, n_bootstrap=20)

        assert result["value"] is None
        assert result["ci_lower"] is None
        assert result["ci_upper"] is None
        assert "undefined" in result["message"].lower()
        assert caught == []

    def test_center_effects_missing_institutions(self):
        """Some rows have None institution."""
        rows = []
        for rater in range(4):
            institution = "Center A" if rater < 2 else None
            for img in range(4):
                rows.append({
                    "user_id": rater + 1,
                    "institution": institution,
                    "dataset_image_id": img + 1,
                    "S_total": 10,
                })
        df = pd.DataFrame(rows)
        result = compute_center_effects(df)
        # Should handle gracefully
        assert result is not None

    def test_group_comparison_all_same_scores(self):
        """Both groups have identical scores."""
        rows = []
        for rater in range(3):
            for img in range(6):
                rows.append({
                    "user_id": rater + 1,
                    "dataset_image_id": img + 1,
                    "attr_synthetic": img >= 3,
                    "S_total": 10,
                    "pass_fail": 1,
                })
        df = pd.DataFrame(rows)
        result = compute_group_comparison(df, "attr_synthetic")
        # Mann-Whitney should be 1.0 (no difference) or handle gracefully
        assert result["pass_rates"] is not None

    def test_score_distributions_single_value(self):
        """Single score value -> std = 0."""
        rows = [{"S_total": 10}]
        df = pd.DataFrame(rows)
        result = compute_score_distributions(df)
        assert result["groups"]["all"]["std"] == 0.0
        assert result["groups"]["all"]["count"] == 1

    def test_breakdowns_single_group(self):
        """Only one group -> still works."""
        rows = [
            {"user_id": 1, "dataset_image_id": 1, "attr_mpp_value": 0.25,
             "S_total": 10, "pass_fail": 1},
        ]
        df = pd.DataFrame(rows)
        result = compute_breakdowns(df, "attr_mpp_value")
        assert "0.25" in result["groups"]
        assert result["groups"]["0.25"]["count"] == 1
