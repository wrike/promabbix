# PRD: Promabbix Zabbix API Integration Enhancement

## Executive Summary

This PRD outlines the enhancement of Promabbix to include direct Zabbix API integration capabilities, enabling automated template deployment and pseudo-host management. The current system only generates Zabbix templates from alert configurations; this enhancement will add template synchronization and host management capabilities directly to Promabbix.

## Current State Analysis

### Existing Architecture
```
alert-config repos → OAPW → promabbix → Zabbix JSON Template (file output)
                                    ↓
                           Zabbix Ansible Playbooks → Zabbix API
```

### Current Workflow (Jenkins Integration)
1. **Template Generation**: `promabbix` generates JSON template files
2. **Template Upload**: Ansible playbook (`zbx_template.yml`) uploads templates via Zabbix API
3. **Host Management**: Ansible playbook (`zbx_host.yml`) manages pseudo-hosts via Zabbix API

### Current Promabbix CLI
```bash
# Current single command approach
promabbix alert-config.yaml --output template.json
promabbix alert-config.yaml --validate-only
```

### Current Limitations
- **No Direct API Integration**: Requires separate Ansible playbooks for Zabbix operations
- **Manual Template Upload**: Two-step process (generate → upload)
- **Fragmented Host Management**: Host operations handled separately from template generation
- **Complex Jenkins Pipeline**: Multiple tools and steps required for complete deployment

## Proposed Solution

### New CLI Command Structure
```bash
# Current functionality (enhanced)
promabbix generateTemplate alert-config.yaml --output template.json

# New capabilities
promabbix syncTemplate alert-config.yaml [--skip-validation]
promabbix syncPseudoHosts alert-config.yaml [--skip-sync-template]
```

### Target Architecture
```
alert-config repos → promabbix (unified tool) → Zabbix API
                        ↓
                   generateTemplate / syncTemplate / syncPseudoHosts
```

## Functional Requirements

### FR-1: Enhanced Template Generation Command
**New Command**: `promabbix generateTemplate`

**Purpose**: Move current functionality to explicit subcommand

**Implementation**:
- Current `promabbix` behavior becomes `promabbix generateTemplate`
- Maintains backward compatibility with existing flags
- All existing validation and template generation logic preserved

**CLI Signature**:
```bash
promabbix generateTemplate <config-file> [OPTIONS]
  --output, -o          Output file path (default: stdout)
  --templates, -t       Template directory path
  --template-name, -tn  Template file name
  --validate-only       Skip generation, only validate
```

### FR-2: Template Synchronization Command
**New Command**: `promabbix syncTemplate`

**Purpose**: Generate and upload Zabbix template directly to Zabbix API

**Key Features**:
- **Template Generation**: Internal template generation (no file output)
- **API Integration**: Upload to Zabbix using community.zabbix Ansible modules
- **Update Logic**: Create new or update existing templates
- **Macro Sync**: Upload template-level macros from `zabbix.macros` section
- **Validation**: Optional config validation (enabled by default)

**CLI Signature**:
```bash
promabbix syncTemplate <config-file> [OPTIONS]
  --zabbix-url          Zabbix server URL (default: from config/env)
  --zabbix-user         Zabbix username (default: from config/env)
  --zabbix-password     Zabbix password (default: from config/env)
  --skip-validation     Skip configuration validation
  --debug              Enable detailed logging
```

**Configuration Sources** (priority order):
1. Command line arguments
2. Environment variables (`ZABBIX_URL`, `ZABBIX_USER`, `ZABBIX_PASSWORD`)
3. Configuration file (`~/.zbx_auth.yml`)

### FR-3: Pseudo-Host Management Command
**New Command**: `promabbix syncPseudoHosts`

**Purpose**: Create/update Zabbix hosts from `zabbix.hosts` configuration

**Key Features**:
- **Host Creation/Update**: Manage hosts defined in `zabbix.hosts` section
- **Template Linking**: Link hosts to generated templates
- **Macro Management**: Apply host-level macro overrides
- **Template Sync**: Template synchronization enabled by default
- **Bulk Operations**: Process multiple hosts from single configuration

