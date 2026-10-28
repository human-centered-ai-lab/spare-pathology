"""Statistics engine for Tier-2 reader-study analysis.

Computes:
- ICC (intraclass correlation) for S_total
- Fleiss' kappa for pass/fail classification
- Per-question agreement (ICC or kappa)
- Center (institution) effects via MixedLM
- Group comparison with Mann-Whitney tests (any two-group attribute)
- Failure-mode distribution by center
- Score distributions, optionally grouped by a dynamic attribute
- Breakdowns by any attribute column
- Fully-crossed design validation
"""

import hashlib
import json
import time
import warnings

import numpy as np
import pandas as pd
import pingouin as pg
from scipy import stats as scipy_stats
from statsmodels.regression.mixed_linear_model import MixedLM
from statsmodels.stats.inter_rater import fleiss_kappa

from app import db
from app.models import DatasetImage, StudyParticipant, Rating, User
from app.services.schema_service import (
    get_ordinal_question_ids,
    compute_pass_fail,
    compute_total_score,
    get_default_rating_schema,
)

# ─── Simple TTL cache for compute_all results ────────────────────────────────
_stats_cache: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 60  # seconds


def _finite_or_none(value):
    """Return a finite float or None for undefined/NaN statistics."""
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _cache_key(study_id, filters, schema, pass_fail_config):
    """Build a stable cache key from the arguments."""
    raw = json.dumps({"pid": study_id, "f": filters, "s": schema, "p": pass_fail_config}, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def invalidate_stats_cache(study_id=None):
    """Clear cached statistics. Call after ratings/submissions change."""
    if study_id is None:
        _stats_cache.clear()
    else:
        to_remove = [k for k in _stats_cache if k.startswith(f"{study_id}_")]
        for k in to_remove:
            del _stats_cache[k]


def prepare_ratings_dataframe(study_id, filters=None, schema=None, pass_fail_config=None):
    """Query ratings into a pandas DataFrame with computed columns.

    Args:
        study_id: The study ID to query ratings for.
        filters: Optional dict with filter keys:
            - submitted_only (bool): Only include users who have submitted
            - user_ids (list[int]): Filter to specific user IDs
            - attributes (dict): Filter by attribute values,
              e.g. {"mpp_value": 0.5, "synthetic": True}
        schema: The rating schema to use. If None, uses the study's schema
            or falls back to the default schema.
        pass_fail_config: The pass/fail configuration. If None, uses the
            study's pass_fail_config.

    Returns:
        A pandas DataFrame with columns:
            user_id, institution, dataset_image_id, S_total, pass_fail,
            attr_* columns (one per attribute key), responses,
            and individual question responses (e.g. F1, F2, ...)
        Returns an empty DataFrame if no ratings match.
    """
    if filters is None:
        filters = {}

    # Build the query — fetch attributes JSON instead of individual columns
    query = (
        db.session.query(
            Rating.user_id,
            User.institution,
            Rating.dataset_image_id,
            Rating.study_id,
            Rating.responses,
            DatasetImage.attributes,
        )
        .join(User, Rating.user_id == User.id)
        .join(DatasetImage, Rating.dataset_image_id == DatasetImage.id)
        .filter(Rating.study_id == study_id)
        .filter(User.is_test_user.is_(False))
    )

    # Apply submitted_only filter
    if filters.get("submitted_only"):
        from sqlalchemy import select

        submitted_user_ids = (
            select(StudyParticipant.user_id)
            .where(
                StudyParticipant.study_id == study_id,
                StudyParticipant.submitted.is_(True),
            )
            .scalar_subquery()
        )
        query = query.filter(Rating.user_id.in_(submitted_user_ids))

    # Apply user-level filters
    if filters.get("user_ids"):
        query = query.filter(Rating.user_id.in_(filters["user_ids"]))

    results = query.all()

    if not results:
        return pd.DataFrame()

    # Get the schema and pass_fail_config
    if schema is None or pass_fail_config is None:
        from app.models import Study

        study = db.session.get(Study, study_id)
        if schema is None:
            if study and study.rating_schema:
                schema = study.rating_schema
            else:
                schema = get_default_rating_schema()
        if pass_fail_config is None:
            if study and study.pass_fail_config:
                pass_fail_config = study.pass_fail_config
            else:
                pass_fail_config = None

    ordinal_ids = get_ordinal_question_ids(schema)

    # Build rows
    rows = []
    for row in results:
        responses = row.responses or {}
        s_total = compute_total_score(responses, schema, pass_fail_config)
        pf = compute_pass_fail(responses, schema, pass_fail_config)
        attributes = row.attributes or {}

        record = {
            "user_id": row.user_id,
            "institution": row.institution,
            "dataset_image_id": row.dataset_image_id,
            "S_total": s_total,
            "pass_fail": int(pf) if pf is not None else None,
            "responses": responses,
        }

        # Flatten attributes into attr_* columns
        for attr_key, attr_val in attributes.items():
            record[f"attr_{attr_key}"] = attr_val

        # Add individual question responses
        for qid in ordinal_ids:
            record[qid] = responses.get(qid)

        rows.append(record)

    df = pd.DataFrame(rows)

    # Apply attribute filters as post-load filtering on attr_* columns
    attr_filters = filters.get("attributes", {})
    for attr_key, attr_val in attr_filters.items():
        col_name = f"attr_{attr_key}"
        if col_name in df.columns:
            # Support both single values and lists/sets of values
            if isinstance(attr_val, (set, list)):
                df = df[df[col_name].isin(attr_val)]
            else:
                df = df[df[col_name] == attr_val]
        else:
            # Column doesn't exist — no rows match
            return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    return df


def compute_icc(df):
    """Compute ICC(3,1) for S_total using pingouin.

    ICC3 = two-way mixed effects, consistency, single measures.

    Args:
        df: DataFrame with columns user_id, dataset_image_id, S_total

    Returns:
        dict with keys: value, ci_lower, ci_upper, message
        Returns value=None with message if insufficient data.
    """
    if df.empty:
        return {"value": None, "ci_lower": None, "ci_upper": None,
                "message": "No data available for ICC computation"}

    n_raters = df["user_id"].nunique()
    n_targets = df["dataset_image_id"].nunique()

    if n_raters < 2:
        return {"value": None, "ci_lower": None, "ci_upper": None,
                "message": "ICC requires at least 2 raters"}

    if n_targets < 2:
        return {"value": None, "ci_lower": None, "ci_upper": None,
                "message": "ICC requires at least 2 images"}

    # pingouin requires at least 5 non-missing values
    if len(df) < 5:
        return {"value": None, "ci_lower": None, "ci_upper": None,
                "message": "ICC requires at least 5 ratings"}

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            icc_df = pg.intraclass_corr(
                data=df,
                targets="dataset_image_id",
                raters="user_id",
                ratings="S_total",
            )
        # Pick ICC3 row (Type = "ICC3")
        icc3 = icc_df[icc_df["Type"] == "ICC3"]
        if icc3.empty:
            return {"value": None, "ci_lower": None, "ci_upper": None,
                    "message": "ICC3 not found in results"}

        row = icc3.iloc[0]
        ci = row["CI95%"]
        value = _finite_or_none(row["ICC"])

        return {
            "value": value,
            "ci_lower": _finite_or_none(ci[0]),
            "ci_upper": _finite_or_none(ci[1]),
            "message": None if value is not None else "ICC is undefined for constant or degenerate ratings",
        }
    except Exception as e:
        return {"value": None, "ci_lower": None, "ci_upper": None,
                "message": f"ICC computation failed: {str(e)}"}


def compute_fleiss_kappa_score(df, n_bootstrap=200, random_state=42):
    """Compute Fleiss' kappa for pass/fail classification with bootstrap CI.

    Args:
        df: DataFrame with columns user_id, dataset_image_id, pass_fail (0 or 1)
        n_bootstrap: Number of bootstrap iterations for CI
        random_state: Random state for reproducibility

    Returns:
        dict with keys: value, ci_lower, ci_upper, message
    """
    if df.empty:
        return {"value": None, "ci_lower": None, "ci_upper": None,
                "message": "No data available for Fleiss' kappa computation"}

    n_raters = df["user_id"].nunique()
    if n_raters < 2:
        return {"value": None, "ci_lower": None, "ci_upper": None,
                "message": "Fleiss' kappa requires at least 2 raters"}

    n_targets = df["dataset_image_id"].nunique()
    if n_targets < 2:
        return {"value": None, "ci_lower": None, "ci_upper": None,
                "message": "Fleiss' kappa requires at least 2 images"}

    # Filter out rows with indeterminate pass_fail (incomplete ratings)
    df = df[df["pass_fail"].notna()].copy()
    if df.empty:
        return {"value": None, "ci_lower": None, "ci_upper": None,
                "message": "No complete pass/fail data available"}

    n_raters = df["user_id"].nunique()
    if n_raters < 2:
        return {"value": None, "ci_lower": None, "ci_upper": None,
                "message": "Fleiss' kappa requires at least 2 raters with complete data"}

    try:
        kappa_val = _compute_fleiss_from_df(df)
        kappa_value = _finite_or_none(kappa_val)
        if kappa_value is None:
            return {
                "value": None,
                "ci_lower": None,
                "ci_upper": None,
                "message": "Fleiss' kappa is undefined for degenerate pass/fail data",
            }

        # Bootstrap CI
        rng = np.random.RandomState(random_state)
        image_ids = df["dataset_image_id"].unique()
        bootstrap_kappas = []

        for _ in range(n_bootstrap):
            sampled_ids = rng.choice(image_ids, size=len(image_ids), replace=True)
            # Need to remap image IDs for duplicates in bootstrap
            new_rows = []
            counter = 0
            for img_id in sampled_ids:
                sub = df[df["dataset_image_id"] == img_id].copy()
                sub["dataset_image_id"] = counter
                new_rows.append(sub)
                counter += 1
            if new_rows:
                boot_df = pd.concat(new_rows, ignore_index=True)
                try:
                    k = _compute_fleiss_from_df(boot_df)
                    if k is not None and np.isfinite(k):
                        bootstrap_kappas.append(k)
                except Exception:
                    continue

        if len(bootstrap_kappas) >= 10:
            ci_lower = float(np.percentile(bootstrap_kappas, 2.5))
            ci_upper = float(np.percentile(bootstrap_kappas, 97.5))
        else:
            ci_lower = None
            ci_upper = None

        return {
            "value": kappa_value,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "message": None,
        }
    except Exception as e:
        return {"value": None, "ci_lower": None, "ci_upper": None,
                "message": f"Fleiss' kappa computation failed: {str(e)}"}


def _compute_fleiss_from_df(df, categories=None):
    """Compute Fleiss' kappa from a DataFrame with user_id, dataset_image_id, pass_fail.

    Args:
        df: DataFrame with user_id, dataset_image_id, pass_fail.
        categories: Optional ordered list of valid category values.
            Defaults to [0, 1] for pass/fail-style data.

    Creates a subjects x categories matrix and applies statsmodels fleiss_kappa.
    """
    if categories is None:
        categories = [0, 1]

    # Preserve order and uniqueness for deterministic column order.
    categories = list(dict.fromkeys(categories))
    if len(categories) < 2:
        return None

    observed_categories = set(df["pass_fail"].dropna().unique().tolist())
    unknown_categories = observed_categories - set(categories)
    if unknown_categories:
        # Avoid silently dropping unexpected category values.
        return None

    # Create pivot: rows=images, columns=categories.
    # Count how many raters assigned each category to each image.
    pivot = df.pivot_table(
        index="dataset_image_id",
        columns="pass_fail",
        values="user_id",
        aggfunc="count",
        fill_value=0,
    )

    # Ensure all configured categories are present.
    for cat in categories:
        if cat not in pivot.columns:
            pivot[cat] = 0

    pivot = pivot[categories]
    table = pivot.values

    if table.shape[0] < 1:
        return None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return fleiss_kappa(table, method="fleiss")


def compute_question_agreement(df, schema=None):
    """Compute per-question ICC or kappa for individual ordinal questions.

    For ordinal questions with more than 2 levels, computes ICC.
    For binary questions (2 levels), computes Fleiss' kappa.

    Args:
        df: DataFrame with individual question columns
        schema: Rating schema. If None, uses the default schema.

    Returns:
        dict mapping question_id -> {value, ci_lower, ci_upper, metric, message}
    """
    if schema is None:
        schema = get_default_rating_schema()

    ordinal_ids = get_ordinal_question_ids(schema)
    questions_by_id = {q["id"]: q for q in schema.get("questions", [])}
    results = {}

    for qid in ordinal_ids:
        if qid not in df.columns:
            results[qid] = {
                "value": None, "ci_lower": None, "ci_upper": None,
                "metric": None, "message": f"Column {qid} not found in data",
            }
            continue

        q_df = df[["user_id", "dataset_image_id", qid]].dropna(subset=[qid]).copy()

        if q_df.empty:
            results[qid] = {
                "value": None, "ci_lower": None, "ci_upper": None,
                "metric": None, "message": f"No data for question {qid}",
            }
            continue

        n_raters = q_df["user_id"].nunique()
        n_targets = q_df["dataset_image_id"].nunique()

        if n_raters < 2 or n_targets < 2:
            results[qid] = {
                "value": None, "ci_lower": None, "ci_upper": None,
                "metric": None,
                "message": f"Insufficient data for question {qid} (need >= 2 raters and >= 2 images)",
            }
            continue

        q_info = questions_by_id.get(qid, {})
        q_min = q_info.get("min", 0)
        q_max = q_info.get("max", 2)
        n_levels = q_max - q_min + 1

        if n_levels <= 2:
            # Use kappa for binary
            kappa_df = q_df.rename(columns={qid: "pass_fail"})
            kappa_categories = [q_min, q_max]
            kappa_result = _compute_fleiss_from_df(
                kappa_df,
                categories=kappa_categories,
            )
            kappa_value = _finite_or_none(kappa_result)
            results[qid] = {
                "value": kappa_value,
                "ci_lower": None,
                "ci_upper": None,
                "metric": "kappa",
                "message": None if kappa_value is not None else f"Kappa is undefined for {qid}",
            }
        else:
            # Use ICC for ordinal with > 2 levels
            if len(q_df) < 5:
                results[qid] = {
                    "value": None, "ci_lower": None, "ci_upper": None,
                    "metric": "ICC",
                    "message": f"ICC requires at least 5 ratings for {qid}",
                }
                continue

            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    icc_df = pg.intraclass_corr(
                        data=q_df,
                        targets="dataset_image_id",
                        raters="user_id",
                        ratings=qid,
                    )
                icc3 = icc_df[icc_df["Type"] == "ICC3"]
                if not icc3.empty:
                    row = icc3.iloc[0]
                    ci = row["CI95%"]
                    value = _finite_or_none(row["ICC"])
                    results[qid] = {
                        "value": value,
                        "ci_lower": _finite_or_none(ci[0]),
                        "ci_upper": _finite_or_none(ci[1]),
                        "metric": "ICC",
                        "message": None if value is not None else f"ICC is undefined for {qid}",
                    }
                else:
                    results[qid] = {
                        "value": None, "ci_lower": None, "ci_upper": None,
                        "metric": "ICC", "message": f"ICC3 not found for {qid}",
                    }
            except Exception as e:
                results[qid] = {
                    "value": None, "ci_lower": None, "ci_upper": None,
                    "metric": "ICC", "message": f"ICC computation failed for {qid}: {str(e)}",
                }

    return results


def compute_center_effects(df):
    """Compute center (institution) effects using MixedLM.

    Model: S_total ~ C(institution) with random intercept for dataset_image_id.

    Args:
        df: DataFrame with columns institution, dataset_image_id, S_total

    Returns:
        dict with keys: effects (list of {center, effect, ci_lower, ci_upper}),
        converged (bool), message (str or None)
    """
    if df.empty:
        return {"effects": [], "converged": False,
                "message": "No data available for center effects"}

    n_centers = df["institution"].nunique()
    if n_centers < 2:
        return {"effects": [], "converged": False,
                "message": "Center effects require at least 2 centers (institutions)"}

    n_images = df["dataset_image_id"].nunique()
    if n_images < 2:
        return {"effects": [], "converged": False,
                "message": "Center effects require at least 2 images"}

    try:
        # Drop rows with missing institution
        work_df = df.dropna(subset=["institution"]).copy()
        if work_df["institution"].nunique() < 2:
            return {"effects": [], "converged": False,
                    "message": "Center effects require at least 2 centers after removing missing institutions"}

        # Create dummy variables for institution (fixed effect)
        work_df["institution_cat"] = pd.Categorical(work_df["institution"])

        # Fit MixedLM: S_total ~ C(institution) with random intercept for image
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = MixedLM.from_formula(
                "S_total ~ C(institution_cat)",
                data=work_df,
                groups=work_df["dataset_image_id"],
            )
            result = model.fit(reml=True)

        effects = []
        # Extract fixed effects for each center
        centers = sorted(work_df["institution"].unique())
        reference_center = centers[0]

        # Reference center effect is the intercept
        effects.append({
            "center": reference_center,
            "effect": float(result.params["Intercept"]),
            "ci_lower": float(result.conf_int().loc["Intercept", 0]),
            "ci_upper": float(result.conf_int().loc["Intercept", 1]),
            "is_reference": True,
        })

        # Other centers relative to reference
        for center in centers[1:]:
            param_name = f"C(institution_cat)[T.{center}]"
            if param_name in result.params:
                effects.append({
                    "center": center,
                    "effect": float(result.params[param_name]),
                    "ci_lower": float(result.conf_int().loc[param_name, 0]),
                    "ci_upper": float(result.conf_int().loc[param_name, 1]),
                    "is_reference": False,
                })

        return {
            "effects": effects,
            "converged": result.converged,
            "message": None,
        }
    except Exception as e:
        return {"effects": [], "converged": False,
                "message": f"MixedLM computation failed: {str(e)}"}


def compute_group_comparison(df, group_col):
    """Compare two groups on pass rates and scores using Mann-Whitney.

    Args:
        df: DataFrame with S_total, pass_fail, and the group column.
        group_col: Column name to split on (must have exactly 2 unique values).

    Returns:
        dict with keys:
            - pass_rates: {group_a_label: rate, group_b_label: rate}
            - score_comparison: {group_a_label: {mean, std}, group_b_label: {mean, std}, mannwhitney_p}
            - per_question: dict of question_id -> {group_a_label_mean, group_b_label_mean, mannwhitney_p}
            - message: str or None
    """
    if df.empty:
        return {
            "pass_rates": None,
            "score_comparison": None,
            "per_question": None,
            "message": "No data available for group comparison",
        }

    if group_col is None or group_col not in df.columns:
        return {
            "pass_rates": None,
            "score_comparison": None,
            "per_question": None,
            "message": f"Group column '{group_col}' not found in data",
        }

    unique_vals = df[group_col].dropna().unique()
    if len(unique_vals) != 2:
        return {
            "pass_rates": None,
            "score_comparison": None,
            "per_question": None,
            "message": f"Group comparison requires exactly 2 groups, found {len(unique_vals)}",
        }

    group_a_label, group_b_label = sorted(unique_vals, key=str)
    group_a_label_str = str(group_a_label)
    group_b_label_str = str(group_b_label)

    group_a_df = df[df[group_col] == group_a_label]
    group_b_df = df[df[group_col] == group_b_label]

    if group_a_df.empty or group_b_df.empty:
        return {
            "pass_rates": None,
            "score_comparison": None,
            "per_question": None,
            "message": "Need data in both groups for comparison",
        }

    # Pass rates (exclude incomplete ratings with None pass_fail)
    a_pf = group_a_df["pass_fail"].dropna()
    b_pf = group_b_df["pass_fail"].dropna()
    a_pass_rate = float(a_pf.mean()) if len(a_pf) > 0 else None
    b_pass_rate = float(b_pf.mean()) if len(b_pf) > 0 else None

    # S_total comparison with Mann-Whitney
    a_scores = group_a_df["S_total"].values
    b_scores = group_b_df["S_total"].values

    try:
        mw_stat, mw_p = scipy_stats.mannwhitneyu(
            a_scores, b_scores, alternative="two-sided"
        )
        mw_p = float(mw_p)
    except ValueError:
        mw_p = None

    score_comparison = {
        group_a_label_str: {
            "mean": float(np.mean(a_scores)),
            "std": float(np.std(a_scores, ddof=1)) if len(a_scores) > 1 else 0.0,
        },
        group_b_label_str: {
            "mean": float(np.mean(b_scores)),
            "std": float(np.std(b_scores, ddof=1)) if len(b_scores) > 1 else 0.0,
        },
        "mannwhitney_p": mw_p,
    }

    # Per-question comparison
    per_question = {}
    # Find ordinal question columns (those that aren't standard or attr_* columns)
    standard_cols = {
        "user_id", "institution", "dataset_image_id",
        "S_total", "pass_fail", "responses",
    }
    question_cols = [
        c for c in df.columns
        if c not in standard_cols and not c.startswith("attr_")
    ]

    for qid in question_cols:
        a_vals = group_a_df[qid].dropna().values
        b_vals = group_b_df[qid].dropna().values

        if len(a_vals) == 0 or len(b_vals) == 0:
            per_question[qid] = {
                f"{group_a_label_str}_mean": None,
                f"{group_b_label_str}_mean": None,
                "mannwhitney_p": None,
            }
            continue

        try:
            _, q_p = scipy_stats.mannwhitneyu(
                a_vals, b_vals, alternative="two-sided"
            )
            q_p = float(q_p)
        except ValueError:
            q_p = None

        per_question[qid] = {
            f"{group_a_label_str}_mean": float(np.mean(a_vals)),
            f"{group_b_label_str}_mean": float(np.mean(b_vals)),
            "mannwhitney_p": q_p,
        }

    return {
        "pass_rates": {group_a_label_str: a_pass_rate, group_b_label_str: b_pass_rate},
        "score_comparison": score_comparison,
        "per_question": per_question,
        "message": None,
    }


def compute_failure_modes(df, schema=None):
    """Compute failure-mode distribution grouped by center.

    Failure reason is extracted from responses when pass_fail == 0.

    Args:
        df: DataFrame with columns institution, pass_fail, responses
        schema: Rating schema (used to determine failure reason field)

    Returns:
        dict with keys:
            - by_center: dict of center -> {reason -> count}
            - overall: dict of reason -> count
            - message: str or None
    """
    if df.empty:
        return {"by_center": {}, "overall": {}, "message": "No data available"}

    # Filter to failed ratings
    failed_df = df[df["pass_fail"] == 0]
    if failed_df.empty:
        return {"by_center": {}, "overall": {},
                "message": "No failed ratings to analyze"}

    # Extract failure reasons
    overall = {}
    by_center = {}

    for _, row in failed_df.iterrows():
        responses = row.get("responses", {})
        if not isinstance(responses, dict):
            continue

        reason = responses.get("failure_reason", "Unknown")
        if reason is None:
            reason = "Unknown"
        reasons = reason if isinstance(reason, list) else [reason]

        # By center
        center = row.get("institution", "Unknown") or "Unknown"
        if center not in by_center:
            by_center[center] = {}
        for r in reasons:
            overall[r] = overall.get(r, 0) + 1
            by_center[center][r] = by_center[center].get(r, 0) + 1

    return {"by_center": by_center, "overall": overall, "message": None}


def compute_score_distributions(df, group_col=None):
    """Compute score distributions, optionally grouped by a dynamic attribute column.

    Args:
        df: DataFrame with S_total and optionally the group column.
        group_col: Optional column name to group by. If None or not in df,
            returns a single "all" group.

    Returns:
        dict with keys:
            - groups: {group_label: {scores, mean, median, std, q1, q3, count}}
            - message: str or None
    """
    if df.empty:
        return {"groups": {},
                "message": "No data available for score distributions"}

    result_groups = {}

    if group_col is not None and group_col in df.columns:
        for group_val, group_df in df.groupby(group_col, dropna=False):
            label = str(group_val) if group_val is not None else "Unknown"
            scores = group_df["S_total"].values
            result_groups[label] = {
                "scores": scores.tolist(),
                "mean": float(np.mean(scores)),
                "median": float(np.median(scores)),
                "std": float(np.std(scores, ddof=1)) if len(scores) > 1 else 0.0,
                "q1": float(np.percentile(scores, 25)),
                "q3": float(np.percentile(scores, 75)),
                "count": len(scores),
            }
    else:
        scores = df["S_total"].values
        result_groups["all"] = {
            "scores": scores.tolist(),
            "mean": float(np.mean(scores)),
            "median": float(np.median(scores)),
            "std": float(np.std(scores, ddof=1)) if len(scores) > 1 else 0.0,
            "q1": float(np.percentile(scores, 25)),
            "q3": float(np.percentile(scores, 75)),
            "count": len(scores),
        }

    return {"groups": result_groups, "message": None}


def compute_breakdowns(df, group_col):
    """Compute breakdowns by a grouping column.

    Args:
        df: DataFrame
        group_col: Column name to group by

    Returns:
        dict with keys:
            - groups: dict of group_value -> {
                mean_score, std_score, pass_rate, count, n_raters, n_images
              }
            - message: str or None
    """
    if df.empty:
        return {"groups": {}, "message": "No data available for breakdowns"}

    if group_col not in df.columns:
        return {"groups": {},
                "message": f"Column '{group_col}' not found in data"}

    groups = {}
    for name, group_df in df.groupby(group_col, dropna=False):
        group_key = str(name) if name is not None else "Unknown"
        scores = group_df["S_total"].values
        pf_valid = group_df["pass_fail"].dropna()
        groups[group_key] = {
            "mean_score": float(np.mean(scores)),
            "std_score": float(np.std(scores, ddof=1)) if len(scores) > 1 else 0.0,
            "pass_rate": float(pf_valid.mean()) if len(pf_valid) > 0 else None,
            "count": len(group_df),
            "n_raters": int(group_df["user_id"].nunique()),
            "n_images": int(group_df["dataset_image_id"].nunique()),
        }

    return {"groups": groups, "message": None}


def validate_fully_crossed(df):
    """Check if the design is fully crossed (all raters scored all images).

    Args:
        df: DataFrame with columns user_id, dataset_image_id

    Returns:
        dict with keys:
            - is_balanced: bool
            - n_raters: int
            - n_images: int
            - expected_ratings: int
            - actual_ratings: int
            - missing_ratings: int
            - completeness: float (0-1)
            - warnings: list of str
    """
    if df.empty:
        return {
            "is_balanced": False,
            "n_raters": 0,
            "n_images": 0,
            "expected_ratings": 0,
            "actual_ratings": 0,
            "missing_ratings": 0,
            "completeness": 0.0,
            "warnings": ["No data available"],
        }

    raters = df["user_id"].unique()
    images = df["dataset_image_id"].unique()
    n_raters = len(raters)
    n_images = len(images)
    expected = n_raters * n_images

    # Count unique (user, image) pairs
    actual = df.groupby(["user_id", "dataset_image_id"]).ngroups
    missing = expected - actual
    completeness = actual / expected if expected > 0 else 0.0

    warnings_list = []
    is_balanced = missing == 0

    if not is_balanced:
        warnings_list.append(
            f"Design is not fully crossed: {missing} of {expected} "
            f"expected ratings are missing ({completeness:.1%} complete)"
        )

        # Find which raters are incomplete
        ratings_per_rater = df.groupby("user_id")["dataset_image_id"].nunique()
        incomplete_raters = ratings_per_rater[ratings_per_rater < n_images]
        if not incomplete_raters.empty:
            warnings_list.append(
                f"{len(incomplete_raters)} rater(s) have incomplete ratings"
            )

    return {
        "is_balanced": is_balanced,
        "n_raters": n_raters,
        "n_images": n_images,
        "expected_ratings": expected,
        "actual_ratings": actual,
        "missing_ratings": missing,
        "completeness": completeness,
        "warnings": warnings_list,
    }


def compute_all(study_id, filters=None, schema=None, pass_fail_config=None):
    """Orchestrator: compute all statistics for a study.

    Results are cached for 60 seconds to avoid recomputing on every request.

    Args:
        study_id: The study ID
        filters: Optional filter dict (see prepare_ratings_dataframe).
            Additional key:
            - group_by (str): Attribute key to group by (e.g. "mpp_value",
              "synthetic"). The corresponding DataFrame column will be
              "attr_{group_by}".
        schema: Optional schema override
        pass_fail_config: Optional pass/fail configuration override

    Returns:
        dict with all computed statistics
    """
    if schema is None or pass_fail_config is None:
        from app.models import Study

        study = db.session.get(Study, study_id)
        if schema is None:
            if study and study.rating_schema:
                schema = study.rating_schema
            else:
                schema = get_default_rating_schema()
        if pass_fail_config is None and study:
            pass_fail_config = study.pass_fail_config

    # Check cache
    key = f"{study_id}_{_cache_key(study_id, filters, schema, pass_fail_config)}"
    cached = _stats_cache.get(key)
    if cached is not None:
        ts, result = cached
        if time.time() - ts < _CACHE_TTL:
            return result

    if filters is None:
        filters = {}

    df = prepare_ratings_dataframe(study_id, filters=filters, schema=schema, pass_fail_config=pass_fail_config)

    # Determine grouping column from filters
    group_by = filters.get("group_by")
    group_col = f"attr_{group_by}" if group_by else None

    result = {
        "validation": validate_fully_crossed(df),
        "icc": compute_icc(df),
        "fleiss_kappa": compute_fleiss_kappa_score(df),
        "question_agreement": compute_question_agreement(df, schema=schema),
        "center_effects": compute_center_effects(df),
        "failure_modes": compute_failure_modes(df, schema=schema),
        "score_distributions": compute_score_distributions(df, group_col=group_col),
    }

    # Add group comparison if group_col is valid and has exactly 2 groups
    if group_col and not df.empty and group_col in df.columns:
        n_groups = df[group_col].dropna().nunique()
        if n_groups == 2:
            result["group_comparison"] = compute_group_comparison(df, group_col)
        else:
            result["group_comparison"] = {
                "pass_rates": None,
                "score_comparison": None,
                "per_question": None,
                "message": f"Group comparison requires exactly 2 groups, found {n_groups}",
            }
        result["breakdowns"] = compute_breakdowns(df, group_col)
    else:
        result["group_comparison"] = {
            "pass_rates": None,
            "score_comparison": None,
            "per_question": None,
            "message": "No group_by attribute specified" if not group_by else f"Column 'attr_{group_by}' not found in data",
        }
        result["breakdowns"] = {"groups": {}, "message": "No group_by attribute specified" if not group_by else f"Column 'attr_{group_by}' not found in data"}

    _stats_cache[key] = (time.time(), result)
    return result
