#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

"""
Basic tests for template module that don't require external dependencies.
"""

import pytest
import tempfile
import json
import os
import uuid
import hashlib
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.template import date_time, to_uuid4


class TestBasicUtilityFunctions:
    """Test basic utility functions that don't require external dependencies."""
    
    def test_date_time_valid_format(self):
        """Test date_time function with valid format."""
        result = date_time("%Y-%m-%d")
        # Should return current date in YYYY-MM-DD format
        assert len(result) == 10
        assert result.count('-') == 2
        
    def test_date_time_invalid_format(self):
        """Test date_time function with invalid format."""
        # Mock strftime to raise an exception
        with patch('promabbix.core.template.datetime') as mock_datetime:
            mock_dt = MagicMock()
            mock_dt.strftime.side_effect = ValueError("Invalid format")
            mock_datetime.fromtimestamp.return_value = mock_dt
            
            result = date_time("%invalid")
            assert result == 'unknown'
        
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
        
    def test_to_uuid4_known_values(self):
        """Test to_uuid4 function with known input/output pairs."""
        # Test with a known string to ensure consistent hashing
        test_input = "hello world"
        result = to_uuid4(test_input)
        
        # The result should be deterministic based on MD5 hash
        expected_md5 = hashlib.md5(test_input.encode("UTF-8")).hexdigest()
        expected_uuid = str(uuid.UUID(hex=expected_md5, version=4))
        
        assert result == expected_uuid


if __name__ == "__main__":
    pytest.main([__file__])