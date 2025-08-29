#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import pytest
import tempfile
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def temp_directory():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def sample_template_files(temp_directory):
    """Create sample template files for testing."""
    templates = {
        "simple.j2": "Hello {{ name }}!",
        "complex.j2": """
        {## Complex template ##}
        Project: {{ project.name }}
        Version: {{ project.version }}
        
        Features:
        {%- for feature in project.features %}
        - {{ feature }}
        {%- endfor %}
        """,
        "with_filters.j2": "File: {{ filepath | basename }}, Date: {{ date_time('%Y-%m-%d') }}",
        "with_lookup.j2": "Result: {{ lookup_template(data, 'Value is {{ value }}') }}"
    }
    
    template_files = {}
    for filename, content in templates.items():
        template_file = temp_directory / filename
        template_file.write_text(content)
        template_files[filename] = template_file
    
    return template_files


@pytest.fixture
def sample_data():
    """Provide sample data for template testing."""
    return {
        "name": "World",
        "project": {
            "name": "Test Project",
            "version": "1.0.0",
            "features": ["feature1", "feature2", "feature3"]
        },
        "filepath": "/home/user/document.txt",
        "data": {"value": "test_value"}
    }