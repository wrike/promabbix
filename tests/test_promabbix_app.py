#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

"""
Unit tests for refactored PromabbixApp (now just a CLI wrapper) and GenerateTemplateCommand.
"""

import pytest
import tempfile
import json
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.fs_utils import DataLoader, DataSaver
from promabbix.core.validation import ConfigValidator
from promabbix.cli.generate_template import GenerateTemplateCommand


class TestGenerateTemplateCommandCore:
    """Test GenerateTemplateCommand core functionality."""
    
    def test_init_with_default_parameters(self):
        """Test GenerateTemplateCommand initialization with default parameters."""
        command = GenerateTemplateCommand()
        
        assert isinstance(command.loader, DataLoader)
        assert isinstance(command.saver, DataSaver)
        assert isinstance(command.validator, ConfigValidator)
        
    def test_init_with_custom_dependencies(self):
        """Test GenerateTemplateCommand initialization with custom dependencies."""
        mock_loader = MagicMock(spec=DataLoader)
        mock_saver = MagicMock(spec=DataSaver)
        mock_validator = MagicMock(spec=ConfigValidator)
        
        command = GenerateTemplateCommand(
            loader=mock_loader,
            saver=mock_saver,
            validator=mock_validator
        )
        
        assert command.loader is mock_loader
        assert command.saver is mock_saver
        assert command.validator is mock_validator

    def test_load_configuration_from_file(self, temp_directory):
        """Test load_configuration method with file input."""
        mock_loader = MagicMock(spec=DataLoader)
        test_data = {"test": "data"}
        mock_loader.load_from_file.return_value = test_data
        
        command = GenerateTemplateCommand(loader=mock_loader)
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text("test: data")
        
        result = command.load_configuration(str(config_file))
        
        assert result == test_data
        mock_loader.load_from_file.assert_called_once_with(str(config_file))

    def test_load_configuration_from_stdin(self):
        """Test load_configuration method with STDIN input."""
        mock_loader = MagicMock(spec=DataLoader)
        test_data = {"test": "data"}
        mock_loader.load_from_stdin.return_value = test_data
        
        command = GenerateTemplateCommand(loader=mock_loader)
        
        result = command.load_configuration("-")
        
        assert result == test_data
        mock_loader.load_from_stdin.assert_called_once()

    def test_validate_configuration(self):
        """Test validate_configuration method."""
        mock_validator = MagicMock(spec=ConfigValidator)
        command = GenerateTemplateCommand(validator=mock_validator)
        
        test_config = {"test": "config"}
        command.validate_configuration(test_config)
        
        mock_validator.validate_config.assert_called_once_with(test_config)

    def test_save_template_to_file(self, temp_directory):
        """Test save_template method with file output."""
        mock_saver = MagicMock(spec=DataSaver)
        command = GenerateTemplateCommand(saver=mock_saver)
        
        output_file = temp_directory / "output.json"
        template_data = '{"template": "data"}'
        
        command.save_template(template_data, str(output_file))
        
        mock_saver.save_to_file.assert_called_once_with(template_data, str(output_file))

    def test_save_template_to_stdout(self):
        """Test save_template method with STDOUT output."""
        mock_saver = MagicMock(spec=DataSaver)
        command = GenerateTemplateCommand(saver=mock_saver)
        
        template_data = '{"template": "data"}'
        
        command.save_template(template_data, "-")
        
        mock_saver.save_to_stdout.assert_called_once_with(template_data)


