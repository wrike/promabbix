#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

"""
Unit tests for PromabbixApp class.
"""

import pytest
import argparse
import tempfile
import json
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import the real classes from their modules
from promabbix.core.fs_utils import DataLoader, DataSaver
from promabbix.core.template import Render


class TestPromabbixApp:
    """Test PromabbixApp class functionality."""
    
    def setup_method(self):
        """Setup method to import PromabbixApp with mocked dependencies."""
        # Patch the imports in the promabbix.py file to avoid import issues
        with patch.dict('sys.modules', {
            'core.fs_utils': sys.modules['promabbix.core.fs_utils'],
            'core.template': sys.modules['promabbix.core.template'],
            'rich_argparse': MagicMock()
        }):
            from promabbix.promabbix import PromabbixApp
            self.PromabbixApp = PromabbixApp
    
    def test_init_with_default_parameters(self):
        """Test PromabbixApp initialization with default parameters."""
        app = self.PromabbixApp()
        
        assert isinstance(app.loader, DataLoader)
        assert isinstance(app.saver, DataSaver)
        assert isinstance(app.parser, argparse.ArgumentParser)
        
    def test_init_with_custom_loader_and_saver(self):
        """Test PromabbixApp initialization with custom loader and saver."""
        mock_loader = MagicMock(spec=DataLoader)
        mock_saver = MagicMock(spec=DataSaver)
        
        app = self.PromabbixApp(loader=mock_loader, saver=mock_saver)
        
        assert app.loader is mock_loader
        assert app.saver is mock_saver
        assert isinstance(app.parser, argparse.ArgumentParser)
        
    def test_init_with_custom_parser(self):
        """Test PromabbixApp initialization with custom parser."""
        mock_parser = MagicMock(spec=argparse.ArgumentParser)
        
        app = self.PromabbixApp(parser=mock_parser)
        
        assert isinstance(app.loader, DataLoader)
        assert isinstance(app.saver, DataSaver)
        assert app.parser is mock_parser
        
    def test_app_args_creates_parser_with_correct_arguments(self):
        """Test app_args method creates parser with all required arguments."""
        app = self.PromabbixApp()
        parser = app.app_args()
        
        # Test parser is ArgumentParser instance
        assert isinstance(parser, argparse.ArgumentParser)
        
        # Test parser has correct description
        assert parser.description == 'Promabbix'
        
        # Test parser actions to verify arguments are configured
        actions = {action.dest: action for action in parser._actions}
        
        # Check required positional argument
        assert 'alertrules' in actions
        assert actions['alertrules'].type == str
        assert actions['alertrules'].help == 'Path to unified alert configuration file (use "-" to read from STDIN)'
        
        # Check optional arguments
        assert 'templates' in actions
        assert actions['templates'].type == str
        assert actions['templates'].help == 'Path to dir with jinja2 templates'
        
        assert 'output' in actions  
        assert actions['output'].type == str
        assert actions['output'].default == '/tmp/zbx_template.json'
        
        assert 'template_name' in actions
        assert actions['template_name'].type == str
        assert actions['template_name'].default == 'prometheus_alert_rules_to_zbx_template.j2'
        
    def test_app_args_default_templates_path(self):
        """Test app_args sets correct default templates path."""
        app = self.PromabbixApp()
        parser = app.app_args()
        
        actions = {action.dest: action for action in parser._actions}
        templates_default = actions['templates'].default
        
        # Should end with /templates/
        assert templates_default.endswith('/templates/')
        assert 'promabbix' in templates_default
        
    def test_main_successful_execution(self, temp_directory):
        """Test main method successful execution flow."""
        # Setup mocks
        mock_loader = MagicMock(spec=DataLoader)
        mock_saver = MagicMock(spec=DataSaver)
        
        # Setup test data - valid configuration with groups
        template_data = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test_metric", "expr": "1"}]
                }
            ],
            "zabbix": {"template": "test_template"}
        }
        rendered_output = '{"template": "rendered"}'
        
        mock_loader.load_from_file.return_value = template_data
        
        # Create test files
        alertrules_file = temp_directory / "alertrules.yaml"
        alertrules_file.write_text("rules:\n  - name: test_rule")
        
        output_file = temp_directory / "output.json"
        
        # Setup command line arguments
        test_args = [
            str(alertrules_file),
            '--output', str(output_file),
            '--templates', str(temp_directory),
            '--template-name', 'test.j2'
        ]
        
        with patch('sys.argv', ['promabbix'] + test_args):
            with patch.object(Render, '__init__', return_value=None):
                with patch.object(Render, 'render_file', return_value=rendered_output):
                    app = self.PromabbixApp(loader=mock_loader, saver=mock_saver)
                    app.main()
        
        # Verify interactions
        mock_loader.load_from_file.assert_called_once_with(str(alertrules_file))
        # Use call args to verify the call was made correctly (accounting for path resolution differences)
        mock_saver.save_to_file.assert_called_once()
        call_args = mock_saver.save_to_file.call_args
        assert call_args[0][0] == rendered_output  # First argument should be the rendered output
        assert Path(call_args[0][1]).resolve() == output_file.resolve()  # Paths should resolve to the same location
        
    def test_main_empty_template_output(self, temp_directory):
        """Test main method when template rendering returns empty string."""
        # Setup mocks
        mock_loader = MagicMock(spec=DataLoader)
        mock_saver = MagicMock(spec=DataSaver)
        
        # Setup test data
        template_data = {"rules": []}
        rendered_output = ''  # Empty output
        
        mock_loader.load_from_file.return_value = template_data
        
        # Create test files
        alertrules_file = temp_directory / "alertrules.yaml"
        alertrules_file.write_text("rules: []")
        
        output_file = temp_directory / "output.json"
        
        # Setup command line arguments
        test_args = [
            str(alertrules_file),
            '--output', str(output_file),
            '--templates', str(temp_directory),
            '--template-name', 'test.j2'
        ]
        
        with patch('sys.argv', ['promabbix'] + test_args):
            with patch.object(Render, '__init__', return_value=None):
                with patch.object(Render, 'render_file', return_value=rendered_output):
                    app = self.PromabbixApp(loader=mock_loader, saver=mock_saver)
                    app.main()
        
        # Verify loader was called
        mock_loader.load_from_file.assert_called_once_with(str(alertrules_file))
        
        # Verify saver was NOT called for empty output
        mock_saver.save_to_file.assert_not_called()
        
    def test_main_with_tilde_in_output_path(self, temp_directory):
        """Test main method with tilde in output path."""
        # Setup mocks
        mock_loader = MagicMock(spec=DataLoader)
        mock_saver = MagicMock(spec=DataSaver)
        
        # Setup test data - valid configuration with groups
        template_data = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test_metric", "expr": "1"}]
                }
            ],
            "zabbix": {"template": "test_template"}
        }
        rendered_output = '{"template": "rendered"}'
        
        mock_loader.load_from_file.return_value = template_data
        
        # Create test files
        alertrules_file = temp_directory / "alertrules.yaml"
        alertrules_file.write_text("rules:\n  - name: test_rule")
        
        # Use tilde path for output
        output_with_tilde = "~/test_output.json"
        expected_output_path = Path(output_with_tilde).expanduser().resolve()
        
        # Setup command line arguments
        test_args = [
            str(alertrules_file),
            '--output', output_with_tilde,
            '--templates', str(temp_directory),
            '--template-name', 'test.j2'
        ]
        
        with patch('sys.argv', ['promabbix'] + test_args):
            with patch.object(Render, '__init__', return_value=None):
                with patch.object(Render, 'render_file', return_value=rendered_output):
                    app = self.PromabbixApp(loader=mock_loader, saver=mock_saver)
                    app.main()
        
        # Verify saver was called with the original tilde path (expansion happens inside save_to_file)
        mock_saver.save_to_file.assert_called_once_with(rendered_output, output_with_tilde)
        
    def test_main_handles_loader_exception(self, temp_directory):
        """Test main method handles loader exceptions."""
        # Setup mocks
        mock_loader = MagicMock(spec=DataLoader)
        mock_saver = MagicMock(spec=DataSaver)
        
        # Setup loader to raise exception
        mock_loader.load_from_file.side_effect = FileNotFoundError("File not found")
        
        # Create test args
        alertrules_file = temp_directory / "nonexistent.yaml"
        output_file = temp_directory / "output.json"
        
        test_args = [
            str(alertrules_file),
            '--output', str(output_file)
        ]
        
        with patch('sys.argv', ['promabbix'] + test_args):
            app = self.PromabbixApp(loader=mock_loader, saver=mock_saver)
            
            # Should catch the exception and return error code
            result = app.main()
            assert result == 1
        
        # Verify loader was called
        mock_loader.load_from_file.assert_called_once_with(str(alertrules_file))
        # Verify saver was not called due to exception
        mock_saver.save_to_file.assert_not_called()
        
    def test_main_handles_render_exception(self, temp_directory):
        """Test main method handles render exceptions."""
        # Setup mocks
        mock_loader = MagicMock(spec=DataLoader)
        mock_saver = MagicMock(spec=DataSaver)
        
        # Setup test data and exception
        template_data = {"rules": []}
        mock_loader.load_from_file.return_value = template_data
        
        # Create test files
        alertrules_file = temp_directory / "alertrules.yaml"
        alertrules_file.write_text("rules: []")
        
        output_file = temp_directory / "output.json"
        
        test_args = [
            str(alertrules_file),
            '--output', str(output_file),
            '--template-name', 'bad_template.j2'
        ]
        
        with patch('sys.argv', ['promabbix'] + test_args):
            with patch.object(Render, '__init__', return_value=None):
                with patch.object(Render, 'render_file', side_effect=Exception("Template error")):
                    app = self.PromabbixApp(loader=mock_loader, saver=mock_saver)
                    
                    # Should catch the exception and return error code
                    result = app.main()
                    assert result == 1
        
        # Verify interactions up to the failure point
        mock_loader.load_from_file.assert_called_once_with(str(alertrules_file))
        mock_saver.save_to_file.assert_not_called()


