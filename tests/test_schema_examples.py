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


class TestSchemaValidationExamples:
    """Test JSON schema validation with various example configurations."""

    @pytest.fixture
    def unified_schema(self):
        """Load the unified JSON schema."""
        schema_path = Path(__file__).parent.parent / "schemas" / "unified.json"
        if not schema_path.exists():
            raise FileNotFoundError(f"unified.json schema not found at {schema_path}")
        
        with open(schema_path) as f:
            return json.load(f)

    @pytest.fixture
    def minimal_valid_config(self):
        """Minimal valid configuration that should pass schema validation."""
        return {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "test_metric",
                            "expr": "sum(test_metric_total) by (label)"
                        }
                    ]
                },
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "test_metric",
                            "expr": "test_metric > 100",
                            "annotations": {
                                "summary": "Test metric too high"
                            }
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }

    @pytest.fixture
    def comprehensive_valid_config(self):
        """Comprehensive configuration with all optional sections."""
        return {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "http_requests:rate5m",
                            "expr": "sum(rate(http_requests_total[5m])) by (service, method)",
                            "labels": {
                                "team": "backend"
                            }
                        },
                        {
                            "record": "error_rate:ratio",
                            "expr": "sum(rate(http_requests_total{status=~\"5..\"}[5m])) / sum(rate(http_requests_total[5m]))"
                        }
                    ]
                },
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "http_requests:rate5m",
                            "expr": "http_requests:rate5m > {$HTTP_RATE_THRESHOLD}",
                            "for": "5m",
                            "labels": {
                                "__zbx_priority": "WARNING",
                                "team": "backend"
                            },
                            "annotations": {
                                "summary": "High HTTP request rate detected",
                                "description": "Service {{$labels.service}} has {{$value}} requests/sec"
                            }
                        },
                        {
                            "alert": "error_rate:ratio",
                            "expr": "error_rate:ratio > 0.1",
                            "labels": {
                                "__zbx_priority": "HIGH"
                            },
                            "annotations": {
                                "summary": "High error rate detected",
                                "description": "Error rate is {{$value}} (10% threshold)"
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
                        "pattern": "\\{\\{(?:\\s*)\\$value(?:\\s*)\\}\\}",
                        "value": "{ITEM.VALUE1}"
                    },
                    {
                        "pattern": "\\{\\{(?:\\s*)\\$labels\\.(?P<label>[a-zA-Z0-9\\_\\-]*)(?:\\s*)\\}\\}",
                        "value": "{#\\g<label>}"
                    }
                ],
                "query_chars_encoding": [
                    {"char": "+", "encode": "%2B"},
                    {"char": " ", "encode": "%20"}
                ]
            },
            "promabbix": {
                "zabbix_depend_item_preprocessing": "$.metrics[\"{#ZBX.ITEM.SUBKEY}\"]",
                "zabbix_master_item_preprocessing": "var result = JSON.parse(value); return JSON.stringify(result);"
            },
            "zabbix": {
                "template": "comprehensive_service",
                "name": "Template Module Prometheus Comprehensive Service",
                "labels": {
                    "team": "backend",
                    "environment": "{$ENVIRONMENT}"
                },
                "lld_filters": {
                    "filter": {
                        "conditions": [
                            {
                                "formulaid": "A",
                                "macro": "{#SERVICE}",
                                "value": "{$SERVICE_LLD_MATCHES}",
                                "operator": "matches"
                            },
                            {
                                "formulaid": "B", 
                                "macro": "{#ENVIRONMENT}",
                                "value": "{$ENV_LLD_MATCHES}"
                            }
                        ],
                        "evaltype": "AND"
                    }
                },
                "macros": [
                    {
                        "macro": "{$HTTP_RATE_THRESHOLD}",
                        "value": 1000,
                        "description": "HTTP request rate threshold per second"
                    },
                    {
                        "macro": "{$SERVICE_LLD_MATCHES}",
                        "value": ".*",
                        "description": "Service name filter for LLD"
                    },
                    {
                        "macro": "{$ENV_LLD_MATCHES}",
                        "value": "(prod|staging)",
                        "description": "Environment filter for LLD"
                    },
                    {
                        "macro": "{$ERROR_RATE_THRESHOLD:\"critical\"}",
                        "value": 0.05,
                        "description": "Critical error rate threshold"
                    }
                ],
                "tags": [
                    {
                        "tag": "service_type",
                        "value": "web_service"
                    },
                    {
                        "tag": "monitoring_source",
                        "value": "prometheus"
                    }
                ],
                "hosts": [
                    {
                        "host_name": "web-service-prod",
                        "visible_name": "Web Service Production",
                        "host_groups": ["Web Services", "Production"],
                        "link_templates": ["templ_module_promt_comprehensive_service"],
                        "status": "enabled",
                        "state": "present",
                        "proxy": "monitoring-proxy-01",
                        "macros": [
                            {
                                "macro": "{$ENVIRONMENT}",
                                "value": "production"
                            },
                            {
                                "macro": "{$HTTP_RATE_THRESHOLD}",
                                "value": 500,
                                "description": "Production-specific threshold"
                            }
                        ]
                    },
                    {
                        "host_name": "web-service-staging",
                        "visible_name": "Web Service Staging",
                        "host_groups": ["Web Services", "Staging"],
                        "link_templates": ["templ_module_promt_comprehensive_service"],
                        "status": "enabled",
                        "state": "present",
                        "proxy": None,
                        "macros": [
                            {
                                "macro": "{$ENVIRONMENT}",
                                "value": "staging"
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
                                "name": "comprehensive-service",
                                "title": "Comprehensive Service Alert Configuration"
                            }
                        ]
                    }
                },
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "http_requests:rate5m": {
                                "title": "High HTTP Request Rate Alert",
                                "content": "This alert triggers when the HTTP request rate exceeds the configured threshold. It indicates either increased traffic or potential issues with request processing efficiency."
                            },
                            "error_rate:ratio": {
                                "title": "High Error Rate Alert",
                                "content": "This alert indicates an elevated error rate above acceptable thresholds. Investigation should focus on recent deployments, infrastructure issues, or upstream service problems."
                            }
                        }
                    }
                }
            }
        }

    def test_minimal_config_schema_validation(self, minimal_valid_config, unified_schema):
        """Test minimal valid configuration passes schema validation."""
        # Should pass validation
        from promabbix.core.validation import ConfigValidator
        validator = ConfigValidator()
        validator.validate_config(minimal_valid_config)  # Should not raise exception

    def test_comprehensive_config_schema_validation(self, comprehensive_valid_config, unified_schema):
        """Test comprehensive configuration passes schema validation."""
        # Should pass validation
        from promabbix.core.validation import ConfigValidator
        validator = ConfigValidator()
        validator.validate_config(comprehensive_valid_config)  # Should not raise exception

    def test_missing_required_groups_fails_validation(self, unified_schema):
        """Test that missing required 'groups' section fails validation."""
        invalid_config = {
            "zabbix": {
                "template": "test_template"
            }
        }
        
        # Should fail validation
        from promabbix.core.validation import ConfigValidator, ValidationError
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(invalid_config)

    def test_missing_required_zabbix_fails_validation(self, unified_schema):
        """Test that missing required 'zabbix' section fails validation."""
        invalid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": []
                }
            ]
        }
        
        # Should fail validation
        from promabbix.core.validation import ConfigValidator, ValidationError
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(invalid_config)

    def test_invalid_group_name_fails_validation(self, unified_schema):
        """Test that invalid group name fails validation."""
        invalid_config = {
            "groups": [
                {
                    "name": "invalid_group_name",  # Should be recording_rules or alerting_rules
                    "rules": []
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        
        # Should fail validation
        from promabbix.core.validation import ConfigValidator, ValidationError
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(invalid_config)

    def test_recording_rule_missing_record_fails_validation(self, unified_schema):
        """Test that recording rule without 'record' field fails validation."""
        invalid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "expr": "sum(metric) by (label)"
                            # Missing "record" field
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        
        # Should fail validation
        from promabbix.core.validation import ConfigValidator, ValidationError
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(invalid_config)

    def test_alerting_rule_missing_alert_fails_validation(self, unified_schema):
        """Test that alerting rule without 'alert' field fails validation."""
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
        
        # Should fail validation
        from promabbix.core.validation import ConfigValidator, ValidationError
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(invalid_config)

    def test_invalid_zabbix_priority_fails_validation(self, unified_schema):
        """Test that invalid __zbx_priority value fails validation."""
        invalid_config = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "test_alert",
                            "expr": "metric > 1",
                            "labels": {
                                "__zbx_priority": "INVALID_PRIORITY"  # Should be INFO/WARNING/AVERAGE/HIGH/DISASTER
                            },
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
        
        # Should fail validation
        from promabbix.core.validation import ConfigValidator, ValidationError
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(invalid_config)

    def test_invalid_host_status_fails_validation(self, unified_schema):
        """Test that invalid host status fails validation."""
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
                        "status": "invalid_status",  # Should be enabled/disabled
                        "state": "present"
                    }
                ]
            }
        }
        
        # Should fail validation
        from promabbix.core.validation import ConfigValidator, ValidationError
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(invalid_config)

    def test_invalid_lld_formulaid_fails_validation(self, unified_schema):
        """Test that invalid LLD formulaid fails validation."""
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
        
        # Should fail validation
        from promabbix.core.validation import ConfigValidator, ValidationError
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(invalid_config)

    def test_invalid_macro_format_fails_validation(self, unified_schema):
        """Test that invalid macro format fails validation."""
        invalid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ],
            "zabbix": {
                "template": "test_template",
                "macros": [
                    {
                        "macro": "INVALID_MACRO_FORMAT",  # Should be {$NAME} format
                        "value": "test"
                    }
                ]
            }
        }
        
        # Should fail validation
        from promabbix.core.validation import ConfigValidator, ValidationError
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(invalid_config)

    def test_invalid_template_name_fails_validation(self, unified_schema):
        """Test that invalid template name fails validation."""
        invalid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ],
            "zabbix": {
                "template": "invalid-template-name!",  # Should be alphanumeric and underscore only
            }
        }
        
        # Should fail validation
        from promabbix.core.validation import ConfigValidator, ValidationError
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(invalid_config)

    def test_invalid_record_name_fails_validation(self, unified_schema):
        """Test that invalid record name fails validation."""
        invalid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "123invalid_start",  # Should start with letter
                            "expr": "sum(metric)"
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        
        # Should fail validation
        from promabbix.core.validation import ConfigValidator, ValidationError
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(invalid_config)

    def test_missing_annotations_summary_fails_validation(self, unified_schema):
        """Test that alerting rule without summary annotation fails validation."""
        invalid_config = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "test_alert",
                            "expr": "metric > 1",
                            "annotations": {
                                "description": "Some description"
                                # Missing required "summary" field
                            }
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
        }
        
        # Should fail validation
        from promabbix.core.validation import ConfigValidator, ValidationError
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(invalid_config)

    def test_prometheus_url_validation_accepts_valid_urls(self, unified_schema):
        """Test that valid Prometheus URLs are accepted."""
        valid_configs = [
            {
                "groups": [
                    {
                        "name": "recording_rules",
                        "rules": [{"record": "test", "expr": "1"}]
                    }
                ],
                "prometheus": {
                    "api": {
                        "url": "http://prometheus:9090/api/v1/query"
                    }
                },
                "zabbix": {
                    "template": "test_template"
                }
            },
            {
                "groups": [
                    {
                        "name": "recording_rules",
                        "rules": [{"record": "test", "expr": "1"}]
                    }
                ],
                "prometheus": {
                    "api": {
                        "url": "https://victoria-metrics.monitoring.svc:8481/api/v1/query"
                    }
                },
                "zabbix": {
                    "template": "test_template"
                }
            }
        ]
        
        from promabbix.core.validation import ConfigValidator
        validator = ConfigValidator()
        
        for config in valid_configs:
            # Should pass validation
            validator.validate_config(config)

    def test_additional_properties_not_allowed(self, unified_schema):
        """Test that additional properties not defined in schema are rejected."""
        invalid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ],
            "zabbix": {
                "template": "test_template"
            },
            "unknown_section": {  # Not allowed by schema
                "some_property": "value"
            }
        }
        
        # Should fail validation
        from promabbix.core.validation import ConfigValidator, ValidationError
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(invalid_config)

    def test_empty_arrays_allowed_where_appropriate(self, unified_schema):
        """Test that empty arrays are allowed for optional array fields."""
        valid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": []  # Empty rules array should be allowed
                }
            ],
            "zabbix": {
                "template": "test_template",
                "macros": [],  # Empty macros array should be allowed
                "tags": [],    # Empty tags array should be allowed
                "hosts": []    # Empty hosts array should be allowed
            }
        }
        
        # Should pass validation
        from promabbix.core.validation import ConfigValidator
        validator = ConfigValidator()
        validator.validate_config(valid_config)  # Should not raise exception

    def test_schema_supports_contextual_macros(self, unified_schema):
        """Test that schema supports contextual macros like {$MACRO:\"context\"}."""
        valid_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test", "expr": "1"}]
                }
            ],
            "zabbix": {
                "template": "test_template",
                "macros": [
                    {
                        "macro": "{$THRESHOLD:\"service_name\"}",  # Contextual macro
                        "value": 100,
                        "description": "Service-specific threshold"
                    },
                    {
                        "macro": "{$THRESHOLD:regex:\"^web.*$\"}",  # Regex context macro
                        "value": 200
                    }
                ]
            }
        }
        
        # Should pass validation
        from promabbix.core.validation import ConfigValidator
        validator = ConfigValidator()
        validator.validate_config(valid_config)  # Should not raise exception