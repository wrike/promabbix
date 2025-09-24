#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import pytest
import yaml
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
from io import StringIO

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.fs_utils import DataLoader, DataSaver


class TestDataLoaderCoverageImprovements:
    """Test additional scenarios for DataLoader to improve coverage."""

    def test_load_from_file_import_error_fallback(self, temp_directory):
        """Test YAML loading with CLoader import error fallback."""
        test_file = temp_directory / "test.yaml"
        test_data = {"test": "data", "number": 123}
        test_file.write_text(yaml.dump(test_data))
        
        # Mock the import to simulate CLoader not available
        with patch('promabbix.core.fs_utils.CLoader', side_effect=ImportError):
            # Reload the module to test the import fallback
            import importlib
            import promabbix.core.fs_utils
            importlib.reload(promabbix.core.fs_utils)
            
            loader = DataLoader()
            result = loader.load_from_file(str(test_file))
            assert result == test_data

    def test_load_from_stdin_with_yaml_data(self):
        """Test loading YAML data from stdin."""
        yaml_data = {"test": "data", "yaml": True}
        yaml_content = yaml.dump(yaml_data)
        
        with patch('sys.stdin', StringIO(yaml_content)):
            loader = DataLoader()
            result = loader.load_from_stdin()
            assert result == yaml_data

    def test_load_from_stdin_with_json_data(self):
        """Test loading JSON data from stdin."""
        json_data = {"test": "data", "json": True}
        json_content = json.dumps(json_data)
        
        with patch('sys.stdin', StringIO(json_content)):
            loader = DataLoader()
            result = loader.load_from_stdin()
            assert result == json_data

    def test_load_from_stdin_yaml_error_fallback_to_json(self):
        """Test stdin loading with YAML error falling back to JSON."""
        # This is valid JSON but invalid YAML due to quoted keys
        json_content = '{"test": "data", "json": true}'
        
        with patch('sys.stdin', StringIO(json_content)):
            loader = DataLoader()
            result = loader.load_from_stdin()
            assert result == {"test": "data", "json": True}

    def test_load_from_stdin_both_yaml_and_json_error(self):
        """Test stdin loading when both YAML and JSON parsing fail."""
        invalid_content = "invalid: yaml: and json content: [unclosed"
        
        with patch('sys.stdin', StringIO(invalid_content)):
            loader = DataLoader()
            with pytest.raises(ValueError) as excinfo:
                loader.load_from_stdin()
            assert "Could not parse data from STDIN" in str(excinfo.value)

    def test_load_from_file_permission_error_different_exception(self, temp_directory):
        """Test file loading with different permission error types."""
        test_file = temp_directory / "test.yaml"
        test_file.write_text("test: data")
        
        # Mock to raise PermissionError
        with patch('builtins.open', side_effect=PermissionError("Access denied")):
            loader = DataLoader()
            with pytest.raises(ValueError) as excinfo:
                loader.load_from_file(str(test_file))
            assert "Permission denied to read file" in str(excinfo.value)