class TestPromabbixAppArgumentParsing:
    """Test argument parsing functionality separately."""
    
    def setup_method(self):
        """Setup method to import PromabbixApp with mocked dependencies."""
        with patch.dict('sys.modules', {
            'core.fs_utils': sys.modules['promabbix.core.fs_utils'],
            'core.template': sys.modules['promabbix.core.template'],
            'rich_argparse': MagicMock()
        }):
            from promabbix.promabbix import PromabbixApp
            self.PromabbixApp = PromabbixApp
    
    def test_parse_minimal_arguments(self, temp_directory):
        """Test parsing with minimal required arguments."""
        alertrules_file = temp_directory / "rules.yaml"
        alertrules_file.touch()
        
        app = self.PromabbixApp()
        parser = app.app_args()
        
        args = parser.parse_args([str(alertrules_file)])
        
        assert args.alertrules == str(alertrules_file)
        assert args.output == '/tmp/zbx_template.json'
        assert args.template_name == 'prometheus_alert_rules_to_zbx_template.j2'
        assert args.templates.endswith('/templates/')
        
    def test_parse_all_arguments(self, temp_directory):
        """Test parsing with all arguments specified."""
        alertrules_file = temp_directory / "rules.yaml"
        alertrules_file.touch()
        
        templates_dir = temp_directory / "templates"
        templates_dir.mkdir()
        
        output_file = temp_directory / "output.json"
        
        app = self.PromabbixApp()
        parser = app.app_args()
        
        args = parser.parse_args([
            str(alertrules_file),
            '--templates', str(templates_dir),
            '--output', str(output_file),
            '--template-name', 'custom.j2'
        ])
        
        assert args.alertrules == str(alertrules_file)
        assert args.templates == str(templates_dir)
        assert args.output == str(output_file)
        assert args.template_name == 'custom.j2'
        
    def test_parse_short_form_arguments(self, temp_directory):
        """Test parsing with short form arguments."""
        alertrules_file = temp_directory / "rules.yaml"
        alertrules_file.touch()
        
        templates_dir = temp_directory / "templates"
        templates_dir.mkdir()
        
        output_file = temp_directory / "output.json"
        
        app = self.PromabbixApp()
        parser = app.app_args()
        
        args = parser.parse_args([
            str(alertrules_file),
            '-t', str(templates_dir),
            '-o', str(output_file),
            '-tn', 'short.j2'
        ])
        
        assert args.alertrules == str(alertrules_file)
        assert args.templates == str(templates_dir)
        assert args.output == str(output_file)
        assert args.template_name == 'short.j2'


