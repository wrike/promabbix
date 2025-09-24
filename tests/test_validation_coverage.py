#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import pytest
import json
import yaml
from pathlib import Path
import sys
from unittest.mock import patch, mock_open
import tempfile
import os

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.validation import (
    ConfigValidator, ValidationError, SchemaValidator, 
    CrossReferenceValidator, ConfigAnalyzer
)


class TestValidationErrorHandling:
    """Test error handling scenarios in validation."""

    def test_schema_file_not_found_error(self, temp_directory):
        """Test ValidationError raised when schema file doesn't exist."""
        non_existent_schema = str(temp_directory / "non_existent_schema.yaml")
        
        with pytest.raises(ValidationError) as excinfo:
            ConfigValidator(schema_path=non_existent_schema)
        
        assert "Schema file not found" in str(excinfo.value)
        assert non_existent_schema in str(excinfo.value)
        assert "Ensure the unified schema file exists" in str(excinfo.value)

    def test_schema_file_invalid_yaml_error(self, temp_directory):
        """Test ValidationError raised when schema file has invalid YAML."""
        invalid_yaml_schema = temp_directory / "invalid_schema.yaml"
        invalid_yaml_schema.write_text("invalid: yaml: content: [missing closing bracket")
        
        with pytest.raises(ValidationError) as excinfo:
            ConfigValidator(schema_path=str(invalid_yaml_schema))
        
        assert "Invalid format in schema file" in str(excinfo.value)
        assert "Check the schema file for valid YAML/JSON syntax" in str(excinfo.value)

    def test_schema_file_invalid_json_error(self, temp_directory):
        """Test ValidationError raised when schema file has invalid JSON."""
        invalid_json_schema = temp_directory / "invalid_schema.json"
        invalid_json_schema.write_text('{"invalid": "json", "missing": }')
        
        with pytest.raises(ValidationError) as excinfo:
            ConfigValidator(schema_path=str(invalid_json_schema))
        
        assert "Invalid format in schema file" in str(excinfo.value)
        assert "Check the schema file for valid YAML/JSON syntax" in str(excinfo.value)

    def test_multiple_validation_errors_combined(self):
        """Test that multiple validation errors are combined into one error."""
        config_with_multiple_errors = {
            "groups": [
                {
                    "name": "invalid_group_name",  # Error 1: Invalid enum
                    "rules": [
                        {
                            "expr": "test_expr"
                            # Missing required field - Error 2
                        }
                    ]
                }
            ]
            # Missing required zabbix section - Error 3
        }
        
        validator = ConfigValidator()
        with pytest.raises(ValidationError) as excinfo:
            validator.validate_config(config_with_multiple_errors)
        
        error_message = str(excinfo.value)
        assert "Multiple validation errors found" in error_message
        assert "Error 1:" in error_message


