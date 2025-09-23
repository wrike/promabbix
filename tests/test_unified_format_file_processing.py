#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import pytest
import yaml
import json
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.fs_utils import DataLoader
from promabbix.promabbix import PromabbixApp


class TestUnifiedFormatFileProcessing:
    """Test processing of unified format files end-to-end."""

    @pytest.fixture
    def sample_unified_file(self, temp_directory):
        """Create a sample unified alert config file."""
        config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "redis_connected_clients",
                            "expr": "sum(redis_connected_clients{project=\"redis\"})by(project,cluster,instance)>=0"
                        },
                        {
                            "record": "redis_memory_usage_ratio",
                            "expr": "sum(redis_memory_used_bytes{project=\"redis\"})by(project,cluster,instance) / sum(redis_memory_max_bytes{project=\"redis\"})by(project,cluster,instance)"
                        }
                    ]
                },
                {
                    "name": "alerting_rules", 
                    "rules": [
                        {
                            "alert": "redis_connected_clients",
                            "expr": "redis_connected_clients >= {$REDIS.CONNECTED.CLIENTS.MAX}",
                            "annotations": {
                                "description": "instance: {{$labels.instance}}, clients: {{$value}}",
                                "summary": "Redis instance {{$labels.instance}} has high client connections"
                            }
                        },
                        {
                            "alert": "redis_memory_usage_ratio",
                            "expr": "redis_memory_usage_ratio >= {$REDIS.MEMORY.USAGE.RATIO.MAX}",
                            "annotations": {
                                "description": "instance: {{$labels.instance}}, ratio: {{$value}}",
                                "summary": "Redis instance {{$labels.instance}} has high memory usage"
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
                ]
            },
            "promabbix": {
                "zabbix_depend_item_preprocessing": "$.metrics[\"{#ZBX.ITEM.SUBKEY}\"]",
                "zabbix_master_item_preprocessing": """var ingest_json = JSON.parse(value),
    metrics = ingest_json.data.result || [],
    result = { "lld": [], "metrics": {} };
for (var i = 0; i < metrics.length; i++) {
    var metric = metrics[i];
    result.lld.push({"{#INSTANCE}": metric.metric.instance});
    result.metrics[metric.metric.instance] = metric.value[1];
}
return JSON.stringify(result);"""
            },
            "zabbix": {
                "template": "service_redis",
                "name": "Template Module Prometheus service redis",
                "labels": {
                    "slack_alarm_channel_name": "{$SLACK.ALARM.CHANNEL.NAME}"
                },
                "lld_filters": {
                    "filter": {
                        "conditions": [
                            {
                                "formulaid": "A",
                                "macro": "{#PROJECT}",
                                "value": "{$REDIS.PROJECT.LLD.MATCHES}"
                            },
                            {
                                "formulaid": "B",
                                "macro": "{#CLUSTER}",
                                "value": "{$REDIS.CLUSTER.LLD.MATCHES}"
                            }
                        ],
                        "evaltype": "AND"
                    }
                },
                "macros": [
                    {
                        "macro": "{$REDIS.PROJECT.LLD.MATCHES}",
                        "description": "Redis project LLD filter",
                        "value": ".*"
                    },
                    {
                        "macro": "{$REDIS.CLUSTER.LLD.MATCHES}",
                        "description": "Redis cluster LLD filter",
                        "value": ".*"
                    },
                    {
                        "macro": "{$REDIS.CONNECTED.CLIENTS.MAX}",
                        "description": "Maximum Redis connected clients threshold",
                        "value": 1000
                    },
                    {
                        "macro": "{$REDIS.MEMORY.USAGE.RATIO.MAX}",
                        "description": "Maximum Redis memory usage ratio",
                        "value": 0.9
                    }
                ],
                "tags": [
                    {
                        "tag": "service_kind",
                        "value": "redis"
                    }
                ],
                "hosts": [
                    {
                        "host_name": "redis-prod",
                        "visible_name": "Service Redis Prod",
                        "host_groups": ["Prometheus pseudo hosts"],
                        "link_templates": ["templ_module_promt_service_redis"],
                        "status": "enabled",
                        "state": "present",
                        "proxy": "gce-infra-zbx-pr02",
                        "macros": [
                            {
                                "macro": "{$SLACK.ALARM.CHANNEL.NAME}",
                                "value": "cache-alerts"
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
                                "name": "redis",
                                "title": "Alert redis configuration"
                            }
                        ]
                    }
                },
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "redis_connected_clients": {
                                "title": "Redis High Client Connections Alert",
                                "content": "This alert triggers when Redis has too many connected clients, which may indicate connection leaks or high load."
                            },
                            "redis_memory_usage_ratio": {
                                "title": "Redis High Memory Usage Alert",
                                "content": "This alert triggers when Redis memory usage exceeds the threshold, which may lead to eviction or OOM conditions."
                            }
                        }
                    }
                }
            }
        }
        
        config_file = temp_directory / "redis-config.yaml"
        config_file.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
        return config_file

    @pytest.fixture  
    def sample_second_unified_file(self, temp_directory):
        """Create a sample unified alert config file."""
        config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "data_export_queue_depth",
                            "expr": "sum(rabbitmq_queue_messages{queue=~\".*data.export.*\"})by(k8s_cluster,namespace,queue)"
                        },
                        {
                            "record": "data_export_processing_time",
                            "expr": "histogram_quantile(0.95, sum(rate(data_export_processing_duration_seconds_bucket[5m]))by(k8s_cluster,namespace,pod,le))"
                        }
                    ]
                },
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "data_export_queue_depth", 
                            "expr": "data_export_queue_depth >= {$DATA.EXPORT.QUEUE.DEPTH.MAX}",
                            "annotations": {
                                "description": "queue: {{$labels.queue}}, depth: {{$value}}",
                                "summary": "Data export queue {{$labels.queue}} has high message count"
                            },
                            "labels": {
                                "__zbx_priority": "WARNING"
                            }
                        },
                        {
                            "alert": "data_export_processing_time",
                            "expr": "data_export_processing_time >= {$DATA.EXPORT.PROCESSING.TIME.MAX}",
                            "annotations": {
                                "description": "pod: {{$labels.pod}}, processing_time: {{$value}}s",
                                "summary": "Data export processing time too high in {{$labels.pod}}"
                            }
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "data_export",
                "name": "Template Module Prometheus data-export",
                "hosts": [
                    {
                        "host_name": "ams-k8s-cluster-backend-services",
                        "visible_name": "AMS K8s Backend Services",
                        "host_groups": ["Kubernetes clusters", "Backend services"],
                        "link_templates": ["templ_module_promt_data_export"],
                        "status": "enabled",
                        "state": "present",
                        "proxy": "gce-infra-zbx-pr02",
                        "macros": [
                            {
                                "macro": "{$DATA.EXPORT.QUEUE.DEPTH.MAX}",
                                "value": 10000
                            },
                            {
                                "macro": "{$DATA.EXPORT.PROCESSING.TIME.MAX}",
                                "value": 300
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
                                "name": "data-export",
                                "title": "data-export alert configuration"
                            }
                        ]
                    }
                },
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "data_export_queue_depth": {
                                "title": "Data Export Queue Depth Alert",
                                "content": "This alert indicates high message queue depth for data export processing, which may cause delays in data availability."
                            },
                            "data_export_processing_time": {
                                "title": "Data Export Processing Time Alert", 
                                "content": "This alert triggers when data export processing takes longer than expected, indicating performance issues."
                            }
                        }
                    }
                }
            }
        }
        
        config_file = temp_directory / "data-export-config.yaml"
        config_file.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
        return config_file

    @pytest.fixture
    def malformed_unified_file(self, temp_directory):
        """Create a malformed unified config file for testing error handling."""
        malformed_config = {
            "groups": [
                {
                    "name": "invalid_group_name",  # Should be recording_rules or alerting_rules
                    "rules": [
                        {
                            "expr": "sum(metric) by (label)",
                            # Missing record field for recording rule
                        }
                    ]
                },
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "expr": "metric > threshold",
                            # Missing alert field for alerting rule
                            "annotations": {
                                "summary": "Test alert"
                            }
                        }
                    ]
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
                        "state": "invalid_state"    # Should be present/absent
                    }
                ]
            },
            "wiki": {
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "non_existent_alert": {  # Alert not defined in groups
                                "title": "Non-existent Alert",
                                "content": "Documentation for alert that doesn't exist"
                            }
                        }
                    }
                }
            }
            # Missing prometheus section (optional but referenced in examples)
        }
        
        config_file = temp_directory / "malformed-config.yaml"
        config_file.write_text(yaml.dump(malformed_config, default_flow_style=False))
        return config_file

    def test_load_unified_file(self, sample_unified_file):
        """Test loading unified config file."""
        loader = DataLoader()
        config = loader.load_from_file(str(sample_unified_file))
        
        assert "groups" in config
        assert "zabbix" in config
        assert "wiki" in config
        assert "prometheus" in config
        assert "promabbix" in config
        
        # Verify structure
        assert len(config["groups"]) == 2
        assert config["groups"][0]["name"] == "recording_rules"
        assert config["groups"][1]["name"] == "alerting_rules"
        assert config["zabbix"]["template"] == "service_redis"

    def test_load_second_unified_file(self, sample_second_unified_file):
        """Test loading unified config file."""
        loader = DataLoader()
        config = loader.load_from_file(str(sample_second_unified_file))
        
        assert "groups" in config
        assert "zabbix" in config
        assert "wiki" in config
        
        # Verify specific structure
        assert config["zabbix"]["template"] == "data_export"
        assert len(config["groups"][1]["rules"]) == 2
        assert "data_export_queue_depth" in [rule["alert"] for rule in config["groups"][1]["rules"]]

    def test_promabbix_app_with_unified_file_validation_only(self, sample_unified_file):
        """Test Promabbix app with validation-only mode on unified file."""
        from unittest.mock import patch
        
        app = PromabbixApp()
        # Test validation-only mode
        with patch('sys.argv', ['promabbix', str(sample_unified_file), '--validate-only']):
            result = app.main()
            assert result == 0  # Should validate successfully

    def test_promabbix_app_with_unified_file_template_generation(self, sample_unified_file):
        """Test Promabbix app generating templates from unified file."""
        from unittest.mock import patch
        
        app = PromabbixApp()
        # Mock template rendering to avoid needing actual template files
        with patch('promabbix.core.template.Render.render_file', return_value='{"mock": "template"}'):
            with patch('sys.argv', ['promabbix', str(sample_unified_file)]):
                result = app.main()
                assert result == 0  # Should generate template successfully

    def test_malformed_unified_file_validation_errors(self, malformed_unified_file):
        """Test validation errors with malformed unified config file."""
        loader = DataLoader()
        config = loader.load_from_file(str(malformed_unified_file))
        
        # Should provide detailed validation errors
        from promabbix.core.validation import ConfigValidator, ValidationError
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(config)

    def test_stdin_unified_format_processing(self, sample_unified_file):
        """Test processing unified format from STDIN."""
        from unittest.mock import patch
        
        # Read the sample file content
        with open(sample_unified_file, 'r') as f:
            yaml_content = f.read()
        
        # Mock stdin with the YAML content
        with patch('sys.stdin.read', return_value=yaml_content):
            loader = DataLoader()
            config = loader.load_from_stdin()
            
            assert "groups" in config
            assert "zabbix" in config
            assert config["zabbix"]["template"] == "service_redis"

    def test_stdout_template_generation(self, sample_unified_file):
        """Test generating Zabbix template to STDOUT from unified file."""
        from unittest.mock import patch
        
        app = PromabbixApp()
        # Mock template rendering to avoid needing actual template files
        with patch('promabbix.core.template.Render.render_file', return_value='{"mock": "template"}'):
            with patch('sys.argv', ['promabbix', str(sample_unified_file), '-o', '-']):
                result = app.main()
                assert result == 0  # Should output template to stdout

    def test_file_format_detection_yaml_vs_json(self, temp_directory):
        """Test that DataLoader can handle both YAML and JSON unified formats."""
        config_dict = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [{"record": "test_metric", "expr": "1"}]
                }
            ],
            "zabbix": {"template": "test_template"}
        }
        
        # Test YAML format
        yaml_file = temp_directory / "config.yaml"
        yaml_file.write_text(yaml.dump(config_dict))
        
        # Test JSON format  
        json_file = temp_directory / "config.json"
        json_file.write_text(json.dumps(config_dict, indent=2))
        
        loader = DataLoader()
        
        yaml_config = loader.load_from_file(str(yaml_file))
        json_config = loader.load_from_file(str(json_file))
        
        assert yaml_config == json_config
        assert yaml_config["zabbix"]["template"] == "test_template"

    def test_large_unified_config_performance(self, temp_directory):
        """Test processing performance with large unified configuration."""
        # Generate a large config with many alerts
        large_config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": f"service_{i}_metric",
                            "expr": f"sum(metric_{i})by(label)"
                        } for i in range(100)  # 100 recording rules
                    ]
                },
                {
                    "name": "alerting_rules", 
                    "rules": [
                        {
                            "alert": f"service_{i}_metric",
                            "expr": f"service_{i}_metric > {i * 10}",
                            "annotations": {
                                "summary": f"Service {i} alert"
                            }
                        } for i in range(100)  # 100 alerting rules
                    ]
                }
            ],
            "zabbix": {
                "template": "large_template",
                "hosts": [
                    {
                        "host_name": f"host-{i}",
                        "visible_name": f"Host {i}",
                        "host_groups": ["Test Group"],
                        "link_templates": ["large_template"],
                        "status": "enabled",
                        "state": "present"
                    } for i in range(50)  # 50 hosts
                ]
            },
            "wiki": {
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            f"service_{i}_metric": {
                                "title": f"Service {i} Alert",
                                "content": f"Documentation for service {i}"
                            } for i in range(100)
                        }
                    }
                }
            }
        }
        
        large_file = temp_directory / "large-config.yaml"
        large_file.write_text(yaml.dump(large_config, default_flow_style=False))
        
        # Test loading performance
        loader = DataLoader()
        config = loader.load_from_file(str(large_file))
        
        assert len(config["groups"][0]["rules"]) == 100
        assert len(config["groups"][1]["rules"]) == 100
        assert len(config["zabbix"]["hosts"]) == 50
        
        # Test validation performance
        from promabbix.core.validation import ConfigValidator
        validator = ConfigValidator()
        validator.validate_config(config)  # Should handle large configs


