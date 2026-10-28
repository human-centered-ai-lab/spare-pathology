"""Tests for schema_service: validation, scoring, conditional logic, completion status."""


from app.services.schema_service import (
    compute_pass_fail,
    compute_total_score,
    evaluate_condition,
    get_completion_status,
    get_default_rating_schema,
    get_default_pass_fail_config,
    validate_schema,
    validate_pass_fail_config,
)


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _default_schema():
    """Return the default schema for convenience."""
    return get_default_rating_schema()


def _default_pf_config():
    """Return the default pass_fail_config for convenience."""
    return get_default_pass_fail_config()


def _make_minimal_schema(questions=None, failure_reason=None):
    """Build a minimal schema dict for testing."""
    schema = {
        "questions": questions or [
            {
                "id": "Q1",
                "type": "ordinal",
                "name": "Question 1",
                "min": 0,
                "max": 3,
                "labels": {"0": "bad", "1": "ok", "2": "good", "3": "great"},
            },
        ],
    }
    if failure_reason is not None:
        schema["failure_reason"] = failure_reason
    return schema


def _make_pf_config(total_score_questions=None, conditions=None, enabled=True):
    """Build a pass_fail_config dict for testing."""
    config = {"enabled": enabled}
    if total_score_questions is not None:
        config["total_score_questions"] = total_score_questions
    else:
        config["total_score_questions"] = []
    if conditions is not None:
        config["conditions"] = conditions
    else:
        config["conditions"] = []
    return config


# ---------------------------------------------------------------------------
# Tests: get_default_rating_schema
# ---------------------------------------------------------------------------

class TestDefaultSchema:
    """Tests that the default schema has the expected structure."""

    def test_has_six_ordinal_questions(self):
        schema = _default_schema()
        questions = schema["questions"]
        assert len(questions) == 6
        for q in questions:
            assert q["type"] == "ordinal"

    def test_question_ids_f1_through_f6(self):
        schema = _default_schema()
        ids = [q["id"] for q in schema["questions"]]
        assert ids == ["F1", "F2", "F3", "F4", "F5", "F6"]

    def test_has_failure_reason_field(self):
        schema = _default_schema()
        fr = schema["failure_reason"]
        assert fr["id"] == "failure_reason"
        assert isinstance(fr["options"], list)
        assert len(fr["options"]) >= 2  # At least some options plus "Other"
        assert "Other" in fr["options"]

    def test_failure_reason_condition(self):
        schema = _default_schema()
        cond = schema["failure_reason"]["condition"]
        assert cond["type"] == "any_ordinal"
        assert cond["operator"] == "=="
        assert cond["value"] == 0

    def test_no_pass_fail_in_schema(self):
        """Default schema should NOT contain pass_fail (moved to pass_fail_config)."""
        schema = _default_schema()
        assert "pass_fail" not in schema


class TestDefaultPassFailConfig:
    """Tests for get_default_pass_fail_config()."""

    def test_has_total_score_questions(self):
        config = _default_pf_config()
        assert config["total_score_questions"] == ["F1", "F2", "F3", "F4", "F5", "F6"]

    def test_has_conditions(self):
        config = _default_pf_config()
        assert len(config["conditions"]) == 2

    def test_conditions_detail(self):
        config = _default_pf_config()
        conditions = config["conditions"]
        assert conditions[0] == {"field": "S_total", "operator": ">=", "value": 9}
        assert conditions[1] == {"field": "F5", "operator": ">=", "value": 1}

    def test_enabled_by_default(self):
        config = _default_pf_config()
        assert config["enabled"] is True


# ---------------------------------------------------------------------------
# Tests: validate_schema
# ---------------------------------------------------------------------------