**CLI Signature**:
```bash
promabbix syncPseudoHosts <config-file> [OPTIONS]
  --zabbix-url          Zabbix server URL
  --zabbix-user         Zabbix username  
  --zabbix-password     Zabbix password
  --skip-sync-template  Skip template synchronization (default: false)
  --debug              Enable detailed logging
```

**Host Configuration Processing**:
```yaml
zabbix:
  hosts:
    - host_name: minikube
      visible_name: minikube
      host_groups: [Kubernetes]
      link_templates: [templ_module_promt_kube_minikube]
      macros:
        - macro: "{$CPU.UTIL.NODE.MAX}"
          value: "60"
```


## Technical Implementation

### Implementation Steps

This enhancement follows a test-driven development approach with paired implementation steps:

#### Step 1a: generateTemplate - Failing Tests and Skeleton ✅ COMPLETED
**Objective**: Implement failing tests and skeleton methods for generateTemplate command

**Tasks**:
- ✅ Create comprehensive failing tests for generateTemplate functionality
- ✅ Implement skeleton CLI command structure with proper Click decorators
- ✅ Create skeleton methods that fail appropriately
- ✅ Ensure test structure validates all expected behavior
- ✅ Verify command registration in main CLI

**Deliverables**:
- ✅ Check existing tests, update them to the new behaviour. If needed, add new tests for generateTemplate. All changed tests MUST initially fail.
- ✅ Skeleton classes and methods with empty implementations (including changes to existing project structure).
- ✅ Test coverage for validation, template generation, error handling
- ✅ CLI integration tests

**Stop Criteria**: ✅ All generateTemplate tests exist and fail appropriately

**Completed Work**:
- ✅ Migrated from argparse to Click CLI framework with `promabbix.promabbix:cli` as main entry point
- ✅ Implemented `GenerateTemplateCommand` class with skeleton methods in `src/promabbix/cli/generate_template.py`
- ✅ Created comprehensive test suite in `tests/test_cli_generate_template.py` with 26+ tests covering:
  - CLI command registration and help output
  - Template generation with various options (output file, stdout, custom templates)
  - Validation modes (validate-only, success/failure scenarios)
  - Backward compatibility with existing functionality
  - Integration tests with core modules
- ✅ Refactored existing `tests/test_promabbix_app.py` to use `GenerateTemplateCommand` instead of obsolete `PromabbixApp`
- ✅ Removed obsolete `PromabbixApp` functionality and consolidated logic into `GenerateTemplateCommand`
- ✅ Updated dependencies and resolved `rpds-py`/`jsonschema` compatibility issues
- ✅ Synchronized dependencies between `requirements.txt` and `pyproject.toml`

**Current Status**: READY FOR STEP 1B - All generateTemplate tests are in place and working with the skeleton implementation

#### Step 1b: generateTemplate - Full Implementation  
**Objective**: Implement full logic for generateTemplate command and verify quality

**Tasks**:
- Implement complete generateTemplate functionality
- Ensure all validation logic works correctly
- Implement template generation with proper error handling
- Add comprehensive logging and user feedback
- Verify all tests pass

**Quality Gates**:
- All generateTemplate tests pass
- Code quality checks pass (flake8, mypy)
- Manual CLI testing successful
- Integration with existing core modules verified

**Stop Criteria**: generateTemplate is fully functional with all tests passing

#### Step 2a: syncTemplate - Failing Tests and Skeleton
**Objective**: Implement failing tests and skeleton methods for syncTemplate command

**Tasks**:
- Create comprehensive failing tests for syncTemplate functionality
- Implement skeleton CLI command with authentication options
- Create skeleton Zabbix integration modules
- Create skeleton Ansible client wrapper
- Ensure test structure validates API integration behavior

**Deliverables**:
- All tests for syncTemplate created and initially failing
- Skeleton `src/promabbix/cli/sync_template.py` with empty implementations
- Skeleton `src/promabbix/zabbix/ansible_client.py` and `template_sync.py`
- Authentication configuration skeleton `src/promabbix/cli/auth.py`

**Stop Criteria**: All syncTemplate tests exist and fail appropriately

#### Step 2b: syncTemplate - Full Implementation
**Objective**: Implement full logic for syncTemplate command and verify quality

**Tasks**:
- Implement complete Ansible Zabbix integration
- Implement authentication configuration loading
- Implement template upload functionality
- Add error handling for Zabbix API operations
- Implement template-level macro synchronization

