# Tests for Promabbix

This directory contains unit tests for the Promabbix project.

## Test Structure

- `test_template_basic.py` - Basic tests for template utility functions that don't require external dependencies
- `test_template.py` - Comprehensive tests for the template module (requires mocking of ansible dependencies)
- `conftest.py` - Shared test fixtures and configuration

## Running Tests

### Prerequisites

Install test dependencies:
```bash
pip install pytest pytest-cov pytest-mock
```

### Running All Tests

From the project root directory:

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run with coverage
python3 -m pytest tests/ -v --cov=src/promabbix --cov-report=term-missing

# Run specific test file
python3 -m pytest tests/test_template_basic.py -v
```

### Using the Test Runner Script

You can also use the provided test runner script:

```bash
python3 run_tests.py
```

This script will:
- Automatically install test dependencies if needed
- Set up the correct Python path
- Run tests with coverage if available
- Accept additional pytest arguments

## Test Categories

### Basic Tests (`test_template_basic.py`)
These tests cover the core utility functions without external dependencies:
- `date_time()` function with various formats
- `to_uuid4()` function with different inputs
- UUID format validation and consistency

### Comprehensive Tests (`test_template.py`)
These tests cover the full template functionality with mocked dependencies:
- Jinja2 environment configuration
- Template rendering from strings and files
- Error handling and validation
- Custom filters, tests, and globals
- Integration scenarios

## Test Coverage

The tests aim to cover:
- ✅ Utility functions (`date_time`, `to_uuid4`)
- ✅ Jinja2 configuration functions
- ✅ Render class initialization and configuration
- ✅ Template validation (`is_template`)
- ✅ String template rendering
- ✅ File template rendering
- ✅ Error handling and edge cases
- ✅ Custom filters, tests, and globals
- ✅ Integration scenarios

## Mocking Strategy

Since the template module depends on ansible plugins that may not be available in the test environment, the comprehensive tests use extensive mocking:

- `ansible.plugins.filter.core.*` functions are mocked
- `ansible.plugins.test.core.*` functions are mocked
- `promabbix.core.data_utils.*` functions are mocked

This allows the tests to focus on the template logic without requiring the full ansible installation.

## Adding New Tests

When adding new tests:

1. For simple utility functions, add them to `test_template_basic.py`
2. For complex functionality requiring mocks, add them to `test_template.py`
3. Use descriptive test names that explain what is being tested
4. Include both positive and negative test cases
5. Mock external dependencies appropriately
6. Add docstrings explaining the test purpose

## Continuous Integration

These tests are designed to run in CI environments without requiring external dependencies beyond what's specified in `requirements-dev.txt`.