class TestValidateSchema:
    """Tests for validate_schema()."""

    def test_default_schema_is_valid(self):
        errors = validate_schema(_default_schema())
        assert errors == []

    def test_empty_questions_list(self):
        errors = validate_schema({"questions": []})
        assert len(errors) > 0
        assert any("at least one question" in e for e in errors)

    def test_missing_questions_key(self):
        errors = validate_schema({})
        assert len(errors) > 0

    def test_not_a_dict(self):
        errors = validate_schema("not a dict")
        assert len(errors) > 0
        assert any("dictionary" in e for e in errors)

    def test_question_missing_id(self):
        schema = _make_minimal_schema(questions=[
            {"type": "ordinal", "name": "No ID", "min": 0, "max": 2},
        ])
        errors = validate_schema(schema)
        assert any("missing 'id'" in e for e in errors)

    def test_question_missing_type(self):
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "name": "No Type", "min": 0, "max": 2},
        ])
        errors = validate_schema(schema)
        assert any("missing 'type'" in e for e in errors)

    def test_question_missing_name(self):
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "ordinal", "min": 0, "max": 2},
        ])
        errors = validate_schema(schema)
        assert any("missing 'name'" in e for e in errors)

    def test_duplicate_question_ids(self):
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "ordinal", "name": "Q1", "min": 0, "max": 2},
            {"id": "Q1", "type": "ordinal", "name": "Q1 dup", "min": 0, "max": 2},
        ])
        errors = validate_schema(schema)
        assert any("Duplicate" in e for e in errors)

    def test_ordinal_missing_min_max(self):
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "ordinal", "name": "No min/max"},
        ])
        errors = validate_schema(schema)
        assert any("min" in e and "max" in e for e in errors)

    def test_ordinal_min_not_less_than_max(self):
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "ordinal", "name": "Bad range", "min": 5, "max": 5},
        ])
        errors = validate_schema(schema)
        assert any("less than max" in e for e in errors)

    def test_ordinal_negative_min(self):
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "ordinal", "name": "Neg min", "min": -1, "max": 2},
        ])
        errors = validate_schema(schema)
        assert any("min must be >= 0" in e for e in errors)

    def test_ordinal_non_integer_min_max(self):
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "ordinal", "name": "Float", "min": 0.5, "max": 2.5},
        ])
        errors = validate_schema(schema)
        assert any("integers" in e for e in errors)

    def test_unknown_question_type(self):
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "multiple_choice", "name": "MC"},
        ])
        errors = validate_schema(schema)
        assert any("unknown type" in e for e in errors)

    def test_free_text_valid(self):
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "ordinal", "name": "Ordinal", "min": 0, "max": 2},
            {"id": "T1", "type": "free_text", "name": "Comments"},
        ])
        errors = validate_schema(schema)
        assert errors == []

    def test_failure_reason_unknown_condition_type(self):
        schema = _make_minimal_schema(
            failure_reason={
                "id": "fr",
                "options": ["A", "B"],
                "multi_select": False,
                "condition": {"type": "bad_type", "operator": "equals", "value": 0},
            },
        )
        errors = validate_schema(schema)
        assert any("bad_type" in e for e in errors)

    def test_failure_reason_unknown_operator(self):
        schema = _make_minimal_schema(
            failure_reason={
                "id": "fr",
                "options": ["A"],
                "multi_select": False,
                "condition": {"type": "any_ordinal", "operator": "NOPE", "value": 0},
            },
        )
        errors = validate_schema(schema)
        assert any("NOPE" in e for e in errors)

    def test_question_not_dict(self):
        schema = {"questions": ["not a dict"]}
        errors = validate_schema(schema)
        assert any("must be a dictionary" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests: validate_pass_fail_config
# ---------------------------------------------------------------------------

class TestValidatePassFailConfig:
    """Tests for validate_pass_fail_config()."""

    def test_default_config_is_valid(self):
        schema = _default_schema()
        config = _default_pf_config()
        errors = validate_pass_fail_config(config, schema)
        assert errors == []

    def test_references_unknown_question(self):
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "ordinal", "name": "Q1", "min": 0, "max": 2},
        ])
        config = _make_pf_config(total_score_questions=["Q1", "Q99"])
        errors = validate_pass_fail_config(config, schema)
        assert any("Q99" in e for e in errors)

    def test_condition_unknown_field(self):
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "ordinal", "name": "Q1", "min": 0, "max": 2},
        ])
        config = _make_pf_config(
            total_score_questions=["Q1"],
            conditions=[{"field": "MISSING", "operator": ">=", "value": 5}],
        )
        errors = validate_pass_fail_config(config, schema)
        assert any("MISSING" in e for e in errors)

    def test_condition_unknown_operator(self):
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "ordinal", "name": "Q1", "min": 0, "max": 2},
        ])
        config = _make_pf_config(
            total_score_questions=["Q1"],
            conditions=[{"field": "S_total", "operator": "NOPE", "value": 5}],
        )
        errors = validate_pass_fail_config(config, schema)
        assert any("NOPE" in e for e in errors)

    def test_s_total_is_valid_field(self):
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "ordinal", "name": "Q1", "min": 0, "max": 2},
        ])
        config = _make_pf_config(
            total_score_questions=["Q1"],
            conditions=[{"field": "S_total", "operator": ">=", "value": 1}],
        )
        errors = validate_pass_fail_config(config, schema)
        assert errors == []

    def test_not_a_dict(self):
        errors = validate_pass_fail_config("not a dict", _default_schema())
        assert any("dictionary" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests: compute_total_score
# ---------------------------------------------------------------------------

class TestComputeTotalScore:
    """Tests for compute_total_score()."""

    def test_all_max_scores(self):
        """All F1-F6 at max (2) -> S_total = 12."""
        schema = _default_schema()
        config = _default_pf_config()
        responses = {"F1": 2, "F2": 2, "F3": 2, "F4": 2, "F5": 2, "F6": 2}
        assert compute_total_score(responses, schema, config) == 12

    def test_all_zero_scores(self):
        """All F1-F6 at 0 -> S_total = 0."""
        schema = _default_schema()
        config = _default_pf_config()
        responses = {"F1": 0, "F2": 0, "F3": 0, "F4": 0, "F5": 0, "F6": 0}
        assert compute_total_score(responses, schema, config) == 0

    def test_mixed_scores(self):
        """F1=2, F2=1, F3=2, F4=1, F5=2, F6=1 -> S_total = 9."""
        schema = _default_schema()
        config = _default_pf_config()
        responses = {"F1": 2, "F2": 1, "F3": 2, "F4": 1, "F5": 2, "F6": 1}
        assert compute_total_score(responses, schema, config) == 9

    def test_missing_question_contributes_zero(self):
        """Missing questions contribute 0 to total."""
        schema = _default_schema()
        config = _default_pf_config()
        responses = {"F1": 2, "F2": 2}  # F3-F6 missing
        assert compute_total_score(responses, schema, config) == 4

    def test_empty_responses(self):
        schema = _default_schema()
        config = _default_pf_config()
        assert compute_total_score({}, schema, config) == 0

    def test_custom_schema_subset_of_questions(self):
        """Custom schema with only 2 questions in total_score."""
        schema = _make_minimal_schema(
            questions=[
                {"id": "A", "type": "ordinal", "name": "A", "min": 0, "max": 5},
                {"id": "B", "type": "ordinal", "name": "B", "min": 0, "max": 5},
                {"id": "C", "type": "ordinal", "name": "C", "min": 0, "max": 5},
            ],
        )
        config = _make_pf_config(total_score_questions=["A", "B"])
        responses = {"A": 3, "B": 4, "C": 5}
        assert compute_total_score(responses, schema, config) == 7  # 3 + 4, not 12

    def test_none_response_value_ignored(self):
        schema = _default_schema()
        config = _default_pf_config()
        responses = {"F1": 2, "F2": None, "F3": 2, "F4": 2, "F5": 2, "F6": 2}
        assert compute_total_score(responses, schema, config) == 10

    def test_no_config_returns_zero(self):
        """No pass_fail_config returns 0."""
        schema = {"questions": [{"id": "Q1", "type": "ordinal", "name": "Q", "min": 0, "max": 2}]}
        assert compute_total_score({"Q1": 2}, schema) == 0
        assert compute_total_score({"Q1": 2}, schema, None) == 0


# ---------------------------------------------------------------------------
# Tests: compute_pass_fail
# ---------------------------------------------------------------------------

class TestComputePassFail:
    """Tests for compute_pass_fail()."""

    def test_pass_all_max(self):
        """All max scores -> S_total=12 >= 9 and F5=2 >= 1 -> pass."""
        schema = _default_schema()
        config = _default_pf_config()
        responses = {"F1": 2, "F2": 2, "F3": 2, "F4": 2, "F5": 2, "F6": 2}
        assert compute_pass_fail(responses, schema, config) is True

    def test_pass_borderline(self):
        """S_total=9, F5=1 -> just barely passes both conditions."""
        schema = _default_schema()
        config = _default_pf_config()
        responses = {"F1": 2, "F2": 1, "F3": 2, "F4": 1, "F5": 1, "F6": 2}
        assert compute_total_score(responses, schema, config) == 9
        assert compute_pass_fail(responses, schema, config) is True

    def test_fail_low_total(self):
        """S_total < 9 -> fail."""
        schema = _default_schema()
        config = _default_pf_config()
        responses = {"F1": 1, "F2": 1, "F3": 1, "F4": 1, "F5": 2, "F6": 1}
        assert compute_total_score(responses, schema, config) == 7
        assert compute_pass_fail(responses, schema, config) is False

    def test_fail_f5_zero(self):
        """S_total=10 but F5=0 -> fail on F5 >= 1 condition."""
        schema = _default_schema()
        config = _default_pf_config()
        responses = {"F1": 2, "F2": 2, "F3": 2, "F4": 2, "F5": 0, "F6": 2}
        assert compute_total_score(responses, schema, config) == 10
        assert compute_pass_fail(responses, schema, config) is False

    def test_fail_both_conditions(self):
        """S_total < 9 AND F5=0 -> fail."""
        schema = _default_schema()
        config = _default_pf_config()
        responses = {"F1": 0, "F2": 0, "F3": 0, "F4": 0, "F5": 0, "F6": 0}
        assert compute_pass_fail(responses, schema, config) is False

    def test_pass_no_conditions(self):
        """Config with empty conditions -> always pass."""
        schema = _make_minimal_schema()
        config = _make_pf_config(total_score_questions=["Q1"], conditions=[])
        assert compute_pass_fail({"Q1": 0}, schema, config) is True

    def test_custom_schema_different_threshold(self):
        """Custom schema with different pass/fail threshold."""
        schema = _make_minimal_schema(
            questions=[
                {"id": "A", "type": "ordinal", "name": "A", "min": 0, "max": 10},
                {"id": "B", "type": "ordinal", "name": "B", "min": 0, "max": 10},
            ],
        )
        config = _make_pf_config(
            total_score_questions=["A", "B"],
            conditions=[{"field": "S_total", "operator": ">=", "value": 15}],
        )
        # 8 + 8 = 16 >= 15 -> pass
        assert compute_pass_fail({"A": 8, "B": 8}, schema, config) is True
        # 7 + 7 = 14 < 15 -> fail
        assert compute_pass_fail({"A": 7, "B": 7}, schema, config) is False

    def test_pass_fail_with_missing_field_response(self):
        """If a condition references a question with no response, result is indeterminate (None)."""
        schema = _default_schema()
        config = _default_pf_config()
        # F5 not in responses -> F5 >= 1 cannot be evaluated
        responses = {"F1": 2, "F2": 2, "F3": 2, "F4": 2, "F6": 2}
        assert compute_pass_fail(responses, schema, config) is None

    def test_no_config_returns_none(self):
        """No pass_fail_config -> returns None."""
        schema = {"questions": [{"id": "Q1", "type": "ordinal", "name": "Q", "min": 0, "max": 2}]}
        assert compute_pass_fail({"Q1": 1}, schema) is None
        assert compute_pass_fail({"Q1": 1}, schema, None) is None


# ---------------------------------------------------------------------------
# Tests: evaluate_condition
# ---------------------------------------------------------------------------

class TestEvaluateCondition:
    """Tests for evaluate_condition()."""

    def test_any_ordinal_equals_zero_true(self):
        """any_ordinal equals 0: True when any ordinal is 0."""
        schema = _default_schema()
        condition = {"type": "any_ordinal", "operator": "equals", "value": 0}
        responses = {"F1": 2, "F2": 0, "F3": 2, "F4": 2, "F5": 2, "F6": 2}
        assert evaluate_condition(condition, responses, schema) is True

    def test_any_ordinal_equals_zero_false(self):
        """any_ordinal equals 0: False when no ordinal is 0."""
        schema = _default_schema()
        condition = {"type": "any_ordinal", "operator": "equals", "value": 0}
        responses = {"F1": 2, "F2": 1, "F3": 2, "F4": 1, "F5": 2, "F6": 1}
        assert evaluate_condition(condition, responses, schema) is False

    def test_any_ordinal_less_than(self):
        """any_ordinal less_than 2: True when any ordinal < 2."""
        schema = _default_schema()
        condition = {"type": "any_ordinal", "operator": "less_than", "value": 2}
        responses = {"F1": 2, "F2": 2, "F3": 1, "F4": 2, "F5": 2, "F6": 2}
        assert evaluate_condition(condition, responses, schema) is True

    def test_any_ordinal_less_than_false(self):
        schema = _default_schema()
        condition = {"type": "any_ordinal", "operator": "less_than", "value": 2}
        responses = {"F1": 2, "F2": 2, "F3": 2, "F4": 2, "F5": 2, "F6": 2}
        assert evaluate_condition(condition, responses, schema) is False

    def test_specific_question_equals(self):
        schema = _default_schema()
        condition = {"type": "specific_question", "question_id": "F5", "operator": "equals", "value": 0}
        responses = {"F5": 0}
        assert evaluate_condition(condition, responses, schema) is True

    def test_specific_question_not_equals(self):
        schema = _default_schema()
        condition = {"type": "specific_question", "question_id": "F5", "operator": "equals", "value": 0}
        responses = {"F5": 2}
        assert evaluate_condition(condition, responses, schema) is False

    def test_specific_question_less_than(self):
        schema = _default_schema()
        condition = {"type": "specific_question", "question_id": "F5", "operator": "less_than", "value": 2}
        responses = {"F5": 1}
        assert evaluate_condition(condition, responses, schema) is True

    def test_specific_question_greater_than_or_equal(self):
        schema = _default_schema()
        condition = {
            "type": "specific_question",
            "question_id": "F1",
            "operator": "greater_than_or_equal",
            "value": 2,
        }
        responses = {"F1": 2}
        assert evaluate_condition(condition, responses, schema) is True
        responses2 = {"F1": 1}
        assert evaluate_condition(condition, responses2, schema) is False

    def test_specific_question_missing_from_responses(self):
        """If the question is not in responses, condition is False."""
        schema = _default_schema()
        condition = {"type": "specific_question", "question_id": "F5", "operator": "equals", "value": 0}
        responses = {"F1": 2}
        assert evaluate_condition(condition, responses, schema) is False

    def test_empty_condition(self):
        assert evaluate_condition({}, {}, _default_schema()) is False

    def test_none_condition(self):
        assert evaluate_condition(None, {}, _default_schema()) is False

    def test_unknown_operator(self):
        schema = _default_schema()
        condition = {"type": "any_ordinal", "operator": "NOPE", "value": 0}
        responses = {"F1": 0}
        assert evaluate_condition(condition, responses, schema) is False

    def test_any_ordinal_with_empty_responses(self):
        schema = _default_schema()
        condition = {"type": "any_ordinal", "operator": "equals", "value": 0}
        assert evaluate_condition(condition, {}, schema) is False

    def test_any_ordinal_ignores_free_text(self):
        """any_ordinal should only check ordinal questions, not free text."""
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "ordinal", "name": "Q1", "min": 0, "max": 2},
            {"id": "T1", "type": "free_text", "name": "Comments"},
        ])
        condition = {"type": "any_ordinal", "operator": "equals", "value": 0}
        # T1 has value 0 but is free_text, not ordinal
        responses = {"Q1": 2, "T1": 0}
        assert evaluate_condition(condition, responses, schema) is False

    def test_specific_question_with_gte_operator(self):
        """Test >= alias operator."""
        schema = _default_schema()
        condition = {"type": "specific_question", "question_id": "F1", "operator": ">=", "value": 1}
        assert evaluate_condition(condition, {"F1": 1}, schema) is True
        assert evaluate_condition(condition, {"F1": 0}, schema) is False

    def test_any_ordinal_with_none_response(self):
        """None response values are skipped."""
        schema = _default_schema()
        condition = {"type": "any_ordinal", "operator": "equals", "value": 0}
        responses = {"F1": None, "F2": None}
        assert evaluate_condition(condition, responses, schema) is False


