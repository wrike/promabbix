# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Promabbix is a tool that connects Prometheus to Zabbix monitoring. It converts Prometheus alert rules into Zabbix templates, allowing you to monitor Kubernetes/Prometheus metrics within Zabbix while maintaining your existing monitoring infrastructure.

## Key Architecture Components

### Core Application (`src/promabbix/promabbix.py`)
- **PromabbixApp**: Main application class that handles CLI arguments and orchestrates the conversion process
- Supports STDIN/STDOUT for pipeline usage or file-based input/output
- Uses dependency injection pattern for loader, saver, and parser components

### Core Modules (`src/promabbix/core/`)
- **template.py**: Jinja2-based template rendering engine with custom filters and globals from Ansible
  - `Render` class handles template processing with extensive Jinja2 customization
  - Integrates Ansible filters for data manipulation (combine, regex operations, JSON/YAML handling)
- **fs_utils.py**: File system operations for loading/saving YAML/JSON data
  - `DataLoader`: Handles input from files or STDIN with automatic YAML/JSON detection
  - `DataSaver`: Unified save_to_file method with format detection (.json/.yaml/.yml)
  - Supports both structured data and string content with smart format handling
- **validation.py**: Comprehensive configuration validation system
  - `ConfigValidator`: Schema validation with enhanced error reporting (supports both YAML and JSON schemas)
  - `CrossReferenceValidator`: Validates consistency between config sections
  - `SchemaValidator`: JSON Schema validation with detailed error messages and suggestions
  - Wiki documentation validation for alerts (optional but recommended)
  - Uses `unified.yaml` schema by default (backward compatible with JSON schemas)
- **migration.py**: Legacy format migration utilities
  - Converts legacy three-file format to unified YAML format
  - Supports detection and automatic migration of legacy configurations
- **data_utils.py**: Utility functions for data validation (JSON checking)

### Template System
- Main template: `prometheus_alert_rules_to_zbx_template.j2` - Complex Jinja2 template that converts Prometheus recording rules and alerting rules into Zabbix template JSON format
- Template processes both recording_rules (Prometheus queries) and alerting_rules (Zabbix triggers)
- Handles label mapping, macro substitution, and Zabbix-specific formatting

## Development Commands

### Testing
```bash
# Run all tests
python3 -m pytest tests/ -v

# Run tests with coverage
python3 -m pytest tests/ -v --cov=src/promabbix --cov-report=term-missing

# Run using the test runner script (recommended)
python3 run_tests.py

# Run specific test file
python3 -m pytest tests/test_template_basic.py -v
```

### Docker Build and Usage
```bash
# Build Docker image
docker buildx build -t promabbix:local .

# Run with help
docker run promabbix:local

# Process file with mounted directory
docker run --mount type=bind,src=$(pwd)/examples/,dst=/mnt promabbix:local /mnt/minikube-alert-config.yaml -o /mnt/output.json

# Use STDIN/STDOUT for pipeline processing
cat examples/minikube-alert-config.yaml | docker run -i promabbix:local - -o -
```

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run locally
python3 src/promabbix/promabbix.py examples/minikube-alert-config.yaml -o output.json
```

### Code Quality (CI Commands)
```bash
# Run complete CI quality check locally
source .venv/bin/activate

# Run tests with coverage (80% minimum required)
python -m pytest tests/ -v --cov-fail-under=80 --cov=src/promabbix --cov-report=term-missing --cov-report=xml

# Run flake8 linting
flake8 src/ --count --max-complexity=10 --max-line-length=127 --statistics

