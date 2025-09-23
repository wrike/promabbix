#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import pytest
import json
import yaml
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.validation import ConfigValidator, ValidationError


class TestConfigValidator:
    """Test the unified YAML configuration validator."""

    def test_validator_initialization(self):
        """Test validator can be initialized with default schema."""
        # Should successfully initialize with built-in schema
        validator = ConfigValidator()
        assert validator.schema is not None
        assert isinstance(validator.schema, dict)

    def test_validator_with_custom_schema(self, temp_directory):
        """Test validator can be initialized with custom schema."""
        schema_file = temp_directory / "test_schema.json"
        schema = {
            "type": "object",
            "properties": {
                "groups": {"type": "array"}
            }
        }
        schema_file.write_text(json.dumps(schema))
        
        # Should work with custom schema file
        validator = ConfigValidator(str(schema_file))
        assert validator.schema == schema


class TestUnifiedFormatValidation:
    """Test validation of the unified YAML format."""

    @pytest.fixture
    def valid_config(self):
        """Valid alert-config style configuration."""
        return {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "db_role_master",
                            "expr": "sum(pg_db_role_master{project=\"postgres\"})by(project,cluster)>=0"
                        },
                        {
                            "record": "patroni_role_master", 
                            "expr": "sum(pg_patroni{role=\"master\",project=\"postgres\"})by(project,cluster)>=0"
                        }
                    ]
                },
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "db_role_master",
                            "expr": "db_role_master == 0",
                            "annotations": {
                                "description": "PostgreSQL master unavailable",
                                "summary": "No PostgreSQL master found in {{$labels.cluster}}"
                            }
                        }
                    ]
                }
            ],
            "prometheus": {
                "api": {
                    "url": "http://victoria-metrics.monitoring.svc:8481/api/v1/query"
                },
                "labels_to_zabbix_macros": [
                    {
                        "pattern": r'\{\{(?:\s*)\$value(?:\s*)\}\}',
                        "value": "{ITEM.VALUE1}"
                    }
                ]
            },
            "zabbix": {
                "template": "service_postgres",
                "name": "Template Module Prometheus service postgres",
                "labels": {
                    "slack_alarm_channel_name": "{$SLACK.ALARM.CHANNEL.NAME}"
                },
                "lld_filters": {
                    "filter": {
                        "conditions": [
                            {
                                "formulaid": "A",
                                "macro": "{#PROJECT}",
                                "value": "{$POSTGRES.PROJECT.LLD.MATCHES}"
                            }
                        ],
                        "evaltype": "AND"
                    }
                },
                "hosts": [
                    {
                        "host_name": "postgres-prod",
                        "visible_name": "Service Postgres Prod",
                        "host_groups": ["Prometheus pseudo hosts"],
                        "link_templates": ["templ_module_promt_service_postgres"],
                        "status": "enabled",
                        "state": "present",
                        "proxy": "gce-infra-zbx-pr02"
                    }
                ]
            },
            "wiki": {
                "templates": {
                    "wrike_alert_config": {
                        "templates": [
                            {
                                "name": "postgres",
                                "title": "Alert postgres configuration"
                            }
                        ]
                    }
                },
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "db_role_master": {
                                "title": "PostgreSQL Master Role Alert",
                                "content": "This alert triggers when no PostgreSQL master is detected..."
                            }
                        }
                    }
                }
            }
        }

    @pytest.fixture
    def valid_second_config(self):
        """Valid alert-config style configuration."""
        return {
            "groups": [
                {
                    "name": "recording_rules", 
                    "rules": [
                        {
                            "record": "app_server_http_requests:rate5m",
                            "expr": "sum(rate(http_requests_total{service=\"app-server\"}[5m]))by(k8s_cluster,namespace,pod)"
                        }
                    ]
                },
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "app_server_http_requests:rate5m",
                            "expr": "app_server_http_requests:rate5m >= {$HTTP.REQUESTS.RATE.MAX}",
                            "annotations": {
                                "description": "High HTTP request rate: {{$value}} req/s",
                                "summary": "{{$labels.service}} high request rate in {{$labels.namespace}}"
                            },
                            "labels": {
                                "__zbx_priority": "WARNING"
                            }
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "app_server", 
                "name": "Template Module Prometheus app-server",
                "hosts": [
                    {
                        "host_name": "sjc-k8s-cluster-backend-services",
                        "visible_name": "SJC K8s Backend Services",
                        "host_groups": ["Kubernetes clusters", "Backend services"],
                        "link_templates": ["templ_module_promt_app_server"],
                        "status": "enabled",
                        "state": "present",
                        "proxy": "gce-infra-zbx-pr02",
                        "macros": [
                            {
                                "macro": "{$HTTP.REQUESTS.RATE.MAX}",
                                "value": 1000,
                                "description": "Maximum HTTP requests per second threshold"
                            }
                        ]
                    }
                ]
            },
            "wiki": {
                "templates": {
                    "wrike_alert_config": {
                        "templates": [
                            {
                                "name": "app-server",
                                "title": "app-server alert configuration"
                            }
                        ]
                    }
                },
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "app_server_http_requests:rate5m": {
                                "title": "High HTTP Request Rate",
                                "content": "This alert indicates unusually high HTTP request rate..."
                            }
                        }
                    }
                }
            }
        }

    def test_valid_config_validation(self, valid_config):
        """Test validation of valid configuration."""
        # Should pass validation without raising any errors
        validator = ConfigValidator()
        validator.validate_config(valid_config)  # Should not raise any exception

    def test_valid_second_config_validation(self, valid_second_config):
        """Test validation of valid second configuration.""" 
        # Should pass validation without raising any errors
        validator = ConfigValidator()
        validator.validate_config(valid_second_config)  # Should not raise any exception

    def test_missing_required_groups_section(self):
        """Test validation fails when groups section is missing."""
        invalid_config = {
            "zabbix": {
                "template": "test_template"
            }
        }
        
        # Should raise ValidationError for missing required groups section
        validator = ConfigValidator()
        with pytest.raises(ValidationError) as excinfo:
            validator.validate_config(invalid_config)
        assert "required" in str(excinfo.value).lower()
        assert "groups" in str(excinfo.value)

    def test_missing_required_zabbix_section(self):
        """Test validation fails when zabbix section is missing."""
        invalid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": []
                }
            ]
        }
        
        # Should raise ValidationError for missing required zabbix section
        validator = ConfigValidator()
        with pytest.raises(ValidationError) as excinfo:
            validator.validate_config(invalid_config)
        assert "required" in str(excinfo.value).lower()
        assert "zabbix" in str(excinfo.value)

    def test_invalid_group_name(self):
        """Test validation fails for invalid group names."""
        invalid_config = {
            "groups": [
                {
                    "name": "invalid_group_name",  # Should only be recording_rules or alerting_rules
                    "rules": []
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        
        # Should raise ValidationError for invalid group name
        validator = ConfigValidator()
        with pytest.raises(ValidationError) as excinfo:
            validator.validate_config(invalid_config)
        # Should mention the invalid group name or enum violation
        error_msg = str(excinfo.value).lower()
        assert ("enum" in error_msg or "invalid_group_name" in error_msg or 
                "recording_rules" in error_msg or "alerting_rules" in error_msg)

    def test_missing_record_field_in_recording_rule(self):
        """Test validation fails when recording rule missing record field."""
        invalid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "expr": "sum(metric) by (label)",
                            # Missing "record" field
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        
        # Should raise ValidationError for missing record field
        validator = ConfigValidator()
        with pytest.raises(ValidationError) as excinfo:
            validator.validate_config(invalid_config)
        error_msg = str(excinfo.value).lower()
        assert ("required" in error_msg or "record" in error_msg)

    def test_missing_alert_field_in_alerting_rule(self):
        """Test validation fails when alerting rule missing alert field."""
        invalid_config = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "expr": "metric > threshold",
                            # Missing "alert" field
                            "annotations": {
                                "summary": "Test alert"
                            }
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        
        # Should raise ValidationError for missing alert field
        validator = ConfigValidator()
        with pytest.raises(ValidationError) as excinfo:
            validator.validate_config(invalid_config)
        error_msg = str(excinfo.value).lower()
        assert ("required" in error_msg or "alert" in error_msg)


class TestCrossSectionValidation:
    """Test cross-section validation between different parts of config."""

    def test_alert_wiki_consistency_valid(self):
        """Test that alerts with matching wiki documentation pass validation."""
        config = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "test_alert_1",
                            "expr": "metric > 1",
                            "annotations": {"summary": "Test"}
                        },
                        {
                            "alert": "test_alert_2", 
                            "expr": "metric > 2",
                            "annotations": {"summary": "Test 2"}
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "test_template"
            },
            "wiki": {
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "test_alert_1": {
                                "title": "Test Alert 1",
                                "content": "Documentation for test alert 1"
                            },
                            "test_alert_2": {
                                "title": "Test Alert 2", 
                                "content": "Documentation for test alert 2"
                            }
                        }
                    }
                }
            }
        }
        
        # Should pass validation without errors
        validator = ConfigValidator()
        validator.validate_config(config)  # Should not raise any exception

    def test_alert_wiki_consistency_missing_docs(self):
        """Test validation fails when alerts missing wiki documentation."""
        config = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "documented_alert",
                            "expr": "metric > 1",
                            "annotations": {"summary": "Test"}
                        },
                        {
                            "alert": "undocumented_alert",  # Missing from wiki
                            "expr": "metric > 2", 
                            "annotations": {"summary": "Test 2"}
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "test_template"
            },
            "wiki": {
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "documented_alert": {
                                "title": "Documented Alert",
                                "content": "This alert is documented"
                            }
                            # undocumented_alert is missing
                        }
                    }
                }
            }
        }
        
        # Should raise ValidationError for missing documentation
        validator = ConfigValidator()
        with pytest.raises(ValidationError) as excinfo:
            validator.validate_config(config)
        assert "undocumented_alert" in str(excinfo.value)
        assert "wiki documentation" in str(excinfo.value)

    def test_alert_wiki_consistency_extra_docs(self):
        """Test validation allows extra wiki docs (docs without matching alerts)."""
        config = {
            "groups": [
                {
                    "name": "alerting_rules", 
                    "rules": [
                        {
                            "alert": "active_alert",
                            "expr": "metric > 1",
                            "annotations": {"summary": "Test"}
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "test_template"
            },
            "wiki": {
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "active_alert": {
                                "title": "Active Alert",
                                "content": "Documentation for active alert"
                            },
                            "legacy_alert": {  # No matching alert rule - should be allowed
                                "title": "Legacy Alert",
                                "content": "Documentation for deprecated alert"
                            }
                        }
                    }
                }
            }
        }
        
        # Extra documentation should be allowed (for legacy/future alerts)
        validator = ConfigValidator()
        validator.validate_config(config)  # Should not raise exception

    def test_zabbix_host_template_reference_validation(self):
        """Test validation of zabbix host template references."""
        config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ],
            "zabbix": {
                "template": "test_service_template",
                "name": "Test Service Template",
                "hosts": [
                    {
                        "host_name": "test-host",
                        "visible_name": "Test Host",
                        "host_groups": ["Test Group"],
                        "link_templates": [
                            "templ_module_promt_test_service_template"  # Should match template
                        ],
                        "status": "enabled",
                        "state": "present"
                    }
                ]
            }
        }
        
        # Should pass validation (template reference validation not implemented in Phase 1)
        validator = ConfigValidator()
        validator.validate_config(config)  # Should not raise any exception