# ---------------------------------------------------------------------------
# Tests: get_completion_status
# ---------------------------------------------------------------------------

class TestGetCompletionStatus:
    """Tests for get_completion_status()."""

    def test_not_started_none(self):
        schema = _default_schema()
        assert get_completion_status(None, schema) == "not_started"

    def test_not_started_empty(self):
        schema = _default_schema()
        assert get_completion_status({}, schema) == "not_started"

    def test_complete_all_answered(self):
        schema = _default_schema()
        responses = {"F1": 2, "F2": 1, "F3": 2, "F4": 1, "F5": 2, "F6": 1}
        assert get_completion_status(responses, schema) == "complete"

    def test_partial_some_answered(self):
        schema = _default_schema()
        responses = {"F1": 2, "F2": 1}
        assert get_completion_status(responses, schema) == "partial"

    def test_partial_with_free_text_only(self):
        """Free text doesn't count toward completion; ordinal matters."""
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "ordinal", "name": "Q1", "min": 0, "max": 2},
            {"id": "Q2", "type": "ordinal", "name": "Q2", "min": 0, "max": 2},
            {"id": "T1", "type": "free_text", "name": "Comments"},
        ])
        # Only free text answered
        responses = {"T1": "some comment"}
        assert get_completion_status(responses, schema) == "not_started"

    def test_complete_ignores_free_text(self):
        """Completion only checks ordinal questions; free text is irrelevant."""
        schema = _make_minimal_schema(questions=[
            {"id": "Q1", "type": "ordinal", "name": "Q1", "min": 0, "max": 2},
            {"id": "T1", "type": "free_text", "name": "Comments"},
        ])
        responses = {"Q1": 1}  # free text not answered, but that's fine
        assert get_completion_status(responses, schema) == "complete"

    def test_not_started_with_none_values(self):
        """If all ordinal responses are None, it's not_started."""
        schema = _default_schema()
        responses = {"F1": None, "F2": None, "F3": None, "F4": None, "F5": None, "F6": None}
        assert get_completion_status(responses, schema) == "not_started"

    def test_partial_with_some_none_values(self):
        schema = _default_schema()
        responses = {"F1": 2, "F2": None, "F3": 1, "F4": None, "F5": None, "F6": None}
        assert get_completion_status(responses, schema) == "partial"

    def test_complete_with_no_ordinal_questions(self):
        """Schema with only free_text questions -> always complete."""
        schema = _make_minimal_schema(questions=[
            {"id": "T1", "type": "free_text", "name": "Comments"},
        ])
        assert get_completion_status({}, schema) == "not_started"
        assert get_completion_status({"T1": "text"}, schema) == "complete"

    def test_custom_schema_three_ordinal(self):
        schema = _make_minimal_schema(questions=[
            {"id": "A", "type": "ordinal", "name": "A", "min": 0, "max": 5},
            {"id": "B", "type": "ordinal", "name": "B", "min": 0, "max": 5},
            {"id": "C", "type": "ordinal", "name": "C", "min": 0, "max": 5},
        ])
        assert get_completion_status({"A": 3}, schema) == "partial"
        assert get_completion_status({"A": 3, "B": 4}, schema) == "partial"
        assert get_completion_status({"A": 3, "B": 4, "C": 5}, schema) == "complete"