class TestPromabbixAppIntegration:
    """Integration tests for PromabbixApp."""
    
    def setup_method(self):
        """Setup method to import PromabbixApp with mocked dependencies."""
        with patch.dict('sys.modules', {
            'core.fs_utils': sys.modules['promabbix.core.fs_utils'],
            'core.template': sys.modules['promabbix.core.template'],
            'rich_argparse': MagicMock()
        }):
            from promabbix.promabbix import PromabbixApp
            self.PromabbixApp = PromabbixApp
    
    def test_end_to_end_with_real_components(self, temp_directory):
        """Test end-to-end functionality with real components (except templates)."""
        # Create real test data
        alertrules_data = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "TestAlert",
                            "expr": "up == 0",
                            "for": "5m",
                            "labels": {"severity": "critical"},
                            "annotations": {
                                "summary": "Test alert summary",
                                "description": "Test alert"
                            }
                        }
                    ]
                }
            ],
            "zabbix": {"template": "test_template"}
        }
        
        # Create alertrules file
        alertrules_file = temp_directory / "alertrules.yaml"
        with open(alertrules_file, 'w') as f:
            json.dump(alertrules_data, f)
        
        # Create template file (simple mock template)
        templates_dir = temp_directory / "templates"
        templates_dir.mkdir()
        template_file = templates_dir / "test.j2"
        template_file.write_text('{"result": "processed {{ groups|length }} groups"}')
        
        output_file = temp_directory / "output.json"
        
        # Test arguments
        test_args = [
            str(alertrules_file),
            '--templates', str(templates_dir),
            '--output', str(output_file),
            '--template-name', 'test.j2'
        ]
        
        # Mock only the Render class to avoid template complexity
        with patch('sys.argv', ['promabbix'] + test_args):
            with patch.object(Render, '__init__', return_value=None):
                with patch.object(Render, 'render_file', return_value='{"result": "mocked template output"}') as mock_render_file:
                    app = self.PromabbixApp()
                    app.main()
                    
                    # Verify template was called
                    mock_render_file.assert_called_once()


