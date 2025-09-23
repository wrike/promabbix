#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import pytest
import tempfile
import json
import os
import uuid
import hashlib
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.template import (
    date_time, to_uuid4, get_jinja2_globals, Render
)


class TestUtilityFunctions:
    """Test utility functions in template module."""
    
    def test_date_time_valid_format(self):
        """Test date_time function with valid format."""
        result = date_time("%Y-%m-%d")
        # Should return current date in YYYY-MM-DD format
        assert len(result) == 10
        assert result.count('-') == 2
        
    def test_date_time_empty_format(self):
        """Test date_time function with empty format."""
        result = date_time("")
        assert result == ""
        
    @patch('time.time')
    def test_date_time_specific_timestamp(self, mock_time):
        """Test date_time function with specific timestamp."""
        # Mock timestamp for January 1, 2023, 12:00:00 UTC
        mock_time.return_value = 1672574400.0
        result = date_time("%Y-%m-%d %H:%M:%S")
        # The exact result depends on timezone, but should be formatted correctly
        assert len(result) == 19  # YYYY-MM-DD HH:MM:SS format
        
    def test_to_uuid4_consistent_output(self):
        """Test to_uuid4 function produces consistent output for same input."""
        test_string = "test_string"
        result1 = to_uuid4(test_string)
        result2 = to_uuid4(test_string)
        assert result1 == result2
        
    def test_to_uuid4_different_inputs(self):
        """Test to_uuid4 function produces different outputs for different inputs."""
        result1 = to_uuid4("string1")
        result2 = to_uuid4("string2")
        assert result1 != result2
        
    def test_to_uuid4_format(self):
        """Test to_uuid4 function produces valid UUID format."""
        result = to_uuid4("test")
        # UUID format: 8-4-4-4-12 characters
        assert len(result) == 36
        assert result.count('-') == 4
        # Validate it's a valid UUID
        uuid.UUID(result)
        
    def test_to_uuid4_empty_string(self):
        """Test to_uuid4 function with empty string."""
        result = to_uuid4("")
        assert len(result) == 36
        assert result.count('-') == 4
        
    def test_to_uuid4_unicode_string(self):
        """Test to_uuid4 function with unicode string."""
        result = to_uuid4("тест")
        assert len(result) == 36
        assert result.count('-') == 4


class TestJinja2Configuration:
    """Test Jinja2 configuration functions."""
    
    def test_get_jinja2_globals(self):
        """Test get_jinja2_globals returns expected globals."""
        globals_dict = get_jinja2_globals()
        assert 'date_time' in globals_dict
        assert callable(globals_dict['date_time'])