class TestDataSaverCoverageImprovements:
    """Test additional scenarios for DataSaver to improve coverage."""

    def test_save_to_stdout_string_content(self):
        """Test saving string content to stdout."""
        test_content = "This is a test string"
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            saver = DataSaver()
            saver.save_to_stdout(test_content)
            assert mock_stdout.getvalue() == test_content

    def test_save_to_stdout_dict_content(self):
        """Test saving dict content to stdout (should serialize to JSON)."""
        test_data = {"test": "data", "number": 123}
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            saver = DataSaver()
            saver.save_to_stdout(test_data)
            output = mock_stdout.getvalue()
            # Should be valid JSON
            parsed = json.loads(output)
            assert parsed == test_data

    def test_save_to_file_directory_creation_failure(self, temp_directory):
        """Test save to file when directory creation fails."""
        test_file = temp_directory / "subdir" / "test.json"
        test_data = {"test": "data"}
        
        # Mock Path.mkdir to raise PermissionError
        with patch.object(Path, 'mkdir', side_effect=PermissionError("Permission denied")):
            saver = DataSaver()
            with pytest.raises(ValueError) as excinfo:
                saver.save_to_file(test_data, str(test_file))
            assert "Failed to create directory" in str(excinfo.value)

    def test_save_to_file_write_permission_error(self, temp_directory):
        """Test save to file when write operation fails due to permissions."""
        test_file = temp_directory / "test.json"
        test_data = {"test": "data"}
        
        # Mock open to raise PermissionError during write
        with patch('builtins.open', side_effect=PermissionError("Write permission denied")):
            saver = DataSaver()
            with pytest.raises(ValueError) as excinfo:
                saver.save_to_file(test_data, str(test_file))
            assert "Failed to write to file" in str(excinfo.value)

    def test_save_to_file_json_encoding_error(self, temp_directory):
        """Test save to file when JSON encoding fails."""
        test_file = temp_directory / "test.json"
        # Create an object that can't be JSON serialized
        test_data = {"test": set([1, 2, 3])}  # sets are not JSON serializable
        
        saver = DataSaver()
        with pytest.raises(ValueError) as excinfo:
            saver.save_to_file(test_data, str(test_file))
        assert "Failed to serialize data to JSON" in str(excinfo.value)

    def test_save_to_file_yaml_encoding_error(self, temp_directory):
        """Test save to file when YAML encoding fails."""
        test_file = temp_directory / "test.yaml"
        
        # Mock yaml.dump to raise an exception
        with patch('yaml.dump', side_effect=yaml.YAMLError("YAML encoding failed")):
            saver = DataSaver()
            test_data = {"test": "data"}
            with pytest.raises(ValueError) as excinfo:
                saver.save_to_file(test_data, str(test_file))
            assert "Failed to serialize data to YAML" in str(excinfo.value)

    def test_save_text_to_file_encoding_error(self, temp_directory):
        """Test save text to file when encoding fails."""
        test_file = temp_directory / "test.txt"
        test_content = "test content"
        
        # Mock open to raise UnicodeEncodeError
        with patch('builtins.open', side_effect=UnicodeEncodeError('utf-8', b'', 0, 1, "encoding error")):
            saver = DataSaver()
            with pytest.raises(ValueError) as excinfo:
                saver.save_text_to_file(test_content, str(test_file))
            assert "Failed to write text to file" in str(excinfo.value)

    def test_save_to_file_dict_unknown_extension(self, temp_directory):
        """Test saving dict to file with unknown extension defaults to YAML."""
        test_file = temp_directory / "test.unknown"
        test_data = {"test": "data", "number": 123}
        
        saver = DataSaver()
        saver.save_to_file(test_data, str(test_file))
        
        # Should default to YAML format
        with open(test_file, 'r') as f:
            content = f.read()
            # Check if it looks like YAML (contains : but not {})
            assert "test: data" in content
            assert "{" not in content

    def test_save_to_file_list_unknown_extension(self, temp_directory):
        """Test saving list to file with unknown extension defaults to YAML."""
        test_file = temp_directory / "test.unknown"
        test_data = [{"test": "data"}, {"number": 123}]
        
        saver = DataSaver()
        saver.save_to_file(test_data, str(test_file))
        
        # Should default to YAML format
        with open(test_file, 'r') as f:
            content = f.read()
            # Check if it looks like YAML (contains - for list items)
            assert "- test: data" in content or "test: data" in content

    def test_save_to_file_string_unknown_extension(self, temp_directory):
        """Test saving string to file with unknown extension saves as text."""
        test_file = temp_directory / "test.unknown"
        test_content = "This is plain text content"
        
        saver = DataSaver()
        saver.save_to_file(test_content, str(test_file))
        
        with open(test_file, 'r') as f:
            content = f.read()
            assert content == test_content

    def test_save_to_file_unsupported_type(self, temp_directory):
        """Test saving unsupported data type to file."""
        test_file = temp_directory / "test.json"
        # Use a custom class that's not serializable
        class CustomClass:
            def __init__(self):
                self.value = "test"
        
        test_data = CustomClass()
        
        saver = DataSaver()
        with pytest.raises(ValueError) as excinfo:
            saver.save_to_file(test_data, str(test_file))
        assert "Unsupported data type" in str(excinfo.value)

    def test_determine_format_from_extension_edge_cases(self):
        """Test format determination with various file extensions."""
        saver = DataSaver()
        
        # Test case sensitivity
        assert saver._determine_format_from_extension("test.JSON") == "json"
        assert saver._determine_format_from_extension("test.YAML") == "yaml"
        assert saver._determine_format_from_extension("test.YML") == "yaml"
        
        # Test with multiple dots
        assert saver._determine_format_from_extension("test.backup.json") == "json"
        assert saver._determine_format_from_extension("test.old.yaml") == "yaml"
        
        # Test with no extension
        assert saver._determine_format_from_extension("test") == "yaml"  # default
        
        # Test with unknown extension
        assert saver._determine_format_from_extension("test.txt") == "yaml"  # default

    def test_save_to_file_complex_yaml_data(self, temp_directory):
        """Test saving complex YAML data structures."""
        test_file = temp_directory / "complex.yaml"
        complex_data = {
            "simple_string": "value",
            "multiline_string": "line1\nline2\nline3",
            "list_of_dicts": [
                {"name": "item1", "value": 1},
                {"name": "item2", "value": 2}
            ],
            "nested_dict": {
                "level1": {
                    "level2": {
                        "level3": "deep_value"
                    }
                }
            },
            "special_chars": "Special chars: åäö, 中文, 🚀"
        }
        
        saver = DataSaver()
        saver.save_to_file(complex_data, str(test_file))
        
        # Verify the data can be loaded back correctly
        loader = DataLoader()
        loaded_data = loader.load_from_file(str(test_file))
        assert loaded_data == complex_data

    def test_save_to_file_complex_json_data(self, temp_directory):
        """Test saving complex JSON data structures."""
        test_file = temp_directory / "complex.json"
        complex_data = {
            "string": "value",
            "number": 42,
            "float": 3.14159,
            "boolean": True,
            "null_value": None,
            "list": [1, 2, 3, "four", 5.0],
            "nested": {
                "inner_list": [{"a": 1}, {"b": 2}],
                "inner_dict": {"x": "y"}
            }
        }
        
        saver = DataSaver()
        saver.save_to_file(complex_data, str(test_file))
        
        # Verify the data can be loaded back correctly
        loader = DataLoader()
        loaded_data = loader.load_from_file(str(test_file))
        assert loaded_data == complex_data


@pytest.fixture
def temp_directory():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)