**Quality Gates**:
- All syncTemplate tests pass
- Code quality checks pass (flake8, mypy)
- Manual CLI testing with mock Zabbix successful
- Integration with authentication modules verified

**Stop Criteria**: syncTemplate is fully functional with all tests passing

#### Step 3a: syncPseudoHosts - Failing Tests and Skeleton
**Objective**: Implement failing tests and skeleton methods for syncPseudoHosts command

**Tasks**:
- Create comprehensive failing tests for syncPseudoHosts functionality
- Implement skeleton CLI command with all required options
- Create skeleton host management modules
- Create skeleton combined operations logic
- Ensure test structure validates host operations and template integration

**Deliverables**:
- All tests for syncPseudoHosts created and initially failing
- Skeleton `src/promabbix/cli/sync_pseudo_hosts.py` with empty implementations
- Skeleton `src/promabbix/zabbix/host_sync.py`
- Tests for combined template + host operations

**Stop Criteria**: All syncPseudoHosts tests exist and fail appropriately

#### Step 3b: syncPseudoHosts - Full Implementation
**Objective**: Implement full logic for syncPseudoHosts command and verify quality

**Tasks**:
- Implement complete host management functionality
- Implement combined template + host synchronization logic
- Implement host-level macro management
- Add proper operation sequencing and error handling
- Implement `--skip-sync-template` flag functionality

**Quality Gates**:
- All syncPseudoHosts tests pass
- Code quality checks pass (flake8, mypy)
- Manual CLI testing with end-to-end workflows successful
- Integration between template and host operations verified

**Stop Criteria**: syncPseudoHosts is fully functional with all tests passing

#### Final Step: Integration and Documentation
**Objective**: Complete integration testing and documentation

**Tasks**:
- End-to-end integration testing across all commands
- Performance testing and optimization
- Update documentation and examples
- Verify Jenkins pipeline integration
- Create migration guide for existing workflows

**Quality Gates**:
- Full test suite passes (>90% coverage)
- All code quality checks pass
- Integration testing successful
- Documentation complete and accurate

**Stop Criteria**: Complete system ready for production deployment

### Ansible Integration Architecture

#### Ansible Module Execution in Python

**Approach**: Use `ansible-runner` library to execute Ansible modules programmatically

**Key Components**:
```python
import ansible_runner
from typing import Dict, Any, Optional

class AnsibleZabbixClient:
    def __init__(self, zabbix_url: str, username: str, password: str):
        self.connection_params = {
            'ansible_httpapi_host': zabbix_url,
            'ansible_user': username,
            'ansible_httpapi_pass': password,
            'ansible_connection': 'httpapi',
            'ansible_httpapi_port': 443,
            'ansible_httpapi_use_ssl': True
        }
    
    def run_module(self, module_name: str, module_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Ansible module and return results"""
        playbook_data = [{
            'hosts': 'localhost',
            'gather_facts': False,
            'tasks': [{
                'name': f'Execute {module_name}',
                module_name: module_args
            }]
        }]
        
        result = ansible_runner.run(
            playbook=playbook_data,
            inventory={'localhost': self.connection_params},
            quiet=True
        )
        return result
```

#### Template Upload Implementation

**Using community.zabbix.zabbix_template**:
```python
def upload_template(self, template_json: str) -> bool:
    """Upload Zabbix template using Ansible module"""
    module_args = {
        'template_json': template_json,
        'state': 'present'
    }
    
    result = self.run_module('community.zabbix.zabbix_template', module_args)
    return result.status == 'successful'
```

#### Host Management Implementation

**Using community.zabbix.zabbix_host**:
```python
def create_or_update_host(self, host_config: Dict[str, Any]) -> bool:
    """Create or update Zabbix host using Ansible module"""
    module_args = {
        'host_name': host_config['host_name'],
        'visible_name': host_config.get('visible_name', ''),
        'host_groups': host_config.get('host_groups', []),
        'link_templates': host_config.get('link_templates', []),
        'macros': host_config.get('macros', []),
        'interfaces': host_config.get('interfaces', []),
        'state': 'present'
    }
    
    result = self.run_module('community.zabbix.zabbix_host', module_args)
    return result.status == 'successful'
```

