#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2025 Wrike Inc.
#

import pytest
import yaml
import json
from pathlib import Path
import sys
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.promabbix import cli
from promabbix.cli.generate_template import GenerateTemplateCommand, generate_template


class TestGenerateTemplateCommand:
    """Test the generateTemplate CLI command."""
    
    def test_generate_template_command_exists(self):
        """Test that generateTemplate command is registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'generateTemplate' in result.output
    
    def test_generate_template_help(self):
        """Test generateTemplate command help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', '--help'])
        assert result.exit_code == 0
        assert 'Generate Zabbix template from alert configuration file' in result.output
    
    def test_generate_template_with_valid_config(self, temp_directory):
        """Test generateTemplate with valid configuration file."""
        # Create valid config file
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
        
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', str(config_file)])
        
        # Should succeed when implemented
        assert result.exit_code == 0
    
    def test_generate_template_with_output_file(self, temp_directory):
        """Test generateTemplate with custom output file."""
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test"}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        output_file = temp_directory / "output.json"
        
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', str(config_file), '-o', str(output_file)])
        
        assert result.exit_code == 0
        assert output_file.exists()
    
    def test_generate_template_with_stdout(self, temp_directory):
        """Test generateTemplate output to STDOUT."""
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test"}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', str(config_file), '-o', '-'])
        
        assert result.exit_code == 0
        # Should have JSON output to stdout
        assert result.output.strip()
    
    def test_generate_template_validate_only_success(self, temp_directory):
        """Test generateTemplate --validate-only with valid config."""
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test"}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', str(config_file), '--validate-only'])
        
        assert result.exit_code == 0
        assert '✓' in result.output or 'validation passed' in result.output.lower()
    
    def test_generate_template_validate_only_failure(self, temp_directory):
        """Test generateTemplate --validate-only with invalid config."""
        invalid_config = {
            "groups": [{"name": "invalid_group", "rules": [{"expr": "1"}]}]
            # Missing required zabbix section
        }
        
        config_file = temp_directory / "invalid.yaml"
        config_file.write_text(yaml.dump(invalid_config))
        
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', str(config_file), '--validate-only'])
        
        assert result.exit_code == 1
        assert '✗' in result.output or 'validation failed' in result.output.lower()
    
    def test_generate_template_custom_template_path(self, temp_directory):
        """Test generateTemplate with custom template directory."""
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test"}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        templates_dir = temp_directory / "templates"
        templates_dir.mkdir()
        
        runner = CliRunner()
        result = runner.invoke(cli, [
            'generateTemplate', str(config_file), 
            '-t', str(templates_dir)
        ])
        
        assert result.exit_code == 0
    
    def test_generate_template_custom_template_name(self, temp_directory):
        """Test generateTemplate with custom template name."""
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test"}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        runner = CliRunner()
        result = runner.invoke(cli, [
            'generateTemplate', str(config_file),
            '-tn', 'custom_template.j2'
        ])
        
        assert result.exit_code == 0
    
    def test_generate_template_missing_config_file(self):
        """Test generateTemplate with non-existent config file."""
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', '/nonexistent/config.yaml'])
        
        assert result.exit_code != 0
    
    def test_generate_template_invalid_yaml(self, temp_directory):
        """Test generateTemplate with malformed YAML."""
        config_file = temp_directory / "invalid.yaml"
        config_file.write_text("invalid: yaml: content: [")
        
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', str(config_file)])
        
        assert result.exit_code == 1


