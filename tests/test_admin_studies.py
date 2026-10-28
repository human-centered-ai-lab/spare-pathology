"""Tests for the schema service functions."""

from app.services.schema_service import get_default_rating_schema


class TestSchemaService:
    """Test the schema service functions."""

    def test_default_rating_schema_has_six_questions(self):
        """Default rating schema has 6 questions (F1-F6)."""
        schema = get_default_rating_schema()
        assert len(schema['questions']) == 6
        ids = [q['id'] for q in schema['questions']]
        assert ids == ['F1', 'F2', 'F3', 'F4', 'F5', 'F6']

    def test_default_rating_schema_has_failure_reason(self):
        """Default rating schema includes failure_reason config."""
        schema = get_default_rating_schema()
        assert 'failure_reason' in schema
        assert schema['failure_reason']['id'] == 'failure_reason'
        assert len(schema['failure_reason']['options']) == 6

    def test_default_rating_schema_no_pass_fail(self):
        """Default rating schema does NOT include pass_fail (moved to pass_fail_config)."""
        schema = get_default_rating_schema()
        assert 'pass_fail' not in schema

    def test_default_rating_schema_has_visible_attributes(self):
        """Default rating schema includes visible_attributes."""
        schema = get_default_rating_schema()
        assert 'visible_attributes' in schema
        assert isinstance(schema['visible_attributes'], list)