class TestBackwardsCompatibility:
    """Test backwards compatibility with existing three-file format."""

    @pytest.fixture
    def sample_unified_file(self, temp_directory):
        """Create a sample unified config file for testing."""
        import yaml
        config = {
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
                "template": "test_service_template",
                "name": "Test Service Template"
            }
        }
        
        config_file = temp_directory / "unified-config.yaml"
        config_file.write_text(yaml.dump(config, default_flow_style=False))
        return config_file

    @pytest.fixture
    def legacy_three_file_structure(self, temp_directory):
        """Create legacy three-file structure for compatibility testing."""
        service_dir = temp_directory / "service" / "test-service"
        service_dir.mkdir(parents=True)
        
        # alerts.yaml
        alerts_content = {
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
            ]
        }
        
        # zabbix_vars.yaml
        zabbix_content = {
            "zabbix": {
                "template": "test_service_template",
                "name": "Test Service Template",
                "hosts": [
                    {
                        "host_name": "test-host",
                        "visible_name": "Test Host",
                        "host_groups": ["Test Group"],
                        "link_templates": ["test_service_template"],
                        "status": "enabled",
                        "state": "present"
                    }
                ]
            }
        }
        
        # wiki_vars.yaml
        wiki_content = {
            "wiki": {
                "templates": {
                    "wrike_alert_config": {
                        "templates": [
                            {
                                "name": "test-service",
                                "title": "Test Service Alert Configuration"
                            }
                        ]
                    }
                },
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "test_metric": {
                                "title": "Test Metric Alert",
                                "content": "This alert monitors test metrics"
                            }
                        }
                    }
                }
            }
        }
        
        # Write files
        (service_dir / "test_service_alerts.yaml").write_text(yaml.dump(alerts_content))
        (service_dir / "zabbix_vars.yaml").write_text(yaml.dump(zabbix_content))
        (service_dir / "wiki_vars.yaml").write_text(yaml.dump(wiki_content))
        
        return service_dir

    def test_migrate_legacy_to_unified_format(self, legacy_three_file_structure):
        """Test migration from legacy three-file format to unified format."""
        from promabbix.core.migration import migrate_legacy_service
        
        unified_config = migrate_legacy_service(str(legacy_three_file_structure))
        
        assert "groups" in unified_config
        assert "zabbix" in unified_config  
        assert "wiki" in unified_config
        
        # Verify structure is correct
        assert len(unified_config["groups"]) == 2
        assert unified_config["groups"][0]["name"] == "recording_rules"
        assert unified_config["groups"][1]["name"] == "alerting_rules"
        assert unified_config["zabbix"]["template"] == "test_service_template"

    def test_detect_legacy_vs_unified_format(self, legacy_three_file_structure, sample_unified_file):
        """Test detection of legacy vs unified format."""
        from promabbix.core.migration import detect_config_format
        
        legacy_format = detect_config_format(str(legacy_three_file_structure))
        unified_format = detect_config_format(str(sample_unified_file))
        
        assert legacy_format == "legacy_three_file"
        assert unified_format == "unified"

    def test_builder_script_fallback_support(self, legacy_three_file_structure):
        """Test that builder scripts can fall back to legacy processing."""
        from promabbix.core.migration import detect_builder_script_format
        
        # Test builder script format detection
        format_result = detect_builder_script_format(str(legacy_three_file_structure))
        assert format_result == "legacy"
        
        # Test that the function returns simple strings for shell script use
        assert format_result in ["legacy", "unified", None]