class TestGenerateTemplateCommandClass:
    """Test the GenerateTemplateCommand class directly."""
    
    def test_command_initialization(self):
        """Test command class can be initialized."""
        cmd = GenerateTemplateCommand()
        assert cmd.loader is not None
        assert cmd.saver is not None
        assert cmd.validator is not None
        assert cmd.console is not None
    
    def test_command_initialization_with_dependencies(self):
        """Test command class initialization with custom dependencies."""
        loader = MagicMock()
        saver = MagicMock()
        validator = MagicMock()
        
        cmd = GenerateTemplateCommand(loader=loader, saver=saver, validator=validator)
        assert cmd.loader is loader
        assert cmd.saver is saver
        assert cmd.validator is validator
    
    def test_execute_method_exists(self):
        """Test that execute method exists and handles missing file correctly."""
        cmd = GenerateTemplateCommand()
        
        # Should handle missing config file gracefully
        exit_code = cmd.execute("nonexistent.yaml", "output.json", None, "template.j2", False)
        assert exit_code == 1  # Should return error code for missing file
    
    def test_load_configuration_method_exists(self):
        """Test that load_configuration method exists and handles missing file."""
        cmd = GenerateTemplateCommand()
        
        with pytest.raises(FileNotFoundError):
            cmd.load_configuration("nonexistent.yaml")
    
    def test_validate_configuration_method_exists(self):
        """Test that validate_configuration method exists and works."""
        cmd = GenerateTemplateCommand()
        
        # Should work with minimal valid config
        config = {"groups": [{"name": "recording_rules", "rules": []}], "zabbix": {}}
        cmd.validate_configuration(config)  # Should not raise
    
    def test_generate_template_content_method_exists(self):
        """Test that generate_template_content method exists and works."""
        cmd = GenerateTemplateCommand()
        
        # Should work with minimal valid config
        config = {"groups": [{"name": "recording_rules", "rules": []}], "zabbix": {"template": "test"}}
        content = cmd.generate_template_content(config, None, "prometheus_alert_rules_to_zbx_template.j2")
        assert isinstance(content, str)
        assert len(content) > 0
    
    def test_save_template_method_exists(self):
        """Test that save_template method exists and works."""
        cmd = GenerateTemplateCommand()
        
        # Should work with any content
        cmd.save_template('{"test": "content"}', "-")  # STDOUT
    
    def test_print_validation_success_method_exists(self):
        """Test that print_validation_success method exists and works."""
        cmd = GenerateTemplateCommand()
        
        # Should work without raising
        cmd.print_validation_success()
    
    def test_print_validation_error_method_exists(self):
        """Test that print_validation_error method exists and works."""
        cmd = GenerateTemplateCommand()
        
        # Should work without raising
        cmd.print_validation_error("test error")


class TestGenerateTemplateBackwardCompatibility:
    """Test backward compatibility with existing functionality."""
    
    def test_generate_template_maintains_existing_behavior(self, temp_directory):
        """Test that generateTemplate maintains the same behavior as old promabbix command."""
        config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test_metric", "expr": "up"}]
                }
            ],
            "zabbix": {"template": "test_template"}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        output_file = temp_directory / "output.json"
        
        runner = CliRunner()
        result = runner.invoke(cli, [
            'generateTemplate', str(config_file),
            '-o', str(output_file)
        ])
        
        assert result.exit_code == 0
        # Should generate a valid JSON template file
        assert output_file.exists()
        
        with open(output_file) as f:
            template_data = json.load(f)
            # Should be valid Zabbix template structure
            assert 'zabbix_export' in template_data
    
    def test_generate_template_handles_stdin_input(self):
        """Test generateTemplate can handle STDIN input."""
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test"}
        }
        
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', '-'], input=yaml.dump(config))
        
        assert result.exit_code == 0
    
    def test_generate_template_error_handling(self, temp_directory):
        """Test generateTemplate error handling and reporting."""
        # Test with completely invalid configuration
        config_file = temp_directory / "config.yaml"
        config_file.write_text("not_yaml_at_all")
        
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', str(config_file)])
        
        assert result.exit_code == 1
        # Should show meaningful error message
        assert len(result.output) > 0


class TestGenerateTemplateIntegration:
    """Test generateTemplate integration with core modules."""
    
    def test_generate_template_uses_validation_module(self, temp_directory):
        """Test that generateTemplate integrates with validation module."""
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test"}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', str(config_file), '--validate-only'])
        
        # Should use the validation module
        assert result.exit_code == 0
    
    def test_generate_template_uses_template_rendering(self, temp_directory):
        """Test that generateTemplate integrates with template rendering."""
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test"}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', str(config_file)])
        
        # Should use template rendering module
        assert result.exit_code == 0
    
    def test_generate_template_uses_fs_utils(self, temp_directory):
        """Test that generateTemplate integrates with fs_utils module."""
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test"}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', str(config_file)])
        
        # Should use fs_utils for loading and saving
        assert result.exit_code == 0