# Run type checking with mypy
mypy src/ --ignore-missing-imports
```

## Testing Architecture

The test suite uses pytest with comprehensive mocking strategy and achieves high coverage:

### Test Structure
- **200 tests total** with 86% code coverage (exceeds 80% requirement)
- **test_template_basic.py**: Tests utility functions without external dependencies  
- **test_template.py**: Full template functionality tests with mocked Ansible dependencies
- **test_validation.py**: Comprehensive configuration validation tests
- **test_schema_examples.py**: Schema validation tests with comprehensive examples and edge cases
- **test_fs_utils.py**: File system operations and data format handling
- **test_promabbix_app.py**: Main application and CLI integration tests
- **test_cli_validation_integration.py**: End-to-end CLI validation workflow
- **test_unified_format_file_processing.py**: Unified format processing and backwards compatibility
- **test_validation_wiki_optional.py**: Wiki section validation (optional sections)
- **test_config_without_wiki.py**: Configuration validation without wiki documentation
- **conftest.py**: Shared fixtures and configuration

### Test Categories
- **Core Functionality**: App initialization, argument parsing, main execution flow
- **File Operations**: Loading/saving YAML/JSON, STDIN/STDOUT handling  
- **Validation**: Schema validation, cross-reference validation, error handling
- **Schema Testing**: Comprehensive schema validation with valid/invalid configurations
- **Integration**: CLI integration, template processing, exception handling
- **Format Compatibility**: Unified format processing, legacy format migration
- **Edge Cases**: Empty data, malformed input, missing files, complex real-world configs
- **Optional Features**: Wiki documentation validation, backwards compatibility

### Mocking Strategy
- Mocks Ansible filter/test plugins to avoid requiring full Ansible installation
- Uses dependency injection for testing with mock DataLoader/DataSaver instances
- Comprehensive mocking of file system operations and template rendering
- Tests both happy paths and error conditions extensively

### Test Quality Standards
- All tests have clear, descriptive names that match their functionality
- Comprehensive docstrings explaining test purpose and expected behavior
- Realistic test data based on production use cases
- No duplicate functionality across tests
- Proper test isolation and cleanup

## Schema and Configuration Format

### Schema Definition
- **Primary Schema**: `src/promabbix/schemas/unified.yaml` - YAML format for better readability and maintainability
- **Backward Compatibility**: Code supports both YAML and JSON schema formats automatically
- **Validation**: Uses JSON Schema for comprehensive configuration validation
- **Error Reporting**: Enhanced error messages with suggestions and path information

### Input Format (YAML)
- **Unified Configuration**: Single YAML file containing all sections (groups, zabbix, prometheus, wiki)
- **Groups Section**: Contains `recording_rules` (Prometheus queries) and `alerting_rules` (Zabbix triggers)
- **Zabbix Section**: Template configuration, hosts, macros, tags, LLD filters
- **Prometheus Section**: API configuration, label mappings, query encoding rules  
- **Wiki Section**: Optional documentation for alerts and templates
- **Legacy Support**: Automatic migration from three-file format to unified format

### Output Format (JSON)
- Complete Zabbix template export format (version 6.0+)
- Includes discovery rules, item prototypes, trigger prototypes
- Auto-generates UUIDs and handles macro substitution

## Key Design Patterns

1. **Dependency Injection**: Main app accepts loader/saver/parser instances for testability
2. **Template-Driven**: Core logic in Jinja2 template with extensive custom filters
3. **Pipeline-Friendly**: Supports STDIN/STDOUT for integration with other tools
4. **Configuration Separation**: Template logic separated from Python application logic
5. **Error Handling**: Rich console output for user-friendly error reporting
6. **Format Agnostic**: Automatic detection and handling of YAML/JSON formats
7. **Schema-Driven Validation**: Comprehensive validation with detailed error reporting
8. **Backwards Compatibility**: Seamless migration from legacy formats

## Code Quality Standards

This project maintains strict code quality standards enforced by CI/CD:

### Type Safety (MyPy)
- **Complete type coverage**: All functions have proper type annotations
- **Return type annotations**: Every function specifies its return type
- **Parameter typing**: All function parameters are properly typed
- **Import safety**: Handles optional dependencies (CLoader) with proper type guards
- **Generic types**: Uses `Dict[str, Any]`, `List[ValidationError]`, etc. appropriately
- **Type casting**: Uses `cast()` for YAML/JSON loading where types are known

### Code Style (Flake8)
- **Line length**: Maximum 127 characters per line
- **Complexity**: Functions must stay under complexity threshold (≤10)
- **Import organization**: All imports at top of file, no unused imports
- **Whitespace**: No trailing whitespace or unnecessary blank lines
- **Naming**: Consistent naming conventions across modules

### Code Quality Metrics
- ✅ **Flake8**: 0 errors
- ✅ **MyPy**: 0 errors
- ✅ **Tests**: All passed
- ✅ **Coverage**: above 80% requirement

### Refactoring Patterns Applied
- **Complexity Reduction**: Split complex functions (DataSaver.save_to_file, migrate_legacy_service) into focused helper methods
- **Type Safety**: Added comprehensive type hints throughout codebase
- **Import Cleanup**: Removed unused imports and variables, organized import statements
- **Error Handling**: Proper exception types instead of generic sys.exit() calls

### Development Workflow
1. **Code Changes**: Make functionality changes first
2. **Run Tests**: Ensure all tests pass (`pytest tests/ -v`)
3. **Check Coverage**: Verify coverage stays above 80% (`pytest --cov-fail-under=80`)
4. **Lint Code**: Fix any style issues (`flake8 src/`)
5. **Type Check**: Ensure type safety (`mypy src/ --ignore-missing-imports`)
6. **Integration**: All quality checks must pass before deployment

### Configuration Files
- **pytest.ini**: Test configuration and coverage settings
- **requirements-dev.txt**: Development dependencies including linting tools
- **.github/workflows/ci.yml**: CI pipeline with quality gates
- **CLAUDE.local.md**: Local development setup instructions
- **unified.yaml**: Primary schema definition (migrated from unified.json)

## Recent Improvements & Changes

### Schema Migration (2025)
- **YAML Schema**: Migrated from `unified.json` to `unified.yaml` for better readability
- **Enhanced Validation**: Improved error reporting with path information and suggestions
- **Format Flexibility**: Code now supports both YAML and JSON schema formats automatically
- **Backwards Compatibility**: Existing functionality preserved during migration

### Validation Enhancements
- **Cross-Reference Validation**: Validates consistency between alerts and wiki documentation
- **Optional Wiki Sections**: Wiki documentation is optional but validated when present
- **Enhanced Error Messages**: Detailed validation errors with actionable suggestions
- **Schema Validation**: Comprehensive JSON Schema validation with custom error handling

### Testing Improvements
- **200 Tests**: Comprehensive test suite covering all functionality
- **High Coverage**: 86% code coverage exceeding 80% requirement
- **Schema Testing**: Dedicated tests for schema validation with edge cases
- **Integration Testing**: End-to-end CLI validation and template generation tests