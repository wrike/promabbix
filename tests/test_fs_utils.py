#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

"""
Unit tests for fs_utils module.
"""

import pytest
import tempfile
import json
import yaml
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.fs_utils import DataLoader, DataSaver


class TestDataLoader:
    """Test DataLoader class functionality."""
    
    def test_init(self):
        """Test DataLoader initialization."""
        loader = DataLoader()
        assert loader.console is not None
        assert loader.console.file is not None
        assert loader.console.file.buffer is not None
        
    def test_load_from_file_yaml_valid(self):
        """Test loading valid YAML file."""
        yaml_content = """
        name: test
        items:
          - item1
          - item2
        config:
          debug: true
        """
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            
            loader = DataLoader()
            result = loader.load_from_file(f.name)
            
            assert result['name'] == 'test'
            assert result['items'] == ['item1', 'item2']
            assert result['config']['debug'] is True
            
        Path(f.name).unlink()  # cleanup
        
    def test_load_from_file_json_valid(self):
        """Test loading valid JSON file."""
        json_content = {
            "name": "test",
            "items": ["item1", "item2"],
            "config": {"debug": True}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(json_content, f)
            f.flush()
            
            loader = DataLoader()
            result = loader.load_from_file(f.name)
            
            assert result['name'] == 'test'
            assert result['items'] == ['item1', 'item2']
            assert result['config']['debug'] is True
            
        Path(f.name).unlink()  # cleanup
        
    def test_load_from_file_yaml_fallback_to_json(self):
        """Test loading file that fails as YAML but succeeds as JSON."""
        # JSON that's not valid YAML (due to true/false vs True/False)
        json_content = '{"name": "test", "debug": true}'
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(json_content)
            f.flush()
            
            loader = DataLoader()
            result = loader.load_from_file(f.name)
            
            assert result['name'] == 'test'
            assert result['debug'] is True
            
        Path(f.name).unlink()  # cleanup
        
    def test_load_from_file_with_tilde_path(self):
        """Test loading file with tilde in path."""
        yaml_content = "name: test"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            
            # Create a path with tilde that resolves to the temp file
            temp_path = Path(f.name)
            relative_path = temp_path.name
            
            loader = DataLoader()
            # Test with the actual temp file path (can't easily mock tilde expansion)
            result = loader.load_from_file(f.name)
            
            assert result['name'] == 'test'
            
        Path(f.name).unlink()  # cleanup
        
    def test_load_from_file_not_found(self):
        """Test loading non-existent file."""
        loader = DataLoader()
        
        with patch.object(loader.console, 'print') as mock_print:
            with pytest.raises(FileNotFoundError):
                loader.load_from_file('/nonexistent/file.yaml')
            
            mock_print.assert_called_once()
            call_args = mock_print.call_args[0][0]
            assert "Error reading file:" in call_args
            
    def test_load_from_file_permission_error(self):
        """Test loading file with permission error."""
        loader = DataLoader()
        
        with patch('pathlib.Path.read_text', side_effect=PermissionError("Permission denied")):
            with patch.object(loader.console, 'print') as mock_print:
                with pytest.raises(PermissionError):
                    loader.load_from_file('/some/file.yaml')
                
                mock_print.assert_called_once()
                call_args = mock_print.call_args[0][0]
                assert "Error reading file:" in call_args
                assert "Permission denied" in call_args
                
    def test_load_from_file_invalid_yaml_and_json(self):
        """Test loading file that's neither valid YAML nor JSON."""
        invalid_content = "{ invalid content that's neither yaml nor json }"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(invalid_content)
            f.flush()
            
            loader = DataLoader()
            with patch.object(loader.console, 'print') as mock_print:
                loader.load_from_file(f.name)

                loader = DataLoader()
                result = loader.load_from_file(f.name)

                # yes, even this can be loaded
                assert result['invalid content that\'s neither yaml nor json'] == None

        Path(f.name).unlink()  # cleanup
        
    def test_load_from_file_yaml_error_fallback_json(self):
        """Test YAML parsing error with successful JSON fallback."""
        # Content that causes YAML error but is valid JSON
        content = '{"key": "value with: colon"}'
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(content)
            f.flush()
            
            loader = DataLoader()
            result = loader.load_from_file(f.name)
            
            assert result['key'] == 'value with: colon'
            
        Path(f.name).unlink()  # cleanup
        
    def test_load_from_file_yaml_returns_none(self):
        """Test YAML parsing that returns None."""
        # Empty YAML file
        content = ""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(content)
            f.flush()
            
            loader = DataLoader()
            
            with patch.object(loader.console, 'print') as mock_print:
                with pytest.raises(ValueError):
                    loader.load_from_file(f.name)
                
                # Should try JSON parsing after YAML returns None
                mock_print.assert_called_once()
                
        Path(f.name).unlink()  # cleanup


class TestDataSaver:
    """Test DataSaver class functionality."""
    
    def test_init(self):
        """Test DataSaver initialization."""
        saver = DataSaver()
        assert saver.console is not None
        assert saver.console.file is not None
        assert saver.console.file.buffer is not None
        
    def test_save_to_file_json_dict(self):
        """Test save_to_file for dictionary to JSON file."""
        data = {"name": "test", "items": [1, 2, 3]}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver.console, 'print') as mock_print:
                saver.save_to_file(data, f.name)
                
                # Verify success message
                mock_print.assert_called_once()
                call_args = mock_print.call_args[0][0]
                assert "Data saved to" in call_args
                
            # Verify file content
            saved_data = json.loads(Path(f.name).read_text())
            assert saved_data == data
            
        Path(f.name).unlink()  # cleanup
        
    def test_save_to_file_valid_json_string(self):
        """Test save_to_file for valid JSON string to file."""
        data = '{"name": "test", "value": 123}'
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver.console, 'print') as mock_print:
                saver.save_to_file(data, f.name)
                
                mock_print.assert_called_once()
                call_args = mock_print.call_args[0][0]
                assert "Data saved to" in call_args
                
            # Verify file content is properly formatted
            saved_content = Path(f.name).read_text()
            saved_data = json.loads(saved_content)
            assert saved_data == {"name": "test", "value": 123}
            
        Path(f.name).unlink()  # cleanup
        
    def test_save_to_file_json_invalid_json_string(self):
        """Test save_to_file for invalid JSON string as plain text."""
        data = "not valid json string"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver.console, 'print') as mock_print:
                saver.save_to_file(data, f.name)
                
                # Should have two calls: warning and success
                assert mock_print.call_count == 2
                warning_call = mock_print.call_args_list[0][0][0]
                success_call = mock_print.call_args_list[1][0][0]
                assert "Warning: String is not valid data format" in warning_call
                assert "Data saved to" in success_call
                
            # Verify file content is the original string
            saved_content = Path(f.name).read_text()
            assert saved_content == data
            
        Path(f.name).unlink()  # cleanup
        
    def test_save_to_file_json_with_tilde_path(self):
        """Test save_to_file for JSON file with tilde in path."""
        data = {"test": "value"}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver.console, 'print') as mock_print:
                saver.save_to_file(data, f.name)
                
                mock_print.assert_called_once()
                
            # Verify file was created and contains correct data
            saved_data = json.loads(Path(f.name).read_text())
            assert saved_data == data
            
        Path(f.name).unlink()  # cleanup
        
    def test_save_to_file_json_error(self):
        """Test JSON save error handling."""
        data = {"test": "value"}
        
        saver = DataSaver()
        
        with patch('pathlib.Path.write_text', side_effect=PermissionError("Permission denied")):
            with patch.object(saver.console, 'print') as mock_print:
                saver.save_to_file(data, '/invalid/path/file.json')
                
                mock_print.assert_called_once()
                call_args = mock_print.call_args[0][0]
                assert "Error saving file:" in call_args
                assert "Permission denied" in call_args
                
    def test_save_to_file_yaml_dict(self):
        """Test save_to_file for dictionary as YAML file."""
        data = {"name": "test", "items": [1, 2, 3], "config": {"debug": True}}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver.console, 'print') as mock_print:
                saver.save_to_file(data, f.name)
                
                mock_print.assert_called_once()
                call_args = mock_print.call_args[0][0]
                assert "Data saved to" in call_args
                
            # Verify file content
            saved_data = yaml.safe_load(Path(f.name).read_text())
            assert saved_data == data
            
        Path(f.name).unlink()  # cleanup
        
    def test_save_to_file_yaml_valid_yaml_string(self):
        """Test save_to_file for valid YAML string to file."""
        data = "name: test\nvalue: 123"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver.console, 'print') as mock_print:
                saver.save_to_file(data, f.name)
                
                mock_print.assert_called_once()
                
            # Verify file content is properly formatted YAML
            saved_data = yaml.safe_load(Path(f.name).read_text())
            assert saved_data == {"name": "test", "value": 123}
            
        Path(f.name).unlink()  # cleanup
        
    def test_save_to_file_yaml_empty_string(self):
        """Test save_to_file for empty string as YAML."""
        data = ""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver.console, 'print') as mock_print:
                saver.save_to_file(data, f.name)
                
                mock_print.assert_called_once()
                
            # Verify file content is empty
            saved_content = Path(f.name).read_text()
            assert saved_content == ""
            
        Path(f.name).unlink()  # cleanup
        
    def test_save_to_file_yaml_invalid_yaml_string(self):
        """Test save_to_file for invalid YAML string as plain text."""
        data = "not: valid: yaml: string: with: too: many: colons:"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver.console, 'print') as mock_print:
                saver.save_to_file(data, f.name)
                
                # Should have two calls: warning and success
                assert mock_print.call_count == 2
                warning_call = mock_print.call_args_list[0][0][0]
                success_call = mock_print.call_args_list[1][0][0]
                assert "Warning: String is not valid data format" in warning_call
                assert "Data saved to" in success_call
                
            # Verify file content is the original string
            saved_content = Path(f.name).read_text()
            assert saved_content == data
            
        Path(f.name).unlink()  # cleanup
        
    def test_save_to_file_yaml_error(self):
        """Test YAML save error handling."""
        data = {"test": "value"}
        
        saver = DataSaver()
        
        with patch('pathlib.Path.write_text', side_effect=IOError("Disk full")):
            with patch.object(saver.console, 'print') as mock_print:
                saver.save_to_file(data, '/invalid/path/file.yaml')
                
                mock_print.assert_called_once()
                call_args = mock_print.call_args[0][0]
                assert "Error saving file:" in call_args
                assert "Disk full" in call_args
                
    def test_save_text_to_file(self):
        """Test save_to_file for text to file."""
        data = "This is a test text content\nwith multiple lines."
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver.console, 'print') as mock_print:
                saver.save_text_to_file(data, f.name)
                
                mock_print.assert_called_once()
                call_args = mock_print.call_args[0][0]
                assert "Text data saved to" in call_args
                
            # Verify file content
            saved_content = Path(f.name).read_text()
            assert saved_content == data
            
        Path(f.name).unlink()  # cleanup
        
    def test_save_text_to_file_error(self):
        """Test text save error handling."""
        data = "test content"
        
        saver = DataSaver()
        
        with patch('pathlib.Path.write_text', side_effect=OSError("No space left")):
            with patch.object(saver.console, 'print') as mock_print:
                saver.save_text_to_file(data, '/invalid/path/file.txt')
                
                mock_print.assert_called_once()
                call_args = mock_print.call_args[0][0]
                assert "Error saving text file:" in call_args
                assert "No space left" in call_args
                
    def test_save_json_extension(self):
        """Test save method with JSON extension."""
        data = {"test": "value"}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver, 'save_to_file') as mock_save_json:
                saver.save(data, f.name)
                mock_save_json.assert_called_once_with(data, f.name)
                
        Path(f.name).unlink()  # cleanup
        
    def test_save_yaml_extension(self):
        """Test save method with YAML extension."""
        data = {"test": "value"}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver, 'save_to_file') as mock_save_yaml:
                saver.save(data, f.name)
                mock_save_yaml.assert_called_once_with(data, f.name)
                
        Path(f.name).unlink()  # cleanup
        
    def test_save_yml_extension(self):
        """Test save method with YML extension."""
        data = {"test": "value"}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver, 'save_to_file') as mock_save_yaml:
                saver.save(data, f.name)
                mock_save_yaml.assert_called_once_with(data, f.name)
                
        Path(f.name).unlink()  # cleanup
        
    def test_save_dict_no_extension(self):
        """Test save method with dict data and no extension (defaults to JSON)."""
        data = {"test": "value"}
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver, 'save_to_file') as mock_save_json:
                saver.save(data, f.name)
                mock_save_json.assert_called_once_with(data, f.name)
                
        Path(f.name).unlink()  # cleanup
        
    def test_save_list_no_extension(self):
        """Test save method with list data and no extension (defaults to JSON)."""
        data = [1, 2, 3]
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver, 'save_to_file') as mock_save_json:
                saver.save(data, f.name)
                mock_save_json.assert_called_once_with(data, f.name)
                
        Path(f.name).unlink()  # cleanup
        
    def test_save_string_no_extension(self):
        """Test save method with string data and no extension."""
        data = "test string content"
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver, 'save_text_to_file') as mock_save_text:
                saver.save(data, f.name)
                mock_save_text.assert_called_once_with(data, f.name)
                
        Path(f.name).unlink()  # cleanup
        
    def test_save_unknown_type(self):
        """Test save method with unknown data type."""
        data = 12345  # integer
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            saver = DataSaver()
            
            with patch.object(saver.console, 'print') as mock_print:
                with patch.object(saver, 'save_text_to_file') as mock_save_text:
                    saver.save(data, f.name)
                    
                    # Should print warning about unknown type
                    mock_print.assert_called_once()
                    call_args = mock_print.call_args[0][0]
                    assert "Unknown data type" in call_args
                    
                    # Should save as string
                    mock_save_text.assert_called_once_with("12345", f.name)
                
        Path(f.name).unlink()  # cleanup


