"""Service for default rating schema and stratification configuration.

Provides:
- Default schema/stratification factories
- Schema validation
- Scoring (compute_total_score, compute_pass_fail)
- Conditional logic evaluation
- Completion status tracking
"""

# Valid comparison operators used in conditions and pass/fail rules
_OPERATORS = {
    "equals": lambda a, b: a == b,
    "less_than": lambda a, b: a < b,
    "less_than_or_equal": lambda a, b: a <= b,
    "greater_than": lambda a, b: a > b,
    "greater_than_or_equal": lambda a, b: a >= b,
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


def get_default_rating_schema() -> dict:
    """Return the Tier-2 protocol JSON rating schema.

    This schema defines the six feature-level questions (F1-F6),
    a conditional failure reason selector, and pass/fail rules.
    """
    return {
        "questions": [
            {
                "id": "F1",
                "type": "ordinal",
                "name": "Nuclear detail & cytology",
                "description": (
                    "Are nuclear size/shape, chromatin texture, and nucleoli "
                    "patterns consistent with real histology?"
                ),
                "min": 0,
                "max": 2,
                "labels": {
                    "0": "inconsistent",
                    "1": "borderline",
                    "2": "consistent",
                },
            },
            {
                "id": "F2",
                "type": "ordinal",
                "name": "Tissue architecture",
                "description": "Is the tissue organization coherent?",
                "min": 0,
                "max": 2,
                "labels": {
                    "0": "inconsistent",
                    "1": "borderline",
                    "2": "consistent",
                },
            },
            {
                "id": "F3",
                "type": "ordinal",
                "name": "Stroma / ECM realism",
                "description": "Is stromal/ECM texture consistent?",
                "min": 0,
                "max": 2,
                "labels": {
                    "0": "inconsistent",
                    "1": "borderline",
                    "2": "consistent",
                },
            },
            {
                "id": "F4",
                "type": "ordinal",
                "name": "Inflammation / TIL plausibility",
                "description": (
                    "Are inflammatory cells/TIL morphology and spatial "
                    "distribution consistent?"
                ),
                "min": 0,
                "max": 2,
                "labels": {
                    "0": "inconsistent",
                    "1": "borderline",
                    "2": "consistent",
                },
            },
            {
                "id": "F5",
                "type": "ordinal",
                "name": "Synthetic artifacts / hallucination markers",
                "description": "Are there visible synthetic artifacts?",
                "min": 0,
                "max": 2,
                "labels": {
                    "0": "clear artifacts",
                    "1": "possible/subtle",
                    "2": "none visible",
                },
            },
            {
                "id": "F6",
                "type": "ordinal",
                "name": "Global clinical usability",
                "description": (
                    "Would you trust this patch as evidence in "
                    "diagnostic reasoning?"
                ),
                "min": 0,
                "max": 2,
                "labels": {
                    "0": "no",
                    "1": "limited/uncertain",
                    "2": "yes",
                },
            },
        ],
        "failure_reason": {
            "id": "failure_reason",
            "enabled": True,
            "label": "Why did you rate this image so low?",
            "options": [
                "Nuclear/cytology inconsistency (F1)",
                "Architecture incoherence (F2)",
                "Stroma/ECM artifact (F3)",
                "TIL/inflammation artifact (F4)",
                "Obvious synthetic artifacts/repetition (F5)",
                "Other",
            ],
            "multi_select": False,
            "condition": {
                "type": "any_ordinal",
                "operator": "==",
                "value": 0,
            },
        },
        "visible_attributes": [],
    }


def get_default_pass_fail_config() -> dict:
    """Return the default pass/fail configuration.

    This is stored separately from the rating schema so it can be
    edited at any time without requiring the study to be in draft.
    """
    return {
        "enabled": True,
        "total_score_questions": ["F1", "F2", "F3", "F4", "F5", "F6"],
        "conditions": [
            {"field": "S_total", "operator": ">=", "value": 9},
            {"field": "F5", "operator": ">=", "value": 1},
        ],
    }


def validate_schema(schema: dict) -> list[str]:
    """Validate a rating schema and return a list of error messages.

    Returns an empty list if the schema is valid.

    Checks:
    - Schema must have a 'questions' list with at least one question
    - Each question must have an id, type, and name
    - Ordinal questions must have valid min/max (min < max, both integers >= 0)
    - Question IDs must be unique
    - failure_reason condition (if present) must have valid type and operator
    """
    errors = []

    if not isinstance(schema, dict):
        return ["Schema must be a dictionary."]

    # Validate questions
    questions = schema.get("questions")
    if not isinstance(questions, list) or len(questions) == 0:
        errors.append("Schema must have at least one question.")
        return errors

    seen_ids = set()
    ordinal_ids = set()
    all_question_ids = set()

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            errors.append(f"Question at index {i} must be a dictionary.")
            continue

        qid = q.get("id")
        qtype = q.get("type")
        qname = q.get("name")

        if not isinstance(qid, str) or not qid:
            errors.append(f"Question at index {i} is missing 'id'.")
            continue
        if not qtype:
            errors.append(f"Question at index {i} is missing 'type'.")
        if not isinstance(qname, str) or not qname:
            errors.append(f"Question at index {i} is missing 'name'.")

        if qid:
            if qid in seen_ids:
                errors.append(f"Duplicate question ID: '{qid}'.")
            seen_ids.add(qid)
            all_question_ids.add(qid)

        if qtype == "ordinal":
            qmin = q.get("min")
            qmax = q.get("max")
            valid_ordinal = True
            if qmin is None or qmax is None:
                errors.append(
                    f"Ordinal question '{qid}' must have 'min' and 'max'."
                )
                valid_ordinal = False
            elif type(qmin) is not int or type(qmax) is not int:
                errors.append(
                    f"Ordinal question '{qid}': min and max must be integers."
                )
                valid_ordinal = False
            elif qmin < 0:
                errors.append(
                    f"Ordinal question '{qid}': min must be >= 0."
                )
                valid_ordinal = False
            elif qmin >= qmax:
                errors.append(
                    f"Ordinal question '{qid}': min must be less than max."
                )
                valid_ordinal = False
            if valid_ordinal and qid:
                ordinal_ids.add(qid)
        elif qtype == "free_text":
            pass  # No additional validation for free text
        elif qtype:
            errors.append(
                f"Question '{qid}': unknown type '{qtype}'. "
                "Must be 'ordinal' or 'free_text'."
            )

    # Validate visible_attributes (optional)
    visible_attrs = schema.get("visible_attributes")
    if visible_attrs is not None:
        if not isinstance(visible_attrs, list):
            errors.append("visible_attributes must be a list of strings.")
        else:
            for i, attr in enumerate(visible_attrs):
                if not isinstance(attr, str):
                    errors.append(
                        f"visible_attributes[{i}] must be a string."
                    )

    # Validate failure_reason condition
    fr = schema.get("failure_reason")
    if fr is not None and not isinstance(fr, dict):
        errors.append('failure_reason must be a dictionary.')
    if fr and isinstance(fr, dict):
        # Validate options is a list of non-empty strings (if present)
        fr_options = fr.get("options")
        if fr_options is not None:
            if not isinstance(fr_options, list):
                errors.append("failure_reason options must be a list.")
            else:
                for i, opt in enumerate(fr_options):
                    if not isinstance(opt, str) or not opt.strip():
                        errors.append(
                            f"failure_reason options[{i}] must be a non-empty string."
                        )

        cond = fr.get("condition")
        if cond is not None and not isinstance(cond, dict):
            errors.append('failure_reason condition must be a dictionary.')
        if cond and isinstance(cond, dict):
            ctype = cond.get("type", "")
            if ctype not in ("any_ordinal", "specific_question"):
                errors.append(
                    f"failure_reason condition has unknown type '{ctype}'."
                )
            elif ctype == "specific_question":
                qid = cond.get("question_id", "")
                if not qid:
                    errors.append(
                        "failure_reason condition of type 'specific_question' "
                        "must have a non-empty 'question_id'."
                    )
                elif not isinstance(qid, str) or qid not in all_question_ids:
                    errors.append(
                        f"failure_reason condition references unknown "
                        f"question '{qid}'."
                    )
            op = cond.get("operator", "")
            if not isinstance(op, str) or op not in _OPERATORS:
                errors.append(
                    f"failure_reason condition has unknown operator '{op}'."
                )

    return errors


def validate_pass_fail_config(config: dict, schema: dict) -> list[str]:
    """Validate a pass_fail_config against a rating schema.

    Returns an empty list if the config is valid.

    Checks:
    - total_score_questions must reference existing ordinal question IDs
    - condition fields must be S_total or existing question IDs
    - condition operators must be valid
    """
    errors = []

    if not isinstance(config, dict):
        return ["pass_fail_config must be a dictionary."]

    questions = schema.get("questions", [])
    ordinal_ids = {q["id"] for q in questions if q.get("type") == "ordinal"}
    all_question_ids = {q["id"] for q in questions if q.get("id")}

    total_qs = config.get("total_score_questions", [])
    if not isinstance(total_qs, list):
        errors.append("total_score_questions must be a list.")
    else:
        for qid in total_qs:
            if not isinstance(qid, str) or qid not in ordinal_ids:
                errors.append(
                    f"pass_fail.total_score_questions references unknown "
                    f"ordinal question '{qid}'."
                )

    conditions = config.get("conditions", [])
    if not isinstance(conditions, list):
        errors.append("conditions must be a list.")
    else:
        for cond in conditions:
            if not isinstance(cond, dict):
                errors.append('Each pass_fail condition must be a dictionary.')
                continue
            field = cond.get("field", "")
            if not isinstance(field, str) or (field != "S_total" and field not in all_question_ids):
                errors.append(
                    f"pass_fail condition references unknown field '{field}'."
                )
            op = cond.get("operator", "")
            if not isinstance(op, str) or op not in _OPERATORS:
                errors.append(
                    f"pass_fail condition has unknown operator '{op}'."
                )

    return errors


def evaluate_condition(condition: dict, responses: dict, schema: dict) -> bool:
    """Evaluate a conditional logic expression against responses.

    Condition types:
    - "any_ordinal": True if ANY ordinal question in responses meets
      the comparison (operator, value).
    - "specific_question": True if a specific question (condition["question_id"])
      meets the comparison (operator, value).

    Args:
        condition: Dict with keys type, operator, value, and optionally question_id.
        responses: Dict mapping question IDs to response values.
        schema: The full rating schema (used to identify ordinal questions).

    Returns:
        True if the condition is met, False otherwise.
    """
    if not condition or not isinstance(condition, dict):
        return False

    ctype = condition.get("type", "")
    operator = condition.get("operator", "")
    value = condition.get("value")
    compare_fn = _OPERATORS.get(operator)

    if compare_fn is None or value is None:
        return False

    if ctype == "any_ordinal":
        ordinal_ids = get_ordinal_question_ids(schema)
        for qid in ordinal_ids:
            if qid in responses and responses[qid] is not None:
                try:
                    if compare_fn(responses[qid], value):
                        return True
                except (TypeError, ValueError):
                    continue
        return False

    elif ctype == "specific_question":
        qid = condition.get("question_id", "")
        if qid in responses and responses[qid] is not None:
            try:
                return compare_fn(responses[qid], value)
            except (TypeError, ValueError):
                return False
        return False

    return False


def compute_total_score(responses: dict, schema: dict, pass_fail_config: dict | None = None) -> int:
    """Compute the total score (S_total) from responses.

    Sums the values of the ordinal questions listed in
    pass_fail_config["total_score_questions"].

    Args:
        responses: Dict mapping question IDs to integer response values.
        schema: The full rating schema.
        pass_fail_config: The pass/fail configuration dict.

    Returns:
        The total score as an integer. Missing questions contribute 0.
    """
    if pass_fail_config is None:
        return 0
    total_qs = pass_fail_config.get("total_score_questions", [])

    total = 0
    for qid in total_qs:
        val = responses.get(qid)
        if val is not None:
            try:
                total += int(val)
            except (TypeError, ValueError):
                pass
    return total


def compute_pass_fail(responses: dict, schema: dict, pass_fail_config: dict | None = None) -> bool | None:
    """Determine pass/fail based on responses and pass_fail_config.

    All conditions in pass_fail_config["conditions"] must be satisfied
    (AND logic). Each condition specifies a field (either "S_total" for the
    total score, or a specific question ID), an operator, and a threshold value.

    Args:
        responses: Dict mapping question IDs to integer response values.
        schema: The full rating schema.
        pass_fail_config: The pass/fail configuration dict.

    Returns:
        True if the response passes all conditions, False if it fails,
        None if config is missing/disabled or data is incomplete.
    """
    if pass_fail_config is None:
        return None

    if not pass_fail_config.get("enabled", True):
        return None

    conditions = pass_fail_config.get("conditions", [])

    if not conditions:
        return True

    # If no ordinal questions have been answered yet, return None (indeterminate)
    total_qs = pass_fail_config.get("total_score_questions", [])
    has_any_answer = any(responses.get(qid) is not None for qid in total_qs)
    if total_qs and not has_any_answer:
        return None

    # If some but not all ordinal questions answered, return None (indeterminate)
    all_answered = all(responses.get(qid) is not None for qid in total_qs)
    if total_qs and has_any_answer and not all_answered:
        return None

    s_total = compute_total_score(responses, schema, pass_fail_config)

    for cond in conditions:
        field = cond.get("field", "")
        operator = cond.get("operator", "")
        value = cond.get("value")
        compare_fn = _OPERATORS.get(operator)

        if compare_fn is None or value is None:
            return False

        if field == "S_total":
            actual = s_total
        else:
            actual = responses.get(field)
            if actual is None:
                # Field not yet answered — treat as indeterminate, not a fail
                return None

        try:
            if not compare_fn(actual, value):
                return False
        except (TypeError, ValueError):
            return False

    return True


def get_completion_status(responses: dict | None, schema: dict) -> str:
    """Determine the completion status of a set of responses.

    Args:
        responses: Dict mapping question IDs to response values, or None.
        schema: The full rating schema.

    Returns:
        One of:
        - "not_started": responses is None or empty
        - "partial": some ordinal questions answered but not all
        - "complete": all ordinal questions answered
    """
    if not responses:
        return "not_started"

    ordinal_ids = get_ordinal_question_ids(schema)

    if not ordinal_ids:
        return "complete"

    answered = 0
    for qid in ordinal_ids:
        if qid in responses and responses[qid] is not None:
            answered += 1

    if answered == 0:
        return "not_started"
    elif answered < len(ordinal_ids):
        return "partial"
    else:
        return "complete"


def get_ordinal_question_ids(schema: dict) -> list[str]:
    """Extract IDs of all ordinal questions from the schema."""
    questions = schema.get("questions", [])
    return [q["id"] for q in questions if q.get("type") == "ordinal"]


def get_question_by_id(schema: dict, question_id: str) -> dict | None:
    """Find a question definition by its ID, or None if not found."""
    for q in schema.get("questions", []):
        if q.get("id") == question_id:
            return q
    return None