class TestSchemaValidatorSuggestions:
    """Test suggestion generation in SchemaValidator."""

    def test_suggestions_for_required_field_error(self):
        """Test suggestion generation for missing required fields."""
        from jsonschema import ValidationError as JsonSchemaError
        
        schema = {"type": "object", "required": ["field1"]}
        validator = SchemaValidator(schema)
        
        # Mock jsonschema ValidationError
        mock_error = JsonSchemaError("'field1' is a required property")
        mock_error.validator = 'required'
        mock_error.schema = schema
        mock_error.absolute_path = []
        
        suggestions = validator.generate_suggestions(mock_error)
        assert any("Add the required field" in suggestion for suggestion in suggestions)

    def test_suggestions_for_type_error(self):
        """Test suggestion generation for type errors."""
        from jsonschema import ValidationError as JsonSchemaError
        
        schema = {"type": "string"}
        validator = SchemaValidator(schema)
        
        mock_error = JsonSchemaError("123 is not of type 'string'")
        mock_error.validator = 'type'
        mock_error.schema = schema
        mock_error.absolute_path = ['field1']
        
        suggestions = validator.generate_suggestions(mock_error)
        assert any("Change value to type: string" in suggestion for suggestion in suggestions)

    def test_suggestions_for_enum_error(self):
        """Test suggestion generation for enum violations."""
        from jsonschema import ValidationError as JsonSchemaError
        
        schema = {"enum": ["value1", "value2", "value3"]}
        validator = SchemaValidator(schema)
        
        mock_error = JsonSchemaError("'invalid_value' is not one of ['value1', 'value2', 'value3']")
        mock_error.validator = 'enum'
        mock_error.schema = schema
        mock_error.absolute_path = ['field1']
        
        suggestions = validator.generate_suggestions(mock_error)
        assert any("Use one of the allowed values: value1, value2, value3" in suggestion for suggestion in suggestions)

    def test_suggestions_for_pattern_error(self):
        """Test suggestion generation for pattern violations."""
        from jsonschema import ValidationError as JsonSchemaError
        
        schema = {"pattern": "^[A-Z]$"}
        validator = SchemaValidator(schema)
        
        mock_error = JsonSchemaError("'abc' does not match '^[A-Z]$'")
        mock_error.validator = 'pattern'
        mock_error.schema = schema
        mock_error.absolute_path = ['field1']
        
        suggestions = validator.generate_suggestions(mock_error)
        assert any("Value must match pattern: ^[A-Z]$" in suggestion for suggestion in suggestions)

    def test_suggestions_for_additional_properties_error(self):
        """Test suggestion generation for additional properties violations."""
        from jsonschema import ValidationError as JsonSchemaError
        
        schema = {"additionalProperties": False}
        validator = SchemaValidator(schema)
        
        mock_error = JsonSchemaError("Additional properties are not allowed ('extra_field' was unexpected)")
        mock_error.validator = 'additionalProperties'
        mock_error.schema = schema
        mock_error.absolute_path = []
        
        suggestions = validator.generate_suggestions(mock_error)
        assert any("Remove unexpected properties or check property names for typos" in suggestion for suggestion in suggestions)

    def test_suggestions_for_min_items_error(self):
        """Test suggestion generation for minItems violations."""
        from jsonschema import ValidationError as JsonSchemaError
        
        schema = {"minItems": 2}
        validator = SchemaValidator(schema)
        
        mock_error = JsonSchemaError("[] is too short")
        mock_error.validator = 'minItems'
        mock_error.schema = schema
        mock_error.absolute_path = ['array_field']
        
        suggestions = validator.generate_suggestions(mock_error)
        assert any("Array must have at least 2 items" in suggestion for suggestion in suggestions)

    def test_suggestions_for_max_items_error(self):
        """Test suggestion generation for maxItems violations."""
        from jsonschema import ValidationError as JsonSchemaError
        
        schema = {"maxItems": 5}
        validator = SchemaValidator(schema)
        
        mock_error = JsonSchemaError("[1,2,3,4,5,6] is too long")
        mock_error.validator = 'maxItems'
        mock_error.schema = schema
        mock_error.absolute_path = ['array_field']
        
        suggestions = validator.generate_suggestions(mock_error)
        assert any("Array must have at most 5 items" in suggestion for suggestion in suggestions)

    def test_suggestions_for_unknown_validator(self):
        """Test suggestion generation for unknown validator types."""
        from jsonschema import ValidationError as JsonSchemaError
        
        schema = {}
        validator = SchemaValidator(schema)
        
        mock_error = JsonSchemaError("Some unknown validation error")
        mock_error.validator = 'unknown_validator'
        mock_error.schema = schema
        mock_error.absolute_path = []
        
        suggestions = validator.generate_suggestions(mock_error)
        assert any("Check the schema documentation for valid values" in suggestion for suggestion in suggestions)


class TestPathGeneration:
    """Test path generation in validation errors."""

    def test_path_generation_with_nested_objects(self):
        """Test path generation for nested object validation errors."""
        from jsonschema import ValidationError as JsonSchemaError
        
        schema = {"type": "object"}
        validator = SchemaValidator(schema)
        
        mock_error = JsonSchemaError("Validation error in nested field")
        mock_error.validator = 'type'
        mock_error.schema = schema
        mock_error.absolute_path = ['groups', 0, 'rules', 1, 'alert']
        
        converted_error = validator.convert_jsonschema_error(mock_error)
        assert "groups.[0].rules.[1].alert" in converted_error.path

    def test_path_generation_for_root_level_error(self):
        """Test path generation for root level validation errors."""
        from jsonschema import ValidationError as JsonSchemaError
        
        schema = {"type": "object"}
        validator = SchemaValidator(schema)
        
        mock_error = JsonSchemaError("Root level validation error")
        mock_error.validator = 'type'
        mock_error.schema = schema
        mock_error.absolute_path = []
        
        converted_error = validator.convert_jsonschema_error(mock_error)
        assert converted_error.path == "root"


