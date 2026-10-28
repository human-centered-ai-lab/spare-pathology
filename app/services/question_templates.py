"""Utilities for resolving question text attribute placeholders."""

from __future__ import annotations

import re


PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def extract_placeholder_names(text: str | None) -> list[str]:
    """Return ordered unique placeholder names from a question template."""
    if not text:
        return []

    seen: set[str] = set()
    names: list[str] = []

    for match in PLACEHOLDER_PATTERN.finditer(text):
        name = match.group(1).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)

    return names


def get_question_attribute_names(schema: dict | None) -> list[str]:
    """Return ordered unique attribute names referenced by question templates."""
    seen: set[str] = set()
    names: list[str] = []

    questions = (schema or {}).get('questions', []) or []
    for question in questions:
        for text in (question.get('name'), question.get('description')):
            for name in extract_placeholder_names(text):
                if name in seen:
                    continue
                seen.add(name)
                names.append(name)

    return names
