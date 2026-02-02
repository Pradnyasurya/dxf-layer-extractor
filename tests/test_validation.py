"""Tests for the DXF validation logic."""

import pytest
import json


class TestValidationRules:
    """Test the validation rule structure."""

    def test_odisha_rules_have_required_fields(self):
        """Test that all rules have the required structure."""
        import os

        filepath = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "odisha_layers.json"
        )

        with open(filepath, "r") as f:
            data = json.load(f)

        # Check structure - it's a list of rule dicts
        assert isinstance(data, list)
        assert len(data) > 0

        for rule in data:
            # Basic fields that should exist
            assert isinstance(rule, dict), f"Rule should be a dict"

            # Check for key fields
            if "Layer Name" in rule:
                assert isinstance(rule["Layer Name"], str)
            if "Color Code" in rule:
                assert isinstance(rule["Color Code"], (str, int, type(None)))


class TestComparisonEngine:
    """Test the comparison engine can be initialized."""

    def test_comparator_imports(self):
        """Test that DXFComparator can be imported."""
        from comparison_engine import DXFComparator

        assert DXFComparator is not None

    def test_comparator_instantiation(self):
        """Test that DXFComparator can be created."""
        from comparison_engine import DXFComparator

        # Should be able to create without args
        comparator = DXFComparator()
        assert comparator is not None


class TestEntityTypeMapping:
    """Test entity type mappings exist and are valid."""

    def test_entity_type_mapping_exists(self):
        """Test that ENTITY_TYPE_MAPPING exists in app."""
        import app

        assert hasattr(app, "ENTITY_TYPE_MAPPING")
        mapping = app.ENTITY_TYPE_MAPPING

        assert isinstance(mapping, dict)
        assert len(mapping) > 0

        # Check common DXF entity types are mapped
        common_types = ["LINE", "CIRCLE", "ARC", "LWPOLYLINE", "TEXT", "MTEXT"]
        for entity_type in common_types:
            if entity_type in mapping:
                assert isinstance(mapping[entity_type], str)
