#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import pytest
import yaml
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch, mock_open

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.migration import (
    detect_config_format, migrate_legacy_service
)


class TestDetectConfigFormat:
    """Test format detection functionality."""

    def test_detect_config_format_unified_file_yaml(self, temp_directory):
        """Test detecting unified format from YAML file."""
        unified_file = temp_directory / "unified.yaml"
        unified_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        unified_file.write_text(yaml.dump(unified_config))
        
        result = detect_config_format(str(unified_file))
        assert result == "unified"

    def test_detect_config_format_unified_file_json(self, temp_directory):
        """Test detecting unified format from JSON file."""
        unified_file = temp_directory / "unified.json"
        unified_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        unified_file.write_text(json.dumps(unified_config))
        
        result = detect_config_format(str(unified_file))
        assert result == "unified"

    def test_detect_config_format_invalid_unified_file_missing_groups(self, temp_directory):
        """Test detecting invalid unified file missing groups."""
        invalid_file = temp_directory / "invalid.yaml"
        invalid_config = {
            "zabbix": {
                "template": "test_template"
            }
            # Missing groups section
        }
        invalid_file.write_text(yaml.dump(invalid_config))
        
        with pytest.raises(ValueError) as excinfo:
            detect_config_format(str(invalid_file))
        assert "doesn't match unified format" in str(excinfo.value)

    def test_detect_config_format_invalid_unified_file_missing_zabbix(self, temp_directory):
        """Test detecting invalid unified file missing zabbix."""
        invalid_file = temp_directory / "invalid.yaml"
        invalid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ]
            # Missing zabbix section
        }
        invalid_file.write_text(yaml.dump(invalid_config))
        
        with pytest.raises(ValueError) as excinfo:
            detect_config_format(str(invalid_file))
        assert "doesn't match unified format" in str(excinfo.value)

    def test_detect_config_format_invalid_yaml_file(self, temp_directory):
        """Test detecting format with invalid YAML content."""
        invalid_file = temp_directory / "invalid.yaml"
        invalid_file.write_text("invalid: yaml: content: [missing closing bracket")
        
        with pytest.raises(ValueError) as excinfo:
            detect_config_format(str(invalid_file))
        assert "Could not parse" in str(excinfo.value)

    def test_detect_config_format_legacy_directory_valid(self, temp_directory):
        """Test detecting legacy three-file format in directory."""
        # Create legacy structure
        (temp_directory / "service_alerts.yaml").write_text("groups: []")
        (temp_directory / "zabbix_vars.yaml").write_text("zabbix:\n  template: test")
        
        result = detect_config_format(str(temp_directory))
        assert result == "legacy_three_file"

    def test_detect_config_format_legacy_directory_missing_zabbix_vars(self, temp_directory):
        """Test detecting legacy directory missing zabbix_vars.yaml."""
        # Create only alerts file
        (temp_directory / "service_alerts.yaml").write_text("groups: []")
        
        with pytest.raises(ValueError) as excinfo:
            detect_config_format(str(temp_directory))
        assert "doesn't match legacy three-file format" in str(excinfo.value)

    def test_detect_config_format_legacy_directory_missing_alerts(self, temp_directory):
        """Test detecting legacy directory missing alert files."""
        # Create only zabbix_vars file
        (temp_directory / "zabbix_vars.yaml").write_text("zabbix:\n  template: test")
        
        with pytest.raises(ValueError) as excinfo:
            detect_config_format(str(temp_directory))
        assert "doesn't match legacy three-file format" in str(excinfo.value)

    def test_detect_config_format_non_existent_path(self):
        """Test detecting format with non-existent path."""
        with pytest.raises(ValueError) as excinfo:
            detect_config_format("/non/existent/path")
        assert "is neither a file nor a directory" in str(excinfo.value)




class TestMigrateLegacyService:
    """Test complete legacy service migration."""

    def test_migrate_legacy_service_basic_structure(self, temp_directory):
        """Test migrating basic legacy service structure."""
        # Create legacy files
        alerts_file = temp_directory / "service_alerts.yaml"
        alerts_data = {
            "groups": [
                {
                    "name": "service_alerts",
                    "rules": [
                        {
                            "alert": "test_alert",
                            "expr": "metric > 1",
                            "annotations": {
                                "summary": "Test alert"
                            }
                        }
                    ]
                }
            ]
        }
        alerts_file.write_text(yaml.dump(alerts_data))
        
        zabbix_vars_file = temp_directory / "zabbix_vars.yaml"
        zabbix_vars_wrapper = {
            "zabbix": {
                "template": "test_template",
                "name": "Test Template Name"
            }
        }
        zabbix_vars_file.write_text(yaml.dump(zabbix_vars_wrapper))
        
        result = migrate_legacy_service(str(temp_directory))
        
        assert "groups" in result
        assert "zabbix" in result
        assert result["zabbix"]["template"] == "test_template"

    def test_migrate_legacy_service_with_error_conditions(self, temp_directory):
        """Test migrating with various error conditions."""
        # Test with non-existent directory
        with pytest.raises(ValueError):
            migrate_legacy_service("/non/existent/path")


@pytest.fixture
def temp_directory():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)