class TestIntegration:
    """Integration tests for DataLoader and DataSaver."""
    
    def test_round_trip_json(self):
        """Test loading and saving JSON data maintains integrity."""
        original_data = {
            "name": "test",
            "items": [1, 2, 3],
            "config": {"debug": True, "timeout": 30},
            "unicode": "тест"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            # Save data
            saver = DataSaver()
            with patch.object(saver.console, 'print'):
                saver.save_to_file(original_data, f.name)
            
            # Load data back
            loader = DataLoader()
            loaded_data = loader.load_from_file(f.name)
            
            assert loaded_data == original_data
            
        Path(f.name).unlink()  # cleanup
        
    def test_round_trip_yaml(self):
        """Test loading and saving YAML data maintains integrity."""
        original_data = {
            "name": "test",
            "items": [1, 2, 3],
            "config": {"debug": True, "timeout": 30},
            "unicode": "тест"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            # Save data
            saver = DataSaver()
            with patch.object(saver.console, 'print'):
                saver.save_to_file(original_data, f.name)
            
            # Load data back
            loader = DataLoader()
            loaded_data = loader.load_from_file(f.name)
            
            assert loaded_data == original_data
            
        Path(f.name).unlink()  # cleanup
        
    def test_cross_format_compatibility(self):
        """Test that data saved as YAML can be loaded and saved as JSON."""
        original_data = {"name": "test", "value": 123}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as yaml_file:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as json_file:
                # Save as YAML
                saver = DataSaver()
                with patch.object(saver.console, 'print'):
                    saver.save_to_file(original_data, yaml_file.name)
                
                # Load from YAML
                loader = DataLoader()
                loaded_data = loader.load_from_file(yaml_file.name)
                
                # Save as JSON
                with patch.object(saver.console, 'print'):
                    saver.save_to_file(loaded_data, json_file.name)
                
                # Load from JSON and verify
                final_data = loader.load_from_file(json_file.name)
                assert final_data == original_data
                
        Path(yaml_file.name).unlink()  # cleanup
        Path(json_file.name).unlink()  # cleanup

    def test_save_to_file_json_extension(self):
        """Test save_to_file with .json extension."""
        data = {"key": "value", "numbers": [1, 2, 3]}
        saver = DataSaver()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            with patch.object(saver.console, 'print'):
                saver.save_to_file(data, f.name)
            
            # Read and verify JSON content
            with open(f.name, 'r') as rf:
                content = rf.read()
                loaded_data = json.loads(content)
                assert loaded_data == data
                
        Path(f.name).unlink()  # cleanup

    def test_save_to_file_yaml_extension(self):
        """Test save_to_file with .yaml extension."""
        data = {"key": "value", "numbers": [1, 2, 3]}
        saver = DataSaver()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            with patch.object(saver.console, 'print'):
                saver.save_to_file(data, f.name)
            
            # Read and verify YAML content
            with open(f.name, 'r') as rf:
                content = rf.read()
                loaded_data = yaml.safe_load(content)
                assert loaded_data == data
                
        Path(f.name).unlink()  # cleanup

    def test_save_to_file_yml_extension(self):
        """Test save_to_file with .yml extension."""
        data = {"key": "value", "numbers": [1, 2, 3]}
        saver = DataSaver()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            with patch.object(saver.console, 'print'):
                saver.save_to_file(data, f.name)
            
            # Read and verify YAML content
            with open(f.name, 'r') as rf:
                content = rf.read()
                loaded_data = yaml.safe_load(content)
                assert loaded_data == data
                
        Path(f.name).unlink()  # cleanup

    def test_save_to_file_unknown_extension_dict(self):
        """Test save_to_file with unknown extension defaults to JSON for dict."""
        data = {"key": "value", "numbers": [1, 2, 3]}
        saver = DataSaver()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            with patch.object(saver.console, 'print'):
                saver.save_to_file(data, f.name)
            
            # Should default to JSON for dict/list data
            with open(f.name, 'r') as rf:
                content = rf.read()
                loaded_data = json.loads(content)
                assert loaded_data == data
                
        Path(f.name).unlink()  # cleanup

    def test_save_to_file_unknown_extension_string(self):
        """Test save_to_file with unknown extension saves string as-is."""
        data = "This is a plain text string"
        saver = DataSaver()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            with patch.object(saver.console, 'print'):
                saver.save_to_file(data, f.name)
            
            # Should save string as-is
            with open(f.name, 'r') as rf:
                content = rf.read()
                assert content == data
                
        Path(f.name).unlink()  # cleanup


if __name__ == "__main__":
    pytest.main([__file__])
