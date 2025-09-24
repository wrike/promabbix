#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.promabbix import PromabbixApp, main
from promabbix.core.validation import ValidationError


class TestPromabbixAppCoverageImprovements:
    """Test additional scenarios for PromabbixApp to improve coverage."""

    def test_validate_configuration_method_success(self):
        """Test the validate_configuration method directly."""
        app = PromabbixApp()
        
        config_data = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "test_metric",
                            "expr": "sum(metric) by (label)"
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        
        result = app.validate_configuration(config_data)
        assert result is True

    def test_validate_configuration_method_failure(self):
        """Test the validate_configuration method with invalid config."""
        app = PromabbixApp()
        
        invalid_config = {
            "groups": [
                {
                    "name": "invalid_group_name",  # Invalid enum value
                    "rules": []
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        
        with pytest.raises(ValidationError):
            app.validate_configuration(invalid_config)

    def test_generate_template_method(self):
        """Test the generate_template method directly."""
        mock_renderer = MagicMock()
        mock_renderer.render_file.return_value = "Generated template content"
        
        with patch('promabbix.promabbix.Render', return_value=mock_renderer):
            app = PromabbixApp()
            
            config_data = {"test": "data"}
            template_path = "/path/to/templates"
            template_name = "test_template.j2"
            
            result = app.generate_template(config_data, template_path, template_name)
            
            assert result == "Generated template content"
            mock_renderer.render_file.assert_called_once_with(
                template_path=template_path,
                template_name=template_name,
                data=config_data
            )

    def test_main_console_script_entry_point(self):
        """Test the main() console script entry point."""
        mock_app = MagicMock()
        mock_app.main.return_value = 0
        
        with patch('promabbix.promabbix.PromabbixApp', return_value=mock_app):
            with patch('sys.exit') as mock_exit:
                main()
                
                mock_app.main.assert_called_once()
                mock_exit.assert_called_once_with(0)

    def test_main_console_script_with_error_exit_code(self):
        """Test the main() console script entry point with error exit code."""
        mock_app = MagicMock()
        mock_app.main.return_value = 1
        
        with patch('promabbix.promabbix.PromabbixApp', return_value=mock_app):
            with patch('sys.exit') as mock_exit:
                main()
                
                mock_app.main.assert_called_once()
                mock_exit.assert_called_once_with(1)

    def test_if_name_main_block(self):
        """Test the if __name__ == '__main__' block."""
        # This tests the coverage of the __main__ block
        with patch('promabbix.promabbix.main') as mock_main:
            # Simulate running the script directly
            import promabbix.promabbix
            
            # Mock __name__ to be '__main__'
            with patch.object(promabbix.promabbix, '__name__', '__main__'):
                # Execute the main block
                exec("""
if __name__ == '__main__':
    main()
""", promabbix.promabbix.__dict__)
                
                mock_main.assert_called_once()


class TestPromabbixAppEdgeCases:
    """Test edge cases and error conditions in PromabbixApp."""

    def test_main_with_file_not_found_exception(self):
        """Test main method handling FileNotFoundError."""
        mock_loader = MagicMock()
        mock_loader.load_from_file.side_effect = FileNotFoundError("File not found")
        
        app = PromabbixApp(loader=mock_loader)
        
        # Mock sys.argv to provide required arguments
        with patch('sys.argv', ['promabbix', 'non_existent_file.yaml']):
            exit_code = app.main()
            
            assert exit_code == 1

    def test_main_with_validation_error_in_normal_mode(self):
        """Test main method with validation error in normal mode."""
        mock_loader = MagicMock()
        mock_loader.load_from_file.return_value = {
            "groups": [
                {
                    "name": "invalid_group_name",  # This will cause validation error
                    "rules": []
                }
            ]
            # Missing required zabbix section
        }
        
        app = PromabbixApp(loader=mock_loader)
        
        # Mock sys.argv for normal mode (no --validate-only)
        with patch('sys.argv', ['promabbix', 'test_file.yaml', '-o', 'output.json']):
            exit_code = app.main()
            
            assert exit_code == 1

    def test_main_with_template_generation_error(self):
        """Test main method with template generation error."""
        mock_loader = MagicMock()
        mock_loader.load_from_file.return_value = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": []
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        
        mock_renderer = MagicMock()
        mock_renderer.render_file.side_effect = Exception("Template rendering failed")
        
        app = PromabbixApp(loader=mock_loader)
        
        with patch('promabbix.promabbix.Render', return_value=mock_renderer):
            with patch('sys.argv', ['promabbix', 'test_file.yaml', '-o', 'output.json']):
                exit_code = app.main()
                
                assert exit_code == 1

    def test_main_with_save_template_error(self):
        """Test main method with save template error."""
        mock_loader = MagicMock()
        mock_loader.load_from_file.return_value = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": []
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        
        mock_saver = MagicMock()
        mock_saver.save_to_file.side_effect = Exception("Save failed")
        
        mock_renderer = MagicMock()
        mock_renderer.render_file.return_value = "Template content"
        
        app = PromabbixApp(loader=mock_loader, saver=mock_saver)
        
        with patch('promabbix.promabbix.Render', return_value=mock_renderer):
            with patch('sys.argv', ['promabbix', 'test_file.yaml', '-o', 'output.json']):
                exit_code = app.main()
                
                assert exit_code == 1

    def test_load_configuration_with_stdin(self):
        """Test load_configuration method with STDIN input."""
        mock_loader = MagicMock()
        mock_loader.load_from_stdin.return_value = {"test": "data"}
        
        app = PromabbixApp(loader=mock_loader)
        
        result = app.load_configuration("-")
        
        assert result == {"test": "data"}
        mock_loader.load_from_stdin.assert_called_once()

    def test_load_configuration_with_file_path(self):
        """Test load_configuration method with file path."""
        mock_loader = MagicMock()
        mock_loader.load_from_file.return_value = {"test": "data"}
        
        app = PromabbixApp(loader=mock_loader)
        
        result = app.load_configuration("test_file.yaml")
        
        assert result == {"test": "data"}
        mock_loader.load_from_file.assert_called_once_with("test_file.yaml")

    def test_save_template_with_stdout(self):
        """Test save_template method with STDOUT output."""
        mock_saver = MagicMock()
        
        app = PromabbixApp(saver=mock_saver)
        
        app.save_template("Template content", "-")
        
        mock_saver.save_to_stdout.assert_called_once_with("Template content")

    def test_save_template_with_file_path(self):
        """Test save_template method with file path."""
        mock_saver = MagicMock()
        
        app = PromabbixApp(saver=mock_saver)
        
        app.save_template("Template content", "output.json")
        
        mock_saver.save_to_file.assert_called_once_with("Template content", "output.json")

    def test_print_validation_success(self):
        """Test print_validation_success method."""
        app = PromabbixApp()
        
        # Mock the console to capture output
        with patch.object(app.console, 'print') as mock_print:
            app.print_validation_success()
            
            mock_print.assert_called_once()
            call_args = mock_print.call_args[0][0]
            assert "Configuration validation passed" in call_args
            assert "[green]" in call_args

    def test_print_validation_error(self):
        """Test print_validation_error method."""
        app = PromabbixApp()
        
        error = ValidationError("Test validation error", path="test.field")
        
        # Mock the console to capture output
        with patch.object(app.console, 'print') as mock_print:
            app.print_validation_error(error)
            
            assert mock_print.call_count == 2  # Two print calls
            
            # Check the calls
            calls = mock_print.call_args_list
            
            # First call should be the failure message
            assert "Configuration validation failed" in calls[0][0][0]
            assert "[red]" in calls[0][0][0]
            
            # Second call should be the error details
            assert "Test validation error" in str(calls[1][0][0])
            assert "[red]" in calls[1][0][0]

    def test_handle_validation_only_mode_success(self):
        """Test handle_validation_only_mode with successful validation."""
        app = PromabbixApp()
        
        config_data = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": []
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        
        with patch.object(app, 'print_validation_success') as mock_print_success:
            exit_code = app.handle_validation_only_mode(config_data)
            
            assert exit_code == 0
            mock_print_success.assert_called_once()

    def test_handle_validation_only_mode_failure(self):
        """Test handle_validation_only_mode with validation failure."""
        app = PromabbixApp()
        
        invalid_config = {
            "groups": [
                {
                    "name": "invalid_group_name",  # Invalid enum value
                    "rules": []
                }
            ]
            # Missing required zabbix section
        }
        
        with patch.object(app, 'print_validation_error') as mock_print_error:
            exit_code = app.handle_validation_only_mode(invalid_config)
            
            assert exit_code == 1
            mock_print_error.assert_called_once()

    def test_handle_normal_mode_success(self):
        """Test handle_normal_mode with successful execution."""
        mock_saver = MagicMock()
        app = PromabbixApp(saver=mock_saver)
        
        config_data = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": []
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        
        pargs = {
            'templates': '/path/to/templates',
            'template_name': 'test_template.j2',
            'output': 'output.json'
        }
        
        with patch.object(app, 'generate_template', return_value="Generated content"):
            exit_code = app.handle_normal_mode(config_data, pargs)
            
            assert exit_code == 0
            mock_saver.save_to_file.assert_called_once_with("Generated content", "output.json")

    def test_handle_normal_mode_validation_failure(self):
        """Test handle_normal_mode with validation failure."""
        app = PromabbixApp()
        
        invalid_config = {
            "groups": [
                {
                    "name": "invalid_group_name",  # Invalid enum value
                    "rules": []
                }
            ]
            # Missing required zabbix section
        }
        
        pargs = {
            'templates': '/path/to/templates',
            'template_name': 'test_template.j2',
            'output': 'output.json'
        }
        
        with patch.object(app, 'print_validation_error') as mock_print_error:
            exit_code = app.handle_normal_mode(invalid_config, pargs)
            
            assert exit_code == 1
            mock_print_error.assert_called_once()