class TestCrossReferenceValidatorMethods:
    """Test CrossReferenceValidator methods (even though validation is disabled)."""

    def test_cross_reference_validator_initialization(self):
        """Test CrossReferenceValidator can be initialized."""
        validator = CrossReferenceValidator()
        assert validator is not None

    def test_should_validate_wiki_consistency_both_sections_present(self):
        """Test should_validate_wiki_consistency when both sections present."""
        config = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "test_alert",
                            "expr": "metric > 1",
                            "annotations": {"summary": "Test"}
                        }
                    ]
                }
            ],
            "wiki": {
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "test_alert": {
                                "title": "Test Alert",
                                "content": "Documentation"
                            }
                        }
                    }
                }
            }
        }
        
        validator = CrossReferenceValidator()
        result = validator.should_validate_wiki_consistency(config)
        assert result is True

    def test_should_validate_wiki_consistency_missing_alerts(self):
        """Test should_validate_wiki_consistency when alerts missing."""
        config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "test_metric",
                            "expr": "metric_value"
                        }
                    ]
                }
            ],
            "wiki": {
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "test_alert": {
                                "title": "Test Alert",
                                "content": "Documentation"
                            }
                        }
                    }
                }
            }
        }
        
        validator = CrossReferenceValidator()
        result = validator.should_validate_wiki_consistency(config)
        assert result is False

    def test_should_validate_wiki_consistency_missing_wiki(self):
        """Test should_validate_wiki_consistency when wiki missing."""
        config = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "test_alert",
                            "expr": "metric > 1",
                            "annotations": {"summary": "Test"}
                        }
                    ]
                }
            ]
        }
        
        validator = CrossReferenceValidator()
        result = validator.should_validate_wiki_consistency(config)
        assert result is False

    def test_validate_alert_wiki_consistency_no_errors(self):
        """Test validate_alert_wiki_consistency returns empty list (validation disabled)."""
        config = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "undocumented_alert",
                            "expr": "metric > 1",
                            "annotations": {"summary": "Test"}
                        }
                    ]
                }
            ],
            "wiki": {
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "different_alert": {
                                "title": "Different Alert",
                                "content": "Documentation"
                            }
                        }
                    }
                }
            }
        }
        
        validator = CrossReferenceValidator()
        errors = validator.validate_alert_wiki_consistency(config)
        # Even with missing documentation, should return empty list since validation is disabled
        assert errors == []


