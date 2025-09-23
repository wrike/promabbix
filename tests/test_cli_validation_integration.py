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
from unittest.mock import patch, MagicMock
import argparse

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.promabbix import PromabbixApp


class TestCLIValidationIntegration:
    """Test CLI integration with validation features."""

    def test_validate_only_flag_added_to_parser(self):
        """Test that --validate-only flag is added to argument parser."""
        app = PromabbixApp()
        parser = app.app_args()
        
        # Parse test arguments to see if validate-only is supported
        args = parser.parse_args(['test.yaml', '--validate-only'])
        assert hasattr(args, 'validate_only')
        assert args.validate_only is True

    def test_schema_flag_not_available(self):
        """Test that --schema flag is NOT available (schema is built-in)."""
        app = PromabbixApp()
        parser = app.app_args()
        
        # Should NOT have schema flag since schema is built-in
        help_text = parser.format_help()
        assert '--schema' not in help_text

    def test_validate_only_mode_success(self, temp_directory):
        """Test --validate-only mode with valid configuration."""
        # Create a valid config file
        config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test_metric", "expr": "1"}]
                }
            ],
            "zabbix": {"template": "test_template"}
        }
        
        config_file = temp_directory / "valid_config.yaml"
        config_file.write_text(yaml.dump(config))
        
        app = PromabbixApp()
        
        # Mock sys.argv to simulate CLI call
        with patch('sys.argv', ['promabbix', str(config_file), '--validate-only']):
            result = app.main()
            assert result == 0  # Success

    def test_validate_only_mode_failure(self, temp_directory):
        """Test --validate-only mode with invalid configuration."""
        # Create an invalid config file
        invalid_config = {
            "groups": [
                {
                    "name": "invalid_group_name",  # Should be recording_rules or alerting_rules
                    "rules": [{"expr": "1"}]  # Missing record field
                }
            ]
            # Missing required zabbix section
        }
        
        config_file = temp_directory / "invalid_config.yaml"
        config_file.write_text(yaml.dump(invalid_config))
        
        app = PromabbixApp()
        
        with patch('sys.argv', ['promabbix', str(config_file), '--validate-only']):
            result = app.main()
            assert result == 1  # Failure

    def test_validate_only_mode_skips_template_generation(self, temp_directory):
        """Test that --validate-only mode doesn't generate templates."""
        config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test_metric", "expr": "1"}]
                }
            ],
            "zabbix": {"template": "test_template"}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        output_file = temp_directory / "output.json"
        
        app = PromabbixApp()
        
        with patch('sys.argv', ['promabbix', str(config_file), '--validate-only', '-o', str(output_file)]):
            app.main()
            
            # Output file should not be created in validation-only mode
            assert not output_file.exists()

    def test_built_in_schema_validation(self, temp_directory):
        """Test validation uses built-in schema (no custom schema option)."""
        # Create config that should be validated against built-in schema
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test"}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        app = PromabbixApp()
        
        with patch('sys.argv', ['promabbix', str(config_file), '--validate-only']):
            result = app.main()
            assert result == 0  # Should pass with built-in schema

    def test_validation_with_template_generation(self, temp_directory):
        """Test that validation runs before template generation in normal mode."""
        config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test_metric", "expr": "1"}]
                }
            ],
            "zabbix": {"template": "test_template"}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        output_file = temp_directory / "output.json"
        
        app = PromabbixApp()
        
        # Mock the template rendering to avoid needing actual template files
        with patch('promabbix.core.template.Render.render_file', return_value='{"mock": "template"}'):
            with patch('sys.argv', ['promabbix', str(config_file), '-o', str(output_file)]):
                result = app.main()
                # Should validate first, then generate template
                assert result == 0

    def test_validation_failure_prevents_template_generation(self, temp_directory):
        """Test that validation failure prevents template generation."""
        invalid_config = {
            "groups": [
                {
                    "name": "invalid_group",
                    "rules": [{"expr": "1"}]  # Missing record
                }
            ]
        }
        
        config_file = temp_directory / "invalid_config.yaml"
        config_file.write_text(yaml.dump(invalid_config))
        
        output_file = temp_directory / "output.json"
        
        app = PromabbixApp()
        
        with patch('sys.argv', ['promabbix', str(config_file), '-o', str(output_file)]):
            result = app.main()
            assert result == 1  # Should fail validation
            assert not output_file.exists()  # No template should be generated

    def test_help_includes_validation_options(self):
        """Test that help text includes validation-related options."""
        app = PromabbixApp()
        parser = app.app_args()
        
        help_text = parser.format_help()
        assert '--validate-only' in help_text
        # Schema flag should NOT be included since it's built-in
        assert '--schema' not in help_text

    def test_validation_error_output_formatting(self, temp_directory, capsys):
        """Test that validation errors are formatted nicely for CLI output."""
        invalid_config = {
            "groups": [
                {
                    "name": "invalid_name",
                    "rules": [{"expr": "test"}]
                }
            ]
        }
        
        config_file = temp_directory / "invalid.yaml"
        config_file.write_text(yaml.dump(invalid_config))
        
        app = PromabbixApp()
        
        with patch('sys.argv', ['promabbix', str(config_file), '--validate-only']):
            app.main()
            
            captured = capsys.readouterr()
            # Should have formatted error output
            error_output = captured.err or captured.out
            assert "❌" in error_output or "ERROR" in error_output or "validation" in error_output.lower()

    def test_validation_success_output_formatting(self, temp_directory, capsys):
        """Test that validation success is formatted nicely for CLI output."""
        valid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ],
            "zabbix": {"template": "test"}
        }
        
        config_file = temp_directory / "valid.yaml"
        config_file.write_text(yaml.dump(valid_config))
        
        app = PromabbixApp()
        
        with patch('sys.argv', ['promabbix', str(config_file), '--validate-only']):
            app.main()
            
            captured = capsys.readouterr()
            # Should have success message
            success_output = captured.out or captured.err
            assert "✓" in success_output or "Configuration validation passed" in success_output or "validation successful" in success_output.lower()

    def test_stdin_validation_mode(self, capsys):
        """Test validation mode with STDIN input."""
        valid_config = {
            "groups": [
                {
                    "name": "recording_rules", 
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ],
            "zabbix": {"template": "test"}
        }
        
        yaml_content = yaml.dump(valid_config)
        
        app = PromabbixApp()
        
        with patch('sys.stdin.read', return_value=yaml_content):
            with patch('sys.argv', ['promabbix', '-', '--validate-only']):
                result = app.main()
                assert result == 0

    def test_multiple_validation_errors_reported(self, temp_directory, capsys):
        """Test that multiple validation errors are reported in a single run."""
        config_with_multiple_errors = {
            "groups": [
                {
                    "name": "invalid_name",  # Error 1
                    "rules": [
                        {
                            "expr": "test"  # Error 2: missing record
                        },
                        {
                            "alert": "test_alert",
                            # Error 3: missing expr for alert rule
                            "annotations": {"summary": "test"}
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "test",
                "hosts": [
                    {
                        "host_name": "test",
                        "visible_name": "Test",
                        "host_groups": ["Test"],
                        "link_templates": ["test"],
                        "status": "invalid_status",  # Error 4
                        "state": "present"
                    }
                ]
            }
            # Error 5: Missing wiki section (if required by cross-validation)
        }
        
        config_file = temp_directory / "multi_error.yaml"
        config_file.write_text(yaml.dump(config_with_multiple_errors))
        
        app = PromabbixApp()
        
        with patch('sys.argv', ['promabbix', str(config_file), '--validate-only']):
            result = app.main()
            assert result == 1
            
            captured = capsys.readouterr()
            # Should report validation errors
            error_output = captured.err or captured.out
            assert "validation" in error_output.lower() or "error" in error_output.lower()

    def test_version_flag_compatibility(self):
        """Test that version flag works with validation features."""
        app = PromabbixApp()
        parser = app.app_args()
        
        # Check if version flag exists in help
        help_text = parser.format_help()
        # Version flag may or may not be implemented, just verify parser works
        assert 'promabbix' in help_text.lower() or 'usage' in help_text.lower()

    def test_config_file_not_found_error(self, capsys):
        """Test error handling when config file doesn't exist."""
        app = PromabbixApp()
        
        with patch('sys.argv', ['promabbix', '/nonexistent/config.yaml', '--validate-only']):
            result = app.main()
            assert result == 1
            
            captured = capsys.readouterr()
            error_output = captured.err or captured.out
            assert "not found" in error_output.lower() or "no such file" in error_output.lower() or "error" in error_output.lower()

    def test_built_in_schema_always_available(self, temp_directory):
        """Test that built-in schema is always available (no schema file needed)."""
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test"}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        app = PromabbixApp()
        
        with patch('sys.argv', ['promabbix', str(config_file), '--validate-only']):
            result = app.main()
            # Should always work since schema is built-in
            assert result == 0


class TestCLIBackwardsCompatibility:
    """Test that existing CLI functionality remains unchanged."""

    def test_existing_functionality_unchanged(self, temp_directory):
        """Test that existing CLI args and behavior are not broken."""
        # Create a simple config in the existing format expected by promabbix
        config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ]
        }
        
        config_file = temp_directory / "existing_format.yaml"
        config_file.write_text(yaml.dump(config))
        
        output_file = temp_directory / "output.json"
        
        # Test existing functionality still works
        app = PromabbixApp()
        parser = app.app_args()
        
        # These arguments should still work as before
        args = parser.parse_args([
            str(config_file),
            '-o', str(output_file),
            '-t', '/tmp/templates',
            '-tn', 'test_template.j2'
        ])
        
        assert args.alertrules == str(config_file)
        assert args.output == str(output_file)
        assert args.templates == '/tmp/templates'
        assert args.template_name == 'test_template.j2'

    def test_help_output_includes_new_and_old_options(self):
        """Test that help output includes both new validation and existing options."""
        app = PromabbixApp()
        parser = app.app_args()
        help_text = parser.format_help()
        
        # Existing options should still be present
        assert 'alertrules' in help_text
        assert '--output' in help_text or '-o' in help_text
        assert '--templates' in help_text or '-t' in help_text
        assert '--template-name' in help_text or '-tn' in help_text
        
        # New options should be added
        assert '--validate-only' in help_text
        # Schema flag should NOT be available since it's built-in
        assert '--schema' not in help_text