class TestSchemaValidation:
    """Test JSON schema validation of configuration structure."""

    def test_invalid_host_status(self):
        """Test validation fails for invalid host status values."""
        invalid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ],
            "zabbix": {
                "template": "test_template",
                "hosts": [
                    {
                        "host_name": "test-host",
                        "visible_name": "Test Host", 
                        "host_groups": ["Test Group"],
                        "link_templates": ["test_template"],
                        "status": "invalid_status",  # Should be "enabled" or "disabled"
                        "state": "present"
                    }
                ]
            }
        }
        
        # Should raise ValidationError for invalid enum value
        validator = ConfigValidator()
        with pytest.raises(ValidationError) as excinfo:
            validator.validate_config(invalid_config)
        error_msg = str(excinfo.value).lower()
        assert ("enum" in error_msg or "invalid_status" in error_msg or 
                "enabled" in error_msg or "disabled" in error_msg)

    def test_invalid_host_state(self):
        """Test validation fails for invalid host state values."""
        invalid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ],
            "zabbix": {
                "template": "test_template",
                "hosts": [
                    {
                        "host_name": "test-host",
                        "visible_name": "Test Host",
                        "host_groups": ["Test Group"], 
                        "link_templates": ["test_template"],
                        "status": "enabled",
                        "state": "invalid_state"  # Should be "present" or "absent"
                    }
                ]
            }
        }
        
        # Should raise ValidationError for invalid enum value
        validator = ConfigValidator()
        with pytest.raises(ValidationError) as excinfo:
            validator.validate_config(invalid_config)
        error_msg = str(excinfo.value).lower()
        assert ("enum" in error_msg or "invalid_state" in error_msg or 
                "present" in error_msg or "absent" in error_msg)

    def test_invalid_lld_filter_evaltype(self):
        """Test validation fails for invalid LLD filter evaltype."""
        invalid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ],
            "zabbix": {
                "template": "test_template",
                "lld_filters": {
                    "filter": {
                        "conditions": [
                            {
                                "formulaid": "A",
                                "macro": "{#TEST}",
                                "value": ".*"
                            }
                        ],
                        "evaltype": "INVALID"  # Should be "AND" or "OR"
                    }
                }
            }
        }
        
        # Should raise ValidationError for invalid enum value
        validator = ConfigValidator()
        with pytest.raises(ValidationError) as excinfo:
            validator.validate_config(invalid_config)
        error_msg = str(excinfo.value).lower()
        assert ("enum" in error_msg or "invalid" in error_msg or 
                "and" in error_msg or "or" in error_msg)

    def test_invalid_formulaid_pattern(self):
        """Test validation fails for invalid formulaid patterns."""
        invalid_config = {
            "groups": [
                {
                    "name": "recording_rules", 
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ],
            "zabbix": {
                "template": "test_template",
                "lld_filters": {
                    "filter": {
                        "conditions": [
                            {
                                "formulaid": "AA",  # Should be single letter A-Z
                                "macro": "{#TEST}",
                                "value": ".*"
                            }
                        ],
                        "evaltype": "AND"
                    }
                }
            }
        }
        
        # Should raise ValidationError for invalid pattern
        validator = ConfigValidator()
        with pytest.raises(ValidationError) as excinfo:
            validator.validate_config(invalid_config)
        error_msg = str(excinfo.value).lower()
        assert ("pattern" in error_msg or "formulaid" in error_msg)


class TestComplexRealWorldConfigurations:
    """Test validation with complex real-world configurations inspired by actual alert configs."""

    @pytest.fixture
    def complex_postgres_config(self):
        """Complex PostgreSQL configuration based on alert-config/service/postgres/."""
        return {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "db_role_master",
                            "expr": "sum(pg_db_role_master{project=\"postgres\"})by(project,cluster)>=0"
                        },
                        {
                            "record": "patroni_role_master",
                            "expr": "sum(pg_patroni{role=\"master\",project=\"postgres\"})by(project,cluster)>=0"
                        },
                        {
                            "record": "patroni_pg_role_master", 
                            "expr": "sum(sum(pg_patroni{role=\"master\",project=\"postgres\"})by(project,cluster)>=0 and sum(pg_db_role_master{project=\"postgres\"})by(project,cluster)>=0)by(project,cluster)"
                        },
                        {
                            "record": "db_percent_connections_ratio",
                            "expr": "max(pg_db_database_percent_connections_ratio{project=\"postgres\"})by(project,cluster,instance)>=0"
                        },
                        {
                            "record": "replication_lag_ratio",
                            "expr": "(max(avg_over_time(pg_db_replication_info_replay_bytes{state=\"streaming\",project=\"postgres\"}[5m]))by(project,cluster) > 104857600 - max(avg_over_time(pg_db_replication_info_replay_bytes{state=\"streaming\",project=\"postgres\"}[5m] > 104857600 offset 1h))by(project,cluster)) / max(avg_over_time(pg_db_replication_info_replay_bytes{state=\"streaming\",project=\"postgres\"}[5m] > 104857600 offset 1h))by(project,cluster) * 100"
                        }
                    ]
                },
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "db_role_master",
                            "expr": "db_role_master == 0",
                            "annotations": {
                                "description": "cluster: {{$labels.cluster}}, project: {{$labels.project}}",
                                "summary": "PostgreSQL master unavailable in cluster {{$labels.cluster}}"
                            },
                            "labels": {
                                "__zbx_priority": "DISASTER"
                            }
                        },
                        {
                            "alert": "patroni_role_master",
                            "expr": "patroni_role_master == 0", 
                            "annotations": {
                                "description": "cluster: {{$labels.cluster}}, project: {{$labels.project}}",
                                "summary": "Patroni master unavailable in cluster {{$labels.cluster}}"
                            },
                            "labels": {
                                "__zbx_priority": "HIGH"
                            }
                        },
                        {
                            "alert": "db_percent_connections_ratio",
                            "expr": "db_percent_connections_ratio >= {$POSTGRES.CONNECTIONS.PERCENT.MAX}",
                            "annotations": {
                                "description": "cluster: {{$labels.cluster}}, instance: {{$labels.instance}}, ratio: {{$value}}%",
                                "summary": "PostgreSQL connection usage above threshold in {{$labels.cluster}}"
                            }
                        }
                    ]
                }
            ],
            "prometheus": {
                "api": {
                    "url": "http://victoria-metrics.monitoring.svc:8481/api/v1/query"
                },
                "labels_to_zabbix_macros": [
                    {
                        "pattern": r'\{\{(?:\s*)\$value(?:\s*)\}\}',
                        "value": "{ITEM.VALUE1}"
                    },
                    {
                        "pattern": r'\{\{(?:\s*)\$labels\.(?P<label>[a-zA-Z0-9\_\-]*)(?:\s*)\}\}',
                        "value": "{#\\g<label>}"
                    }
                ],
                "query_chars_encoding": [
                    {"char": "+", "encode": "%2B"}
                ]
            },
            "promabbix": {
                "zabbix_depend_item_preprocessing": "$.metrics[\"{#ZBX.ITEM.SUBKEY}\"]",
                "zabbix_master_item_preprocessing": """var ingest_json = JSON.parse(value),
    metrics = ingest_json.data.result || [],
    result = { "lld": [], "metrics": {} };
return JSON.stringify(result);"""
            },
            "zabbix": {
                "template": "service_postgres",
                "name": "Template Module Prometheus service postgres",
                "labels": {
                    "slack_alarm_channel_name": "{$SLACK.ALARM.CHANNEL.NAME}"
                },
                "lld_filters": {
                    "filter": {
                        "conditions": [
                            {
                                "formulaid": "A",
                                "macro": "{#PROJECT}",
                                "value": "{$POSTGRES.PROJECT.LLD.MATCHES}"
                            },
                            {
                                "formulaid": "B", 
                                "macro": "{#CLUSTER}",
                                "value": "{$POSTGRES.CLUSTER.LLD.MATCHES}"
                            }
                        ],
                        "evaltype": "AND"
                    }
                },
                "macros": [
                    {
                        "macro": "{$POSTGRES.PROJECT.LLD.MATCHES}",
                        "description": "This macro is used in dbms discovery. Can be overridden on the host or linked template level.",
                        "value": ".*"
                    },
                    {
                        "macro": "{$POSTGRES.CLUSTER.LLD.MATCHES}",
                        "description": "This macro is used in dbms discovery. Can be overridden on the host or linked template level.", 
                        "value": ".*"
                    },
                    {
                        "macro": "{$POSTGRES.CONNECTIONS.PERCENT.MAX}",
                        "description": "Maximum PostgreSQL connections percentage threshold",
                        "value": 80
                    }
                ],
                "tags": [
                    {
                        "tag": "service_kind",
                        "value": "postgres"
                    }
                ],
                "hosts": [
                    {
                        "host_name": "postgres-prod",
                        "visible_name": "Service Postgres Prod",
                        "host_groups": ["Prometheus pseudo hosts"],
                        "link_templates": ["templ_module_promt_service_postgres"],
                        "status": "enabled",
                        "state": "present", 
                        "proxy": "gce-infra-zbx-pr02",
                        "macros": [
                            {
                                "macro": "{$SLACK.ALARM.CHANNEL.NAME}",
                                "value": "db-alerts"
                            },
                            {
                                "macro": "{$POSTGRES.PROJECT.LLD.MATCHES}",
                                "value": "^postgres$"
                            },
                            {
                                "macro": "{$POSTGRES.CLUSTER.LLD.MATCHES}",
                                "value": "(.*sjc.*|.*gce-.*-prod.*|.*prod.*)"
                            }
                        ]
                    },
                    {
                        "host_name": "postgres-qa",
                        "visible_name": "Service Postgres QA",
                        "host_groups": ["Prometheus pseudo hosts"],
                        "link_templates": ["templ_module_promt_service_postgres"],
                        "status": "enabled",
                        "state": "present",
                        "proxy": "gce-infra-zbx-pr02",
                        "macros": [
                            {
                                "macro": "{$SLACK.ALARM.CHANNEL.NAME}",
                                "value": "db-alerts"
                            },
                            {
                                "macro": "{$POSTGRES.PROJECT.LLD.MATCHES}",
                                "value": "^postgres$"
                            },
                            {
                                "macro": "{$POSTGRES.CLUSTER.LLD.MATCHES}",
                                "value": "(.*led.*|.*alpha.*|.*rct.*)"
                            }
                        ]
                    }
                ]
            },
            "wiki": {
                "templates": {
                    "wrike_alert_config": {
                        "templates": [
                            {
                                "name": "postgres",
                                "title": "Alert postgres configuration"
                            }
                        ]
                    }
                },
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "db_role_master": {
                                "title": "PostgreSQL Master Role Alert",
                                "content": "This alert triggers when no PostgreSQL master database is detected in a cluster. This is a critical condition that requires immediate attention as it means the database cluster cannot accept write operations."
                            },
                            "patroni_role_master": {
                                "title": "Patroni Master Role Alert", 
                                "content": "This alert triggers when Patroni cannot detect a master node. Patroni is the high-availability solution for PostgreSQL that manages automatic failover."
                            },
                            "db_percent_connections_ratio": {
                                "title": "PostgreSQL Connection Usage Alert",
                                "content": "This alert triggers when PostgreSQL connection usage exceeds the configured threshold. High connection usage can lead to connection exhaustion and service unavailability."
                            }
                        }
                    }
                }
            }
        }

    @pytest.fixture
    def complex_app_server_config(self):
        """Complex app-server configuration based on wrike-alert-config."""
        return {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "app_server_cpu_usage:rate5m",
                            "expr": "sum(rate(container_cpu_usage_seconds_total{namespace=~\".*\",pod=~\"app-server.*\"}[5m]))by(k8s_cluster,namespace,pod)"
                        },
                        {
                            "record": "app_server_http_requests:rate5m", 
                            "expr": "sum(rate(http_requests_total{service=\"app-server\"}[5m]))by(k8s_cluster,namespace,pod,status_code)"
                        },
                        {
                            "record": "app_server_jvm_memory:ratio",
                            "expr": "sum(jvm_memory_bytes_used{area=\"heap\",service=\"app-server\"})by(k8s_cluster,namespace,pod) / sum(jvm_memory_bytes_max{area=\"heap\",service=\"app-server\"})by(k8s_cluster,namespace,pod)"
                        }
                    ]
                },
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "app_server_cpu_usage:rate5m",
                            "expr": "app_server_cpu_usage:rate5m >= {$CPU.UTIL.APP.REGION.MAX}",
                            "annotations": {
                                "description": "pod: {{$labels.pod}}, namespace: {{$labels.namespace}}, cpu_usage: {{$value}}",
                                "summary": "High CPU usage for {{$labels.pod}} in {{$labels.namespace}}"
                            },
                            "labels": {
                                "__zbx_priority": "WARNING"
                            }
                        },
                        {
                            "alert": "app_server_http_requests:rate5m",
                            "expr": "app_server_http_requests:rate5m >= {$HTTP.REQUESTS.RATE.MAX}",
                            "annotations": {
                                "description": "pod: {{$labels.pod}}, namespace: {{$labels.namespace}}, request_rate: {{$value}} req/s",
                                "summary": "High HTTP request rate for {{$labels.pod}} in {{$labels.namespace}}"
                            }
                        },
                        {
                            "alert": "app_server_jvm_memory:ratio", 
                            "expr": "app_server_jvm_memory:ratio >= {$JVM.MEMORY.HEAP.RATIO.MAX}",
                            "annotations": {
                                "description": "pod: {{$labels.pod}}, namespace: {{$labels.namespace}}, heap_ratio: {{$value}}",
                                "summary": "High JVM heap usage for {{$labels.pod}} in {{$labels.namespace}}"
                            },
                            "labels": {
                                "__zbx_priority": "HIGH"
                            }
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "app_server",
                "name": "Template Module Prometheus app-server",
                "lld_filters": {
                    "filter": {
                        "conditions": [
                            {
                                "formulaid": "A",
                                "macro": "{#K8S_CLUSTER}",
                                "value": "{$K8S.CLUSTER.LLD.MATCHES}"
                            },
                            {
                                "formulaid": "B",
                                "macro": "{#NAMESPACE}",
                                "value": "{$NAMESPACE.LLD.MATCHES}"
                            }
                        ],
                        "evaltype": "AND"
                    }
                },
                "hosts": [
                    {
                        "host_name": "sjc-k8s-cluster-backend-services",
                        "visible_name": "SJC K8s Backend Services",
                        "host_groups": ["Kubernetes clusters", "Backend services"],
                        "link_templates": ["templ_module_promt_app_server"],
                        "status": "enabled",
                        "state": "present",
                        "proxy": "gce-infra-zbx-pr02",
                        "macros": [
                            {
                                "macro": "{$K8S.CLUSTER.LLD.MATCHES}",
                                "value": "sjc-k8s-.*"
                            },
                            {
                                "macro": "{$NAMESPACE.LLD.MATCHES}",
                                "value": "(.*-sjc-.*|.*-prod-.*)"
                            },
                            {
                                "macro": "{$CPU.UTIL.APP.REGION.MAX}",
                                "value": 0.8
                            },
                            {
                                "macro": "{$HTTP.REQUESTS.RATE.MAX}",
                                "value": 1000
                            },
                            {
                                "macro": "{$JVM.MEMORY.HEAP.RATIO.MAX}",
                                "value": 0.85
                            }
                        ]
                    }
                ]
            },
            "wiki": {
                "templates": {
                    "wrike_alert_config": {
                        "templates": [
                            {
                                "name": "app-server",
                                "title": "app-server alert configuration"
                            }
                        ]
                    }
                },
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "app_server_cpu_usage:rate5m": {
                                "title": "High CPU Usage Alert",
                                "content": "This alert indicates that the app-server is experiencing high CPU usage, which may impact response times and overall performance."
                            },
                            "app_server_http_requests:rate5m": {
                                "title": "High HTTP Request Rate Alert",
                                "content": "This alert triggers when the HTTP request rate exceeds normal thresholds, potentially indicating increased load or traffic spikes."
                            },
                            "app_server_jvm_memory:ratio": {
                                "title": "High JVM Heap Usage Alert",
                                "content": "This alert indicates high JVM heap memory usage which could lead to garbage collection pressure and potential OutOfMemoryError conditions."
                            }
                        }
                    }
                }
            }
        }

    def test_complex_postgres_config_validation(self, complex_postgres_config):
        """Test validation of complex PostgreSQL configuration."""
        # Should pass validation for well-formed complex configuration
        validator = ConfigValidator()
        validator.validate_config(complex_postgres_config)  # Should not raise any exception

    def test_complex_app_server_config_validation(self, complex_app_server_config):
        """Test validation of complex app-server configuration."""
        # Should pass validation for well-formed complex configuration
        validator = ConfigValidator()
        validator.validate_config(complex_app_server_config)  # Should not raise any exception

    def test_malformed_prometheus_expr_in_recording_rule(self, complex_postgres_config):
        """Test validation handles malformed Prometheus expressions in recording rules."""
        # Corrupt a recording rule expression
        complex_postgres_config["groups"][0]["rules"][0]["expr"] = "invalid(prometheus(expr"
        
        # Schema validation should pass for any string expr (Prometheus syntax validation not in Phase 1)
        validator = ConfigValidator()
        validator.validate_config(complex_postgres_config)  # Should not raise any exception

    def test_macro_reference_consistency(self, complex_app_server_config):
        """Test validation of macro references between template and host definitions."""
        # Add macro reference that doesn't exist in host
        complex_app_server_config["groups"][1]["rules"][0]["expr"] = "app_server_cpu_usage:rate5m >= {$NONEXISTENT.MACRO}"
        
        # Macro reference validation not implemented in Phase 1
        validator = ConfigValidator()
        validator.validate_config(complex_app_server_config)  # Should not raise any exception