class TestGenerateTemplateValidationIntegration:
    """Test validation integration features for generateTemplate command."""
    
    def test_validate_only_mode_skips_template_generation(self, temp_directory):
        """Test that --validate-only mode doesn't generate templates."""
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test", "hosts": [{"host_name": "test", "visible_name": "Test Host", "host_groups": ["Test"], "link_templates": ["test"]}]}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        output_file = temp_directory / "output.json"
        
        runner = CliRunner()
        result = runner.invoke(cli, [
            'generateTemplate', str(config_file), 
            '-o', str(output_file), '--validate-only'
        ])
        
        assert result.exit_code == 0
        # Output file should not be created in validate-only mode
        assert not output_file.exists()
        assert '✓' in result.output or 'validation passed' in result.output.lower()
    
    def test_validation_failure_prevents_template_generation(self, temp_directory):
        """Test that validation failure prevents template generation."""
        invalid_config = {
            "groups": [{"name": "invalid", "rules": [{"expr": "1"}]}]
            # Missing required zabbix section
        }
        
        config_file = temp_directory / "invalid.yaml"
        config_file.write_text(yaml.dump(invalid_config))
        
        output_file = temp_directory / "output.json"
        
        runner = CliRunner()
        result = runner.invoke(cli, [
            'generateTemplate', str(config_file), '-o', str(output_file)
        ])
        
        assert result.exit_code == 1
        # Output file should not be created when validation fails
        assert not output_file.exists()
        assert '✗' in result.output or 'validation failed' in result.output.lower()
    
    def test_built_in_schema_validation(self, temp_directory):
        """Test validation uses built-in schema (no custom schema option)."""
        # Test that schema validation works without needing external schema files
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test", "hosts": [{"host_name": "test", "visible_name": "Test Host", "host_groups": ["Test"], "link_templates": ["test"]}]}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', str(config_file), '--validate-only'])
        
        assert result.exit_code == 0
        # Should validate successfully with built-in schema
        assert '✓' in result.output or 'validation passed' in result.output.lower()
    
    def test_validation_with_template_generation(self, temp_directory):
        """Test that validation runs before template generation in normal mode."""
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test", "hosts": [{"host_name": "test", "visible_name": "Test Host", "host_groups": ["Test"], "link_templates": ["test"]}]}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        output_file = temp_directory / "output.json"
        
        runner = CliRunner()
        result = runner.invoke(cli, [
            'generateTemplate', str(config_file), '-o', str(output_file)
        ])
        
        assert result.exit_code == 0
        # Should generate output file after successful validation
        assert output_file.exists()
    
    def test_multiple_validation_errors_reported(self, temp_directory):
        """Test that multiple validation errors are reported in a single run."""
        config_with_multiple_errors = {
            "groups": [
                {
                    "name": "invalid_group_name",  # Error 1: Invalid enum value
                    "rules": []
                }
            ]
            # Error 2: Missing required zabbix section
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config_with_multiple_errors))
        
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', str(config_file), '--validate-only'])
        
        assert result.exit_code == 1
        assert '✗' in result.output or 'validation failed' in result.output.lower()
        # Should show detailed validation error information
        assert len(result.output) > 50  # Should have detailed error message
    
    def test_stdin_validation_mode(self):
        """Test validation mode with STDIN input."""
        valid_config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test", "hosts": [{"host_name": "test", "visible_name": "Test Host", "host_groups": ["Test"], "link_templates": ["test"]}]}
        }
        
        runner = CliRunner()
        result = runner.invoke(cli, [
            'generateTemplate', '-', '--validate-only'
        ], input=yaml.dump(valid_config))
        
        assert result.exit_code == 0
        assert '✓' in result.output or 'validation passed' in result.output.lower()
    
    def test_help_includes_validation_options(self):
        """Test that help text includes validation-related options."""
        runner = CliRunner()
        
        result = runner.invoke(cli, ['generateTemplate', '--help'])
        assert result.exit_code == 0
        assert '--validate-only' in result.output
        assert 'validate the configuration without generating' in result.output
    
    def test_config_file_not_found_error(self):
        """Test error handling when config file doesn't exist."""
        runner = CliRunner()
        result = runner.invoke(cli, ['generateTemplate', '/nonexistent/config.yaml'])
        
        assert result.exit_code != 0
        # Should show meaningful error for missing file
    
    def test_existing_functionality_unchanged(self, temp_directory):
        """Test that existing CLI args and behavior are not broken."""
        config = {
            "groups": [{"name": "recording_rules", "rules": [{"record": "test", "expr": "1"}]}],
            "zabbix": {"template": "test", "hosts": [{"host_name": "test", "visible_name": "Test Host", "host_groups": ["Test"], "link_templates": ["test"]}]}
        }
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text(yaml.dump(config))
        
        output_file = temp_directory / "output.json"
        
        runner = CliRunner()
        result = runner.invoke(cli, [
            'generateTemplate', str(config_file), 
            '-o', str(output_file),
            '-t', '/custom/templates',
            '-tn', 'custom.j2'
        ])
        
        assert result.exit_code == 0
        # All existing CLI options should still work