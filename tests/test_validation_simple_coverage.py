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
import tempfile

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.validation import (
    ConfigValidator, ValidationError, 
    CrossReferenceValidator, ConfigAnalyzer
)


class TestValidationErrorHandlingSimple:
    """Test simple error handling scenarios in validation."""

    def test_schema_file_not_found_error(self, temp_directory):
        """Test ValidationError raised when schema file doesn't exist."""
        non_existent_schema = str(temp_directory / "non_existent_schema.yaml")
        
        with pytest.raises(ValidationError) as excinfo:
            ConfigValidator(schema_path=non_existent_schema)
        
        assert "Schema file not found" in str(excinfo.value)

    def test_schema_file_invalid_yaml_error(self, temp_directory):
        """Test ValidationError raised when schema file has invalid YAML."""
        invalid_yaml_schema = temp_directory / "invalid_schema.yaml"
        invalid_yaml_schema.write_text("invalid: yaml: content: [missing closing bracket")
        
        with pytest.raises(ValidationError) as excinfo:
            ConfigValidator(schema_path=str(invalid_yaml_schema))
        
        assert "Invalid format in schema file" in str(excinfo.value)

    def test_multiple_validation_errors_simple(self):
        """Test that multiple validation errors are handled."""
        config_with_errors = {
            "groups": [
                {
                    "name": "invalid_group_name",  # Error 1: Invalid enum
                    "rules": []
                }
            ]
            # Missing required zabbix section - Error 2
        }
        
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(config_with_errors)


class TestConfigAnalyzerSimple:
    """Test ConfigAnalyzer utility methods."""

    def test_extract_alert_names_simple(self):
        """Test extracting alert names from alerting rules."""
        groups = [
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

    def test_extract_alert_names_no_alerts(self):
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

    def test_extract_wiki_alert_names_simple(self):
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
                        }
                    }
                }
            }
        }
        
        wiki_alert_names = ConfigAnalyzer.extract_wiki_alert_names(wiki)
        assert wiki_alert_names == {"alert_one", "alert_two"}

    def test_extract_wiki_alert_names_empty(self):
        """Test extracting alert names from empty wiki."""
        wiki = {}
        
        wiki_alert_names = ConfigAnalyzer.extract_wiki_alert_names(wiki)
        assert wiki_alert_names == set()

    def test_has_wiki_knowledgebase_true(self):
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

    def test_has_wiki_knowledgebase_false(self):
        """Test has_wiki_knowledgebase with missing wiki section."""
        config = {}
        
        result = ConfigAnalyzer.has_wiki_knowledgebase(config)
        assert result is False

    def test_has_alerting_rules_true(self):
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

    def test_has_alerting_rules_false(self):
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


class TestCrossReferenceValidatorSimple:
    """Test CrossReferenceValidator methods."""

    def test_cross_reference_validator_init(self):
        """Test CrossReferenceValidator can be initialized."""
        validator = CrossReferenceValidator()
        assert validator is not None

    def test_should_validate_wiki_consistency_true(self):
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

    def test_should_validate_wiki_consistency_false(self):
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


@pytest.fixture
def temp_directory():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)