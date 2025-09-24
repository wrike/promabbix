#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import pytest
import tempfile
from pathlib import Path
import sys
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.template import Render, get_jinja2_filters, get_jinja2_globals, get_jinja2_tests
from jinja2 import TemplateSyntaxError, TemplateRuntimeError


class TestTemplateCoverageImprovements:
    """Test additional scenarios for template rendering to improve coverage."""

    def test_render_with_template_syntax_error_line_number(self, temp_directory):
        """Test render error handling with line number information."""
        renderer = Render()
        
        # Create a template with syntax error on a specific line
        invalid_template = """
Valid line 1
{% if condition %}
    Valid line 3
{% invalid_syntax_here
Another line
"""
        
        result = renderer.render(invalid_template, {})
        assert result == ""  # Should return empty string on error

    def test_render_with_template_syntax_error_no_line_number(self, temp_directory):
        """Test render error handling without line number information."""
        renderer = Render()
        
        # Mock TemplateSyntaxError without lineno attribute
        with patch.object(renderer.jinja_env, 'from_string') as mock_from_string:
            mock_template = MagicMock()
            mock_template.render.side_effect = TemplateSyntaxError("Syntax error without line number")
            mock_from_string.return_value = mock_template
            
            result = renderer.render("{{ invalid_template }}", {})
            assert result == ""

    def test_render_with_generic_exception(self, temp_directory):
        """Test render error handling with generic exception."""
        renderer = Render()
        
        # Mock to raise a generic exception
        with patch.object(renderer.jinja_env, 'from_string') as mock_from_string:
            mock_from_string.side_effect = RuntimeError("Generic error")
            
            result = renderer.render("{{ template }}", {})
            assert result == ""

    def test_is_template_with_template_syntax_error_details(self, temp_directory):
        """Test is_template method with detailed syntax error handling."""
        renderer = Render()
        
        # Template with syntax error that should provide line details
        invalid_template = """
Line 1
Line 2
{% if condition
Line 4 with error
"""
        
        result = renderer.is_template(invalid_template)
        assert result is False

    def test_is_template_with_syntax_error_no_lines(self, temp_directory):
        """Test is_template method when template has no newlines."""
        renderer = Render()
        
        # Single line template with syntax error
        invalid_template = "{% invalid syntax"
        
        result = renderer.is_template(invalid_template)
        assert result is False

    def test_render_file_with_search_path_update(self, temp_directory):
        """Test render_file method that updates search path."""
        # Create a template file
        template_file = temp_directory / "test_template.j2"
        template_content = """
Hello {{ name }}!
Your age is {{ age }}.
"""
        template_file.write_text(template_content.strip())
        
        # Create another template in a subdirectory
        subdir = temp_directory / "subdir"
        subdir.mkdir()
        sub_template = subdir / "sub_template.j2"
        sub_template.write_text("Sub template: {{ value }}")
        
        renderer = Render()
        
        # Test rendering with search path update
        result = renderer.render_file(
            template_path=str(temp_directory),
            template_name="test_template.j2",
            data={"name": "Alice", "age": 30}
        )
        
        expected = "Hello Alice!\nYour age is 30."
        assert result.strip() == expected

    def test_render_file_search_path_restoration(self, temp_directory):
        """Test that search path is properly restored after render_file."""
        template_file = temp_directory / "test_template.j2"
        template_file.write_text("Hello {{ name }}!")
        
        renderer = Render(searchpath="/original/path")
        original_searchpath = renderer.searchpath
        
        # Render file with different search path
        result = renderer.render_file(
            template_path=str(temp_directory),
            template_name="test_template.j2",
            data={"name": "Bob"}
        )
        
        # Verify search path is restored
        assert renderer.searchpath == original_searchpath
        assert "Hello Bob!" in result

    def test_render_file_with_none_template_path(self, temp_directory):
        """Test render_file with None template_path."""
        renderer = Render()
        
        # This should attempt to render without changing search path
        # Since no file will be found, it should fall back to string rendering
        result = renderer.render_file(
            template_path=None,
            template_name="Hello {{ name }}!",
            data={"name": "Charlie"}
        )
        
        assert "Hello Charlie!" in result

    def test_render_file_jinja_environment_recreation(self, temp_directory):
        """Test that Jinja environment is properly recreated with new search path."""
        template_file = temp_directory / "test_template.j2"
        template_file.write_text("Template content: {{ value | upper }}")
        
        renderer = Render()
        
        # Verify that filters are preserved when environment is recreated
        result = renderer.render_file(
            template_path=str(temp_directory),
            template_name="test_template.j2",
            data={"value": "hello"}
        )
        
        assert "HELLO" in result

    def test_render_file_with_missing_template_fallback(self, temp_directory):
        """Test render_file fallback to string rendering when template file missing."""
        renderer = Render()
        
        # Try to render non-existent template file
        result = renderer.render_file(
            template_path=str(temp_directory),
            template_name="{{ greeting }} {{ name }}!",
            data={"greeting": "Hi", "name": "David"}
        )
        
        # Should fall back to string rendering
        assert "Hi David!" in result

    def test_do_template_method(self):
        """Test the do_template public method."""
        renderer = Render()
        
        template = "Hello {{ name }}, you are {{ age }} years old."
        data = {"name": "Eve", "age": 25}
        
        result = renderer.do_template(data, template)
        assert result == "Hello Eve, you are 25 years old."

    def test_render_with_complex_template_and_filters(self):
        """Test rendering with complex template using various filters."""
        renderer = Render()
        
        template = """
{%- set items = ['apple', 'banana', 'cherry'] -%}
Items: {{ items | join(', ') | upper }}
Count: {{ items | length }}
First: {{ items | first | title }}
Last: {{ items | last | capitalize }}
"""
        
        result = renderer.render(template, {})
        
        assert "APPLE, BANANA, CHERRY" in result
        assert "Count: 3" in result
        assert "First: Apple" in result
        assert "Last: Cherry" in result

    def test_render_with_globals_and_tests(self):
        """Test rendering with custom globals and tests."""
        renderer = Render()
        
        # Test using lookup_template global (which maps to do_template)
        template = """
Main template
Sub result: {{ lookup_template(data, sub_template) }}
"""
        data = {
            "sub_template": "Hello {{ user }}!",
            "user": "Frank"
        }
        
        result = renderer.render(template, data)
        
        assert "Main template" in result
        assert "Hello Frank!" in result

    def test_render_with_custom_jinja_environment_settings(self, temp_directory):
        """Test that custom Jinja environment settings are preserved."""
        renderer = Render()
        
        # Test StrictUndefined behavior
        template = "Value: {{ undefined_variable }}"
        
        # Should raise error due to StrictUndefined
        result = renderer.render(template, {})
        assert result == ""  # Error should be caught and return empty string

    def test_get_jinja2_filters_function(self):
        """Test the get_jinja2_filters function."""
        filters = get_jinja2_filters()
        
        # Should return a dictionary of filters
        assert isinstance(filters, dict)
        # Should contain at least some basic filters
        assert len(filters) > 0

    def test_get_jinja2_globals_function(self):
        """Test the get_jinja2_globals function."""
        globals_dict = get_jinja2_globals()
        
        # Should return a dictionary of globals
        assert isinstance(globals_dict, dict)

    def test_get_jinja2_tests_function(self):
        """Test the get_jinja2_tests function."""
        tests = get_jinja2_tests()
        
        # Should return a dictionary of tests
        assert isinstance(tests, dict)

    def test_render_initialization_with_tilde_path(self):
        """Test Render initialization with tilde path expansion."""
        with patch('pathlib.Path.expanduser') as mock_expanduser:
            mock_expanduser.return_value = Path("/home/user/templates")
            
            renderer = Render(searchpath="~/templates")
            mock_expanduser.assert_called_once()

    def test_render_initialization_with_path_object(self):
        """Test Render initialization with Path object."""
        path_obj = Path("/some/path")
        renderer = Render(searchpath=path_obj)
        
        assert renderer.searchpath == path_obj

    def test_render_initialization_with_none_searchpath(self):
        """Test Render initialization with None searchpath."""
        renderer = Render(searchpath=None)
        
        assert renderer.searchpath is None


@pytest.fixture
def temp_directory():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)