class TestPromabbixAppStdinStdout:
    """Test STDIN/STDOUT functionality for PromabbixApp."""
    
    def setup_method(self):
        """Setup method to import PromabbixApp with mocked dependencies."""
        with patch.dict('sys.modules', {
            'core.fs_utils': sys.modules['promabbix.core.fs_utils'],
            'core.template': sys.modules['promabbix.core.template'],
            'rich_argparse': MagicMock()
        }):
            from promabbix.promabbix import PromabbixApp
            self.PromabbixApp = PromabbixApp
    
    def test_main_read_from_stdin(self, temp_directory):
        """Test main method reading alertrules from STDIN when alertrules is '-'."""
        # Setup mocks
        mock_loader = MagicMock(spec=DataLoader)
        mock_saver = MagicMock(spec=DataSaver)
        
        # Setup test data - valid configuration with groups
        stdin_data = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test_metric", "expr": "1"}]
                }
            ],
            "zabbix": {"template": "test_template"}
        }
        rendered_output = '{"template": "from_stdin"}'
        
        # Mock reading from STDIN
        mock_loader.load_from_stdin.return_value = stdin_data
        
        output_file = temp_directory / "output.json"
        
        # Setup command line arguments with "-" for alertrules
        test_args = [
            "-",  # Read from STDIN
            '--output', str(output_file),
            '--templates', str(temp_directory),
            '--template-name', 'test.j2'
        ]
        
        with patch('sys.argv', ['promabbix'] + test_args):
            with patch.object(Render, '__init__', return_value=None):
                with patch.object(Render, 'render_file', return_value=rendered_output):
                    app = self.PromabbixApp(loader=mock_loader, saver=mock_saver)
                    app.main()
        
        # Verify interactions
        mock_loader.load_from_stdin.assert_called_once()
        mock_loader.load_from_file.assert_not_called()  # Should not read from file
        # Use call args to verify the call was made correctly
        mock_saver.save_to_file.assert_called_once()
        call_args = mock_saver.save_to_file.call_args
        assert call_args[0][0] == rendered_output
        assert Path(call_args[0][1]).resolve() == output_file.resolve()
    
    def test_main_write_to_stdout(self, temp_directory):
        """Test main method writing output to STDOUT when --output is '-'."""
        # Setup mocks
        mock_loader = MagicMock(spec=DataLoader)
        mock_saver = MagicMock(spec=DataSaver)
        
        # Setup test data
        template_data = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test_metric", "expr": "1"}]
                }
            ],
            "zabbix": {"template": "test_template"}
        }
        rendered_output = '{"template": "to_stdout"}'
        
        mock_loader.load_from_file.return_value = template_data
        
        # Create test files
        alertrules_file = temp_directory / "alertrules.yaml"
        alertrules_file.write_text("rules:\n  - name: stdout_rule")
        
        # Setup command line arguments with "-" for output
        test_args = [
            str(alertrules_file),
            '--output', "-",  # Write to STDOUT
            '--templates', str(temp_directory),
            '--template-name', 'test.j2'
        ]
        
        with patch('sys.argv', ['promabbix'] + test_args):
            with patch.object(Render, '__init__', return_value=None):
                with patch.object(Render, 'render_file', return_value=rendered_output):
                    app = self.PromabbixApp(loader=mock_loader, saver=mock_saver)
                    app.main()
        
        # Verify interactions
        mock_loader.load_from_file.assert_called_once_with(str(alertrules_file))
        mock_saver.save_to_stdout.assert_called_once_with(rendered_output)
        mock_saver.save_to_file.assert_not_called()  # Should not save to file
    
    def test_main_stdin_to_stdout(self, temp_directory):
        """Test main method reading from STDIN and writing to STDOUT."""
        # Setup mocks
        mock_loader = MagicMock(spec=DataLoader)
        mock_saver = MagicMock(spec=DataSaver)
        
        # Setup test data - valid configuration with groups
        stdin_data = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test_metric", "expr": "1"}]
                }
            ],
            "zabbix": {"template": "test_template"}
        }
        rendered_output = '{"template": "piped_output"}'
        
        mock_loader.load_from_stdin.return_value = stdin_data
        
        # Setup command line arguments with "-" for both input and output
        test_args = [
            "-",  # Read from STDIN
            '--output', "-",  # Write to STDOUT
            '--templates', str(temp_directory),
            '--template-name', 'test.j2'
        ]
        
        with patch('sys.argv', ['promabbix'] + test_args):
            with patch.object(Render, '__init__', return_value=None):
                with patch.object(Render, 'render_file', return_value=rendered_output):
                    app = self.PromabbixApp(loader=mock_loader, saver=mock_saver)
                    app.main()
        
        # Verify interactions
        mock_loader.load_from_stdin.assert_called_once()
        mock_loader.load_from_file.assert_not_called()
        mock_saver.save_to_stdout.assert_called_once_with(rendered_output)
        mock_saver.save_to_file.assert_not_called()
    
    def test_main_empty_stdin_input(self, temp_directory):
        """Test main method handles empty STDIN input."""
        # Setup mocks
        mock_loader = MagicMock(spec=DataLoader)
        mock_saver = MagicMock(spec=DataSaver)
        
        # Setup empty stdin data
        mock_loader.load_from_stdin.return_value = {}
        
        output_file = temp_directory / "output.json"
        
        # Setup command line arguments
        test_args = [
            "-",  # Read from STDIN
            '--output', str(output_file),
            '--template-name', 'test.j2'
        ]
        
        with patch('sys.argv', ['promabbix'] + test_args):
            with patch.object(Render, '__init__', return_value=None):
                with patch.object(Render, 'render_file', return_value=''):
                    app = self.PromabbixApp(loader=mock_loader, saver=mock_saver)
                    app.main()
        
        # Verify interactions
        mock_loader.load_from_stdin.assert_called_once()
        mock_saver.save_to_file.assert_not_called()  # Empty output should not be saved
    
    def test_main_stdin_loader_exception(self, temp_directory):
        """Test main method handles STDIN loader exceptions."""
        # Setup mocks
        mock_loader = MagicMock(spec=DataLoader)
        mock_saver = MagicMock(spec=DataSaver)
        
        # Setup loader to raise exception when reading from STDIN
        mock_loader.load_from_stdin.side_effect = ValueError("Invalid STDIN data")
        
        output_file = temp_directory / "output.json"
        
        test_args = [
            "-",  # Read from STDIN
            '--output', str(output_file)
        ]
        
        with patch('sys.argv', ['promabbix'] + test_args):
            app = self.PromabbixApp(loader=mock_loader, saver=mock_saver)
            
            # Should catch the exception and return error code
            result = app.main()
            assert result == 1
        
        # Verify loader was called
        mock_loader.load_from_stdin.assert_called_once()
        # Verify saver was not called due to exception
        mock_saver.save_to_file.assert_not_called()
        mock_saver.save_to_stdout.assert_not_called()
    
    def test_main_stdout_saver_exception(self, temp_directory):
        """Test main method handles STDOUT saver exceptions."""
        # Setup mocks
        mock_loader = MagicMock(spec=DataLoader)
        mock_saver = MagicMock(spec=DataSaver)
        
        # Setup test data and exception - valid configuration with groups
        template_data = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test_metric", "expr": "1"}]
                }
            ],
            "zabbix": {"template": "test_template"}
        }
        rendered_output = '{"test": "output"}'
        
        mock_loader.load_from_file.return_value = template_data
        mock_saver.save_to_stdout.side_effect = IOError("Broken pipe")
        
        # Create test files
        alertrules_file = temp_directory / "alertrules.yaml"
        alertrules_file.write_text("rules:\n  - name: test")
        
        test_args = [
            str(alertrules_file),
            '--output', "-",  # Write to STDOUT
            '--template-name', 'test.j2'
        ]
        
        with patch('sys.argv', ['promabbix'] + test_args):
            with patch.object(Render, '__init__', return_value=None):
                with patch.object(Render, 'render_file', return_value=rendered_output):
                    app = self.PromabbixApp(loader=mock_loader, saver=mock_saver)
                    
                    # Should catch the exception and return error code
                    result = app.main()
                    assert result == 1
        
        # Verify interactions up to the failure point
        mock_loader.load_from_file.assert_called_once_with(str(alertrules_file))
        mock_saver.save_to_stdout.assert_called_once_with(rendered_output)
        mock_saver.save_to_file.assert_not_called()
    
    def test_argument_parser_accepts_dash_for_alertrules(self):
        """Test that argument parser accepts '-' as valid alertrules value."""
        app = self.PromabbixApp()
        parser = app.app_args()
        
        # Should not raise an exception when parsing "-" as alertrules
        args = parser.parse_args(["-"])
        
        assert args.alertrules == "-"
        assert args.output == '/tmp/zbx_template.json'  # Default output
    
    def test_argument_parser_accepts_dash_for_output(self, temp_directory):
        """Test that argument parser accepts '-' as valid output value."""
        # Create a dummy alertrules file
        alertrules_file = temp_directory / "rules.yaml"
        alertrules_file.touch()
        
        app = self.PromabbixApp()
        parser = app.app_args()
        
        # Should not raise an exception when parsing "-" as output
        args = parser.parse_args([
            str(alertrules_file),
            '--output', '-'
        ])
        
        assert args.alertrules == str(alertrules_file)
        assert args.output == '-'