#### Dependencies and Requirements

**New Dependencies**:
- `ansible-runner>=2.3.0` - For programmatic Ansible execution
- `community.zabbix` Ansible collection - Zabbix modules

**Installation Requirements**:
```bash
# Install Python dependency
pip install ansible-runner>=2.3.0

# Install Ansible collection
ansible-galaxy collection install community.zabbix
```

**Benefits of Ansible Approach**:
1. **Leverage Existing Infrastructure**: Reuses current Ansible playbook logic
2. **Proven Reliability**: Same modules used in production Jenkins pipelines
3. **Comprehensive Features**: Full Zabbix API coverage via Ansible modules
4. **Idempotency**: Built-in create/update logic without custom implementation
5. **Error Handling**: Mature Ansible error reporting and debugging
6. **Authentication**: Multiple auth methods already supported
7. **Maintenance**: Community-maintained modules with regular updates

### Error Handling Strategy

**Ansible Module Execution Errors**:
- Parse Ansible runner results for task failures
- Extract meaningful error messages from Ansible output
- Handle authentication failures and connectivity issues

**Template Upload Errors**:
- Validation of template JSON before Ansible module execution
- Parse `community.zabbix.zabbix_template` module error responses
- Continue operation where possible (individual host failures don't stop batch)

**Host Management Errors**:
- Individual host failure isolation using Ansible task-level error handling
- Dependency validation (template must exist before host linking)
- Parse `community.zabbix.zabbix_host` module responses for specific errors

### Logging Strategy

**Default Behavior**:
- Minimal output showing only success/failure status
- Brief error messages for failed Ansible module operations
- Progress indication for multi-host operations

**Debug Mode (--debug flag)**:
- Full Ansible runner output and task results
- Detailed Ansible module execution logs
- Operation timing information
- Configuration parsing details

## Integration with Existing Systems

### OAPW Workflow Updates

**Current OAPW Workflow** (`workflows/zabbix/prometheus_alert_rules_to_zbx_template.yml`):
```yaml
workflow:
  - step: 1
    module: shell
    parameters:
      command: |
        # Current: Generate template file
        promabbix - --output {{ tmp_dir }}/{{ service }}/{{ service }}.json
```

**Enhanced OAPW Workflow**:
```yaml
workflow:
  - step: 1
    module: shell
    parameters:
      command: |
        # New: Direct template and host sync in single command
        promabbix syncPseudoHosts - --zabbix-url https://zabbix.wrke.in \
                                   --zabbix-user "${ZBX_USERNAME}" \
                                   --zabbix-password "${ZBX_PASSWORD}"
      environment:
        ZBX_USERNAME: "{{ zbx_username }}"
        ZBX_PASSWORD: "{{ zbx_password }}"
```

### Jenkins Pipeline Integration

**Current Jenkins Workflow** (`alert-config/Jenkinsfile:64-84`):
```groovy
// Current: Multi-step process
sh "promabbix - --output ${TMP_DIR}/${SERVICE}/${SERVICE}.json"
push_to_zabbix("${ANSIBLE_PLAYBOOK_TEMPLATE}", template_vars)
push_to_zabbix("${ANSIBLE_PLAYBOOK_HOST}", host_vars)
```

**Enhanced Jenkins Workflow**:
```groovy
// New: Single-step process
sh """
promabbix syncPseudoHosts - \
  --zabbix-url https://zabbix.wrke.in \
  --zabbix-user "\${zbx_username}" \
  --zabbix-password "\${zbx_password}"
"""
```

### Backward Compatibility Plan

No further backward compatibility required.

## Security Considerations

### Authentication Security
- **Credential Sources**: CLI, environment variables, config files
- **Password Masking**: Ensure passwords not logged in CLI output

## Conclusion

This enhancement transforms Promabbix from a template generator into a complete Zabbix integration tool, eliminating the need for separate Ansible playbooks and simplifying the deployment pipeline. The new CLI structure provides clear separation of concerns while maintaining backward compatibility for existing workflows.

The implementation prioritizes reliability, security, and operational simplicity while providing a migration path for existing integrations. Success will be measured by reduced deployment complexity, improved reliability, and faster alert configuration deployment across Wrike's infrastructure.