class TestConfigAnalyzerMethods:
    """Test ConfigAnalyzer utility methods."""

    def test_extract_alert_names_multiple_alerts(self):
        """Test extracting alert names from multiple alerting rules."""
        groups = [
            {
                "name": "recording_rules",
                "rules": [
                    {
                        "record": "test_metric",
                        "expr": "metric_value"
                    }
                ]
            },
            {
                "name": "alerting_rules",
                "rules": [
                    {
                        "alert": "alert_one",
                        "expr": "metric > 1",
                        "annotations": {"summary": "Test 1"}
                    },
                    {
                        "alert": "alert_two",
                        "expr": "metric > 2",
                        "annotations": {"summary": "Test 2"}
                    }
                ]
            }
        ]
        
        alert_names = ConfigAnalyzer.extract_alert_names(groups)
        assert alert_names == {"alert_one", "alert_two"}

    def test_extract_alert_names_no_alerting_rules(self):
        """Test extracting alert names when no alerting rules exist."""
        groups = [
            {
                "name": "recording_rules",
                "rules": [
                    {
                        "record": "test_metric",
                        "expr": "metric_value"
                    }
                ]
            }
        ]
        
        alert_names = ConfigAnalyzer.extract_alert_names(groups)
        assert alert_names == set()

    def test_extract_alert_names_rules_missing_alert_field(self):
        """Test extracting alert names when some rules miss alert field."""
        groups = [
            {
                "name": "alerting_rules",
                "rules": [
                    {
                        "alert": "valid_alert",
                        "expr": "metric > 1",
                        "annotations": {"summary": "Test"}
                    },
                    {
                        "expr": "metric > 2",
                        "annotations": {"summary": "Test 2"}
                        # Missing alert field
                    }
                ]
            }
        ]
        
        alert_names = ConfigAnalyzer.extract_alert_names(groups)
        assert alert_names == {"valid_alert"}

    def test_extract_wiki_alert_names_multiple_alerts(self):
        """Test extracting alert names from wiki documentation."""
        wiki = {
            "knowledgebase": {
                "alerts": {
                    "alertings": {
                        "alert_one": {
                            "title": "Alert One",
                            "content": "Documentation for alert one"
                        },
                        "alert_two": {
                            "title": "Alert Two",
                            "content": "Documentation for alert two"
                        },
                        "alert_three": {
                            "title": "Alert Three",
                            "content": "Documentation for alert three"
                        }
                    }
                }
            }
        }
        
        wiki_alert_names = ConfigAnalyzer.extract_wiki_alert_names(wiki)
        assert wiki_alert_names == {"alert_one", "alert_two", "alert_three"}

    def test_extract_wiki_alert_names_empty_wiki(self):
        """Test extracting alert names from empty wiki."""
        wiki = {}
        
        wiki_alert_names = ConfigAnalyzer.extract_wiki_alert_names(wiki)
        assert wiki_alert_names == set()

    def test_extract_wiki_alert_names_missing_alertings(self):
        """Test extracting alert names when alertings section missing."""
        wiki = {
            "knowledgebase": {
                "alerts": {}
            }
        }
        
        wiki_alert_names = ConfigAnalyzer.extract_wiki_alert_names(wiki)
        assert wiki_alert_names == set()

    def test_has_wiki_knowledgebase_complete_structure(self):
        """Test has_wiki_knowledgebase with complete structure."""
        config = {
            "wiki": {
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "test_alert": {
                                "title": "Test Alert",
                                "content": "Documentation"
                            }
                        }
                    }
                }
            }
        }
        
        result = ConfigAnalyzer.has_wiki_knowledgebase(config)
        assert result is True

    def test_has_wiki_knowledgebase_empty_alertings(self):
        """Test has_wiki_knowledgebase with empty alertings."""
        config = {
            "wiki": {
                "knowledgebase": {
                    "alerts": {
                        "alertings": {}
                    }
                }
            }
        }
        
        result = ConfigAnalyzer.has_wiki_knowledgebase(config)
        assert result is False

    def test_has_wiki_knowledgebase_missing_wiki(self):
        """Test has_wiki_knowledgebase with missing wiki section."""
        config = {}
        
        result = ConfigAnalyzer.has_wiki_knowledgebase(config)
        assert result is False

    def test_has_alerting_rules_with_valid_alerts(self):
        """Test has_alerting_rules with valid alerting rules."""
        config = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "test_alert",
                            "expr": "metric > 1",
                            "annotations": {"summary": "Test"}
                        }
                    ]
                }
            ]
        }
        
        result = ConfigAnalyzer.has_alerting_rules(config)
        assert result is True

    def test_has_alerting_rules_no_alerting_group(self):
        """Test has_alerting_rules when no alerting_rules group exists."""
        config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "test_metric",
                            "expr": "metric_value"
                        }
                    ]
                }
            ]
        }
        
        result = ConfigAnalyzer.has_alerting_rules(config)
        assert result is False

    def test_has_alerting_rules_empty_rules(self):
        """Test has_alerting_rules with empty rules array."""
        config = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": []
                }
            ]
        }
        
        result = ConfigAnalyzer.has_alerting_rules(config)
        assert result is False

    def test_has_alerting_rules_rules_missing_alert_field(self):
        """Test has_alerting_rules when rules missing alert field."""
        config = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "expr": "metric > 1",
                            "annotations": {"summary": "Test"}
                            # Missing alert field
                        }
                    ]
                }
            ]
        }
        
        result = ConfigAnalyzer.has_alerting_rules(config)
        assert result is False


@pytest.fixture
def temp_directory():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)