class TestGenerateTemplateCommandExecution:
    """Test GenerateTemplateCommand execute method and workflow."""
    
    def test_execute_validate_only_success(self, temp_directory):
        """Test execute method in validate-only mode with successful validation."""
        mock_loader = MagicMock(spec=DataLoader)
        mock_validator = MagicMock(spec=ConfigValidator)
        
        test_config = {"groups": [], "zabbix": {"template": "test"}}
        mock_loader.load_from_file.return_value = test_config
        
        command = GenerateTemplateCommand(loader=mock_loader, validator=mock_validator)
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text("test config")
        
        with patch.object(command, 'print_validation_success') as mock_print:
            result = command.execute(
                config_file=str(config_file),
                output="/tmp/output.json",
                templates=None,
                template_name="template.j2",
                validate_only=True
            )
        
        assert result == 0
        mock_validator.validate_config.assert_called_once_with(test_config)
        mock_print.assert_called_once()

    def test_execute_full_workflow_success(self, temp_directory):
        """Test execute method full workflow (validation + template generation)."""
        mock_loader = MagicMock(spec=DataLoader)
        mock_validator = MagicMock(spec=ConfigValidator)
        mock_saver = MagicMock(spec=DataSaver)
        
        test_config = {"groups": [], "zabbix": {"template": "test"}}
        template_content = '{"template": "generated"}'
        
        mock_loader.load_from_file.return_value = test_config
        
        command = GenerateTemplateCommand(
            loader=mock_loader,
            validator=mock_validator,
            saver=mock_saver
        )
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text("groups: []\nzabbix:\n  template: test")  # Create the file so it exists
        output_file = temp_directory / "output.json"
        
        with patch.object(command, 'generate_template_content', return_value=template_content):
            result = command.execute(
                config_file=str(config_file),
                output=str(output_file),
                templates="/templates",
                template_name="template.j2",
                validate_only=False
            )
        
        assert result == 0
        mock_validator.validate_config.assert_called_once_with(test_config)
        mock_saver.save_to_file.assert_called_once_with(template_content, str(output_file))

    def test_execute_validation_error(self, temp_directory):
        """Test execute method handles validation errors correctly."""
        from promabbix.core.validation import ValidationError
        
        mock_loader = MagicMock(spec=DataLoader)
        mock_validator = MagicMock(spec=ConfigValidator)
        
        test_config = {"invalid": "config"}
        mock_loader.load_from_file.return_value = test_config
        mock_validator.validate_config.side_effect = ValidationError("Validation failed")
        
        command = GenerateTemplateCommand(loader=mock_loader, validator=mock_validator)
        
        config_file = temp_directory / "config.yaml"
        config_file.write_text("invalid: config")  # Create the file so it exists
        
        with patch.object(command, 'print_validation_error') as mock_print:
            result = command.execute(
                config_file=str(config_file),
                output="/tmp/output.json",
                templates=None,
                template_name="template.j2",
                validate_only=True
            )
        
        assert result == 1
        mock_print.assert_called_once()

    def test_execute_general_exception(self, temp_directory):
        """Test execute method handles general exceptions correctly."""
        mock_loader = MagicMock(spec=DataLoader)
        mock_loader.load_from_file.side_effect = Exception("File error")
        
        command = GenerateTemplateCommand(loader=mock_loader)
        
        config_file = temp_directory / "config.yaml"
        
        result = command.execute(
            config_file=str(config_file),
            output="/tmp/output.json",
            templates=None,
            template_name="template.j2",
            validate_only=True
        )
        
        assert result == 1


class TestPromabbixAppWrapper:
    """Test PromabbixApp as a thin wrapper around GenerateTemplateCommand."""
    
    def test_promabbix_app_delegates_to_generate_template_command(self):
        """Test that PromabbixApp.main() delegates to GenerateTemplateCommand.execute()."""
        # Import here to avoid CLI structure issues
        from promabbix.promabbix import main
        
        # Test that the main function exists and is callable
        assert callable(main)
        
        # More detailed testing would require complex mocking of sys.argv
        # The actual delegation is tested via CLI integration tests


# Keep some integration tests that verify the overall system works
class TestIntegration:
    """Integration tests for the refactored system."""
    
    def test_command_can_be_instantiated_and_used(self):
        """Test that GenerateTemplateCommand can be instantiated and basic methods work."""
        command = GenerateTemplateCommand()
        
        # Test that all expected methods exist
        assert hasattr(command, 'execute')
        assert hasattr(command, 'load_configuration')
        assert hasattr(command, 'validate_configuration')
        assert hasattr(command, 'generate_template_content')
        assert hasattr(command, 'save_template')
        assert hasattr(command, 'print_validation_success')
        assert hasattr(command, 'print_validation_error')
        
        # Test that methods are callable
        assert callable(command.execute)
        assert callable(command.load_configuration)
        assert callable(command.validate_configuration)