# ---------------------------------------------------------------------------
# Tests: Scoring with custom schemas
# ---------------------------------------------------------------------------

class TestCustomSchemaScoring:
    """Tests scoring and pass/fail with non-default schemas."""

    def test_wide_scale_schema(self):
        """Schema with 0-10 scale questions."""
        schema = _make_minimal_schema(
            questions=[
                {"id": "X1", "type": "ordinal", "name": "X1", "min": 0, "max": 10},
                {"id": "X2", "type": "ordinal", "name": "X2", "min": 0, "max": 10},
            ],
        )
        config = _make_pf_config(
            total_score_questions=["X1", "X2"],
            conditions=[{"field": "S_total", "operator": ">=", "value": 15}],
        )
        responses = {"X1": 8, "X2": 9}
        assert compute_total_score(responses, schema, config) == 17
        assert compute_pass_fail(responses, schema, config) is True

        responses2 = {"X1": 5, "X2": 5}
        assert compute_total_score(responses2, schema, config) == 10
        assert compute_pass_fail(responses2, schema, config) is False

    def test_single_question_schema(self):
        """Schema with a single ordinal question."""
        schema = _make_minimal_schema(
            questions=[
                {"id": "ONLY", "type": "ordinal", "name": "Only Q", "min": 0, "max": 3},
            ],
        )
        config = _make_pf_config(
            total_score_questions=["ONLY"],
            conditions=[{"field": "ONLY", "operator": ">=", "value": 2}],
        )
        assert compute_pass_fail({"ONLY": 2}, schema, config) is True
        assert compute_pass_fail({"ONLY": 1}, schema, config) is False

    def test_multiple_operator_types_in_conditions(self):
        """Test various operator types in pass/fail conditions."""
        schema = _make_minimal_schema(
            questions=[
                {"id": "A", "type": "ordinal", "name": "A", "min": 0, "max": 5},
            ],
        )
        config = _make_pf_config(
            total_score_questions=["A"],
            conditions=[{"field": "A", "operator": "greater_than", "value": 2}],
        )
        assert compute_pass_fail({"A": 3}, schema, config) is True
        assert compute_pass_fail({"A": 2}, schema, config) is False

    def test_less_than_or_equal_operator(self):
        schema = _make_minimal_schema(
            questions=[
                {"id": "A", "type": "ordinal", "name": "A", "min": 0, "max": 5},
            ],
        )
        config = _make_pf_config(
            total_score_questions=["A"],
            conditions=[{"field": "A", "operator": "less_than_or_equal", "value": 3}],
        )
        assert compute_pass_fail({"A": 3}, schema, config) is True
        assert compute_pass_fail({"A": 4}, schema, config) is False
