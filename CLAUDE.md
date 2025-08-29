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
  - `DataSaver`: Handles output to files or STDOUT with format-aware serialization
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

## Testing Architecture

The test suite uses pytest with comprehensive mocking strategy:
- **test_template_basic.py**: Tests utility functions without external dependencies
- **test_template.py**: Full template functionality tests with mocked Ansible dependencies
- **conftest.py**: Shared fixtures and configuration
- Mocks Ansible filter/test plugins to avoid requiring full Ansible installation

## Input/Output Format

### Input (YAML)
- `groups` with `recording_rules` (Prometheus queries) and `alerting_rules` (Zabbix triggers)
- Uses Prometheus alert rule format but separated into recording vs alerting

### Output (JSON)
- Complete Zabbix template export format (version 6.0+)
- Includes discovery rules, item prototypes, trigger prototypes
- Auto-generates UUIDs and handles macro substitution

## Key Design Patterns

1. **Dependency Injection**: Main app accepts loader/saver/parser instances for testability
2. **Template-Driven**: Core logic in Jinja2 template with extensive custom filters
3. **Pipeline-Friendly**: Supports STDIN/STDOUT for integration with other tools
4. **Configuration Separation**: Template logic separated from Python application logic
5. **Error Handling**: Rich console output for user-friendly error reporting