class TestValidationErrorMessages:
    """Test that validation provides helpful error messages."""

    def test_validation_error_includes_path(self):
        """Test that validation errors include the path to the invalid field."""
        # Should create ValidationError with path information
        error = ValidationError("Test error", path="groups[0].rules[0].record")
        assert "groups[0].rules[0].record" in str(error)

    def test_validation_error_includes_suggestions(self):
        """Test that validation errors include helpful suggestions."""
        # Should create ValidationError with suggestions
        error = ValidationError(
            "Invalid group name", 
            path="groups[0].name",
            suggestions=["Use 'recording_rules' or 'alerting_rules'"]
        )
        assert "recording_rules" in str(error)
        assert "alerting_rules" in str(error)

    def test_multiple_validation_errors_collected(self):
        """Test that multiple validation errors are collected and reported together."""
        invalid_config = {
            "groups": [
                {
                    "name": "invalid_name",  # Error 1
                    "rules": [
                        {
                            "expr": "test_expr",
                            # Missing record/alert field - Error 2
                        }
                    ]
                }
            ]
            # Missing zabbix section - Error 3
        }
        
        # Should collect and report multiple errors
        validator = ConfigValidator()
        with pytest.raises(ValidationError) as excinfo:
            validator.validate_config(invalid_config)
        error_msg = str(excinfo.value).lower()
        assert "zabbix" in error_msg  # Should report validation error