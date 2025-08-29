#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import pytest
import json
from pathlib import Path

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.data_utils import isjson


class TestIsJsonFunction:
    """Test isjson function in data_utils module."""
    
    def test_isjson_valid_json_strings(self):
        """Test isjson with valid JSON strings."""
        valid_json_strings = [
            '{}',
            '[]',
            '{"key": "value"}',
            '{"number": 42}',
            '{"boolean": true}',
            '{"null_value": null}',
            '[1, 2, 3]',
            '["string", "array"]',
            '{"nested": {"object": "value"}}',
            '[{"mixed": "array"}, {"of": "objects"}]',
            '"simple string"',
            '42',
            'true',
            'false',
            'null',
            '0',
            '-1',
            '3.14',
            '1.23e-4',
        ]
        
        for json_str in valid_json_strings:
            assert isjson(json_str) is True, f"Failed for valid JSON: {json_str}"
    
    def test_isjson_invalid_json_strings(self):
        """Test isjson with invalid JSON strings."""
        invalid_json_strings = [
            '{',  # Unclosed brace
            '}',  # Unmatched brace
            '[',  # Unclosed bracket
            ']',  # Unmatched bracket
            '{"key": }',  # Missing value
            '{"key" "value"}',  # Missing colon
            '{key: "value"}',  # Unquoted key
            "{'key': 'value'}",  # Single quotes
            '{"key": "value",}',  # Trailing comma
            '[1, 2, 3,]',  # Trailing comma in array
            '{"key": undefined}',  # Undefined value
            'plain text',  # Plain text
            '',  # Empty string
            '{broken json',  # Malformed
            'function() {}',  # JavaScript function
            '<!-- comment -->',  # HTML comment
        ]
        
        for json_str in invalid_json_strings:
            assert isjson(json_str) is False, f"Failed for invalid JSON: {json_str}"
    
    def test_isjson_dict_objects(self):
        """Test isjson with dictionary objects."""
        dict_objects = [
            {},
            {"key": "value"},
            {"number": 42},
            {"boolean": True},
            {"null_value": None},
            {"nested": {"object": "value"}},
            {"mixed": ["array", "values"]},
            {"complex": {"nested": {"deeply": {"value": 123}}}},
        ]
        
        for dict_obj in dict_objects:
            assert isjson(dict_obj) is True, f"Failed for dict object: {dict_obj}"
    
    def test_isjson_list_objects(self):
        """Test isjson with list objects."""
        list_objects = [
            [],
            [1, 2, 3],
            ["string", "array"],
            [{"mixed": "array"}, {"of": "objects"}],
            [True, False, None],
            [[1, 2], [3, 4]],  # Nested lists
            [{"nested": "objects"}, ["and", "arrays"]],
        ]
        
        for list_obj in list_objects:
            assert isjson(list_obj) is True, f"Failed for list object: {list_obj}"
    
    def test_isjson_non_json_types(self):
        """Test isjson with non-JSON compatible types."""
        non_json_types = [
            42,  # Integer
            3.14,  # Float
            True,  # Boolean
            False,  # Boolean
            None,  # None
            set([1, 2, 3]),  # Set
            (1, 2, 3),  # Tuple
            bytes(b'binary data'),  # Bytes
            bytearray(b'binary data'),  # Bytearray
            lambda x: x,  # Function
            object(),  # Generic object
            complex(1, 2),  # Complex number
        ]
        
        for obj in non_json_types:
            assert isjson(obj) is False, f"Failed for non-JSON type: {type(obj).__name__} - {obj}"
    
    def test_isjson_edge_cases(self):
        """Test isjson with edge cases."""
        edge_cases = [
            ('   {}   ', True),  # JSON with whitespace
            ('\n{\n  "key": "value"\n}\n', True),  # JSON with newlines
            ('\t[\t1,\t2,\t3\t]\t', True),  # JSON with tabs
            ('{"unicode": "тест"}', True),  # Unicode content
            ('{"emoji": "🚀"}', True),  # Emoji content
            ('{"escaped": "line\\nbreak"}', True),  # Escaped characters
            ('{"quote": "He said \\"Hello\\""}', True),  # Escaped quotes
        ]
        
        for test_input, expected in edge_cases:
            assert isjson(test_input) is expected, f"Failed for edge case: {test_input}"
    
    def test_isjson_large_json(self):
        """Test isjson with large JSON structures."""
        # Large dictionary
        large_dict = {f"key_{i}": f"value_{i}" for i in range(1000)}
        assert isjson(large_dict) is True
        
        # Large array
        large_array = list(range(1000))
        assert isjson(large_array) is True
        
        # Large JSON string
        large_json_str = json.dumps(large_dict)
        assert isjson(large_json_str) is True
    
    def test_isjson_nested_structures(self):
        """Test isjson with deeply nested structures."""
        # Deeply nested dictionary
        nested_dict = {"level1": {"level2": {"level3": {"level4": "deep_value"}}}}
        assert isjson(nested_dict) is True
        
        # Deeply nested array
        nested_array = [[[["deep_value"]]]]
        assert isjson(nested_array) is True
        
        # Mixed nested structure
        mixed_nested = {
            "array": [1, 2, {"nested": ["deep", "array"]}],
            "object": {"nested": {"array": [1, 2, 3]}}
        }
        assert isjson(mixed_nested) is True
    
    def test_isjson_json_serializable_vs_json_string(self):
        """Test distinction between JSON-serializable objects and JSON strings."""
        # JSON-serializable objects should return True
        json_objects = [
            {"key": "value"},
            [1, 2, 3],
            {},
            []
        ]
        
        for obj in json_objects:
            assert isjson(obj) is True
            # Their string representations should also be valid JSON
            json_str = json.dumps(obj)
            assert isjson(json_str) is True
    
    def test_isjson_malformed_json_variations(self):
        """Test various malformed JSON patterns."""
        malformed_patterns = [
            '{"key": "value"',  # Missing closing brace
            '"key": "value"}',  # Missing opening brace
            '{"key": "value"}}',  # Extra closing brace
            '{{"key": "value"}',  # Extra opening brace
            '{"key": "value" "key2": "value2"}',  # Missing comma
            '{"key": "value",, "key2": "value2"}',  # Double comma
            '{"key": "value", "key2":}',  # Missing value
            '{"key": , "key2": "value2"}',  # Missing value after comma
            '[1, 2, 3',  # Missing closing bracket
            '1, 2, 3]',  # Missing opening bracket
            '[1, 2, 3]]',  # Extra closing bracket
            '[[1, 2, 3]',  # Extra opening bracket
            '[1,, 2, 3]',  # Double comma in array
            '[1, 2, 3, ]',  # Trailing comma
        ]
        
        for malformed in malformed_patterns:
            assert isjson(malformed) is False, f"Should be invalid JSON: {malformed}"
    
    def test_isjson_special_json_values(self):
        """Test isjson with special JSON values."""
        special_values = [
            ('null', True),
            ('true', True),
            ('false', True),
            ('0', True),
            ('-0', True),
            ('1', True),
            ('-1', True),
            ('1.0', True),
            ('-1.0', True),
            ('1e10', True),
            ('1E10', True),
            ('1e-10', True),
            ('1E-10', True),
            ('"string"', True),
            ('""', True),  # Empty string
            ('NaN', True),  # Python json.loads accepts NaN
            ('Infinity', True),  # Python json.loads accepts Infinity
            ('-Infinity', True),  # Python json.loads accepts -Infinity
            ('{"key": NaN}', True),  # NaN in object
            ('{"key": Infinity}', True),  # Infinity in object
            ('{"key": -Infinity}', True),  # -Infinity in object
        ]
        
        for value, expected in special_values:
            assert isjson(value) is expected, f"Failed for special JSON value: {value}"