class TestRenderClass:
    """Test Render class functionality."""
    
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_render_init_no_searchpath(self, mock_tests, mock_filters):
        """Test Render initialization without searchpath."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        render = Render()
        assert render.searchpath is None
        assert render.jinja_env is not None
        assert render.console is not None
        
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_render_init_with_searchpath(self, mock_tests, mock_filters):
        """Test Render initialization with searchpath."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            render = Render(temp_dir)
            assert render.searchpath == Path(temp_dir).resolve()
            
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_render_init_with_tilde_path(self, mock_tests, mock_filters):
        """Test Render initialization with tilde in path."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        render = Render("~/test")
        expected_path = Path("~/test").expanduser().resolve()
        assert render.searchpath == expected_path
        
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_jinja_env_configuration(self, mock_tests, mock_filters):
        """Test that Jinja2 environment is configured correctly."""
        mock_filters.return_value = {'to_uuid4': to_uuid4}
        mock_tests.return_value = {}
        
        render = Render()
        
        # Test custom comment delimiters
        assert render.jinja_env.comment_start_string == "{##"
        assert render.jinja_env.comment_end_string == "##}"
        
        # Test trim and lstrip blocks
        assert render.jinja_env.trim_blocks is True
        assert render.jinja_env.lstrip_blocks is True
        
        # Test that custom filters are loaded
        assert 'to_uuid4' in render.jinja_env.filters
        
        # Test that custom globals are loaded
        assert 'date_time' in render.jinja_env.globals
        assert 'lookup_template' in render.jinja_env.globals
        
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_is_template_valid_template(self, mock_tests, mock_filters):
        """Test is_template with valid template syntax."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        render = Render()
        
        valid_templates = [
            "Hello {{ name }}",
            "{% for item in items %}{{ item }}{% endfor %}",
            "{{ value | upper }}",
            "Plain text without variables"
        ]
        
        for template in valid_templates:
            assert render.is_template(template) is True
            
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_is_template_invalid_template(self, mock_tests, mock_filters):
        """Test is_template with invalid template syntax."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        render = Render()
        
        invalid_templates = [
            "{{ unclosed",
            "{% invalid syntax",
            "{{ missing }",
            "{% for item in %}{{ item }}{% endfor %}"
        ]
        
        with patch.object(render.console, 'print') as mock_print:
            for template in invalid_templates:
                assert render.is_template(template) is False
                mock_print.assert_called()
                
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_render_string_template(self, mock_tests, mock_filters):
        """Test rendering from string template."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        render = Render()
        
        template = "Hello {{ name }}!"
        data = {"name": "World"}
        result = render.render(template, data)
        
        assert result == "Hello World!"
        
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_render_string_template_with_filters(self, mock_tests, mock_filters):
        """Test rendering string template with custom filters."""
        mock_filters.return_value = {'basename': os.path.basename}
        mock_tests.return_value = {}
        
        render = Render()
        
        template = "{{ path | basename }}"
        data = {"path": "/home/user/file.txt"}
        result = render.render(template, data)
        
        assert result == "file.txt"
        
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_render_string_template_with_globals(self, mock_tests, mock_filters):
        """Test rendering string template with custom globals."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        render = Render()
        
        template = "Current date: {{ date_time('%Y-%m-%d') }}"
        data = {}
        result = render.render(template, data)
        
        assert "Current date:" in result
        assert len(result.split(": ")[1]) == 10  # YYYY-MM-DD format
        
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_render_file_template(self, mock_tests, mock_filters):
        """Test rendering from file template."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a template file
            template_file = Path(temp_dir) / "test.j2"
            template_file.write_text("Hello {{ name }}!")
            
            render = Render(temp_dir)
            data = {"name": "World"}
            result = render.render("test.j2", data)
            
            assert result == "Hello World!"
            
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_render_file_not_found_fallback_to_string(self, mock_tests, mock_filters):
        """Test rendering falls back to string when file not found."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            render = Render(temp_dir)
            
            # Template that doesn't exist as file but is valid template string
            template = "Hello {{ name }}!"
            data = {"name": "World"}
            result = render.render(template, data)
            
            assert result == "Hello World!"
            
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_render_non_template_string(self, mock_tests, mock_filters):
        """Test rendering non-template string returns empty."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        render = Render()
        
        template = "Just plain text"
        data = {}
        result = render.render(template, data)
        
        assert result == "Just plain text"
        
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_render_template_syntax_error(self, mock_tests, mock_filters):
        """Test rendering with template syntax error."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        render = Render()
        
        template = "{{ unclosed"
        data = {}
        
        with patch.object(render.console, 'print') as mock_print:
            result = render.render(template, data)
            assert result == ""
            mock_print.assert_called()
            
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_do_template_method(self, mock_tests, mock_filters):
        """Test do_template public method."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        render = Render()
        
        template = "Hello {{ name }}!"
        data = {"name": "World"}
        result = render.do_template(data, template)
        
        assert result == "Hello World!"
        
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_lookup_template_global(self, mock_tests, mock_filters):
        """Test lookup_template global function in templates."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        render = Render()
        
        template = "{{ lookup_template({'name': 'World'}, 'Hello {{ name }}!') }}"
        data = {}
        result = render.render(template, data)
        
        assert result == "Hello World!"
        
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_render_with_complex_data(self, mock_tests, mock_filters):
        """Test rendering with complex nested data."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        render = Render()
        
        template = """
        {%- for user in users -%}
        Name: {{ user.name }}, Age: {{ user.age }}
        {%- endfor -%}
        """
        
        data = {
            "users": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25}
            ]
        }
        
        result = render.render(template, data)
        expected = "Name: Alice, Age: 30Name: Bob, Age: 25"
        assert result == expected
        
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_render_with_custom_comment_delimiters(self, mock_tests, mock_filters):
        """Test rendering with custom comment delimiters."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        render = Render()
        
        template = "{## This is a comment ##}Hello {{ name }}!"
        data = {"name": "World"}
        result = render.render(template, data)
        
        assert result == "Hello World!"
        assert "This is a comment" not in result
        
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_render_file_with_line_number_error(self, mock_tests, mock_filters):
        """Test rendering file template with line number in error."""
        mock_filters.return_value = {}
        mock_tests.return_value = {}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a template file with syntax error
            template_file = Path(temp_dir) / "error.j2"
            template_file.write_text("Line 1\n{{ unclosed\nLine 3")
            
            render = Render(temp_dir)
            data = {}
            
            with patch.object(render.console, 'print') as mock_print:
                result = render.render("error.j2", data)
                assert result == ""
                # Should print error with line number
                mock_print.assert_called()
                call_args = str(mock_print.call_args)
                assert "line" in call_args.lower()


class TestIntegration:
    """Integration tests for the template module."""
    
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_full_template_workflow(self, mock_tests, mock_filters):
        """Test complete template workflow with file and string templates."""
        mock_filters.return_value = {'basename': os.path.basename}
        mock_tests.return_value = {}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create template files
            main_template = Path(temp_dir) / "main.j2"
            main_template.write_text("""
            {## Main template ##}
            Project: {{ project_name }}
            Generated: {{ date_time('%Y-%m-%d %H:%M:%S') }}
            
            Files:
            {%- for file in files %}
            - {{ file.name | basename }} ({{ file.size }} bytes)
            {%- endfor %}
            
            Config: {{ lookup_template(config, 'Key: {{ key }}, Value: {{ value }}') }}
            """)
            
            render = Render(temp_dir)
            data = {
                "project_name": "Test Project",
                "files": [
                    {"name": "/path/to/file1.txt", "size": 1024},
                    {"name": "/path/to/file2.txt", "size": 2048}
                ],
                "config": {"key": "debug", "value": "true"}
            }
            
            result = render.render("main.j2", data)
            
            # Verify the result contains expected content
            assert "Project: Test Project" in result
            assert "Generated:" in result
            assert "- file1.txt (1024 bytes)" in result
            assert "- file2.txt (2048 bytes)" in result
            assert "Key: debug, Value: true" in result
            
    @patch('promabbix.core.template.get_jinja2_filters')
    @patch('promabbix.core.template.get_jinja2_tests')
    def test_template_with_builtin_filters(self, mock_tests, mock_filters):
        """Test template using various builtin filters."""
        mock_filters.return_value = {
            'basename': os.path.basename,
            'dirname': os.path.dirname,
            'json_loads': json.loads,
            'to_uuid4': to_uuid4
        }
        mock_tests.return_value = {}
        
        render = Render()
        
        template = """
        Path operations:
        - basename: {{ filepath | basename }}
        - dirname: {{ filepath | dirname }}
        
        JSON operations:
        - parsed: {{ json_data | json_loads }}
        
        UUID generation:
        - uuid4: {{ input_string | to_uuid4 }}
        """
        
        data = {
            "filepath": "/home/user/document.pdf",
            "json_data": '{"test": "value"}',
            "input_string": "test_input"
        }
        
        result = render.render(template, data)
        
        assert "basename: document.pdf" in result
        assert "dirname: /home/user" in result
        assert "parsed: {'test': 'value'}" in result
        assert "uuid4:" in result
        assert len(result.split("uuid4: ")[1].split("\n")[0].strip()) == 36


if __name__ == "__main__":
    pytest.main([__file__])
