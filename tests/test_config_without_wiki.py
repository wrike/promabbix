#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import pytest
import yaml
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.fs_utils import DataLoader


class TestConfigurationsWithoutWiki:
    """Test configurations that don't include wiki sections."""

    @pytest.fixture
    def sysops_config_no_wiki(self, temp_directory):
        """Sysops-style configuration without wiki section."""
        config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "postgres_connections",
                            "expr": "sum(pg_stat_database_numbackends{project=\"postgres\"})by(project,cluster,instance)"
                        },
                        {
                            "record": "postgres_max_connections",
                            "expr": "sum(pg_settings_max_connections{project=\"postgres\"})by(project,cluster,instance)"
                        }
                    ]
                },
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "postgres_connections",
                            "expr": "postgres_connections >= {$POSTGRES.CONNECTIONS.MAX}",
                            "annotations": {
                                "description": "instance: {{$labels.instance}}, connections: {{$value}}",
                                "summary": "PostgreSQL instance {{$labels.instance}} has high connection count"
                            },
                            "labels": {
                                "__zbx_priority": "WARNING"
                            }
                        }
                    ]
                }
            ],
            "prometheus": {
                "api": {
                    "url": "http://victoria-metrics.monitoring.svc:8481/api/v1/query"
                }
            },
            "zabbix": {
                "template": "sysops_service_postgres_minimal",
                "name": "Template Module Prometheus SysOps service postgres minimal",
                "macros": [
                    {
                        "macro": "{$POSTGRES.CONNECTIONS.MAX}",
                        "value": 100,
                        "description": "Maximum PostgreSQL connections threshold"
                    }
                ],
                "hosts": [
                    {
                        "host_name": "postgres-prod-minimal",
                        "visible_name": "Service Postgres Prod Minimal",
                        "host_groups": ["Prometheus pseudo hosts"],
                        "link_templates": ["templ_module_promt_sysops_service_postgres_minimal"],
                        "status": "enabled",
                        "state": "present",
                        "proxy": "gce-infra-zbx-pr02"
                    }
                ]
            }
            # Intentionally no wiki section
        }
        
        config_file = temp_directory / "postgres-minimal-config.yaml"
        config_file.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
        return config_file

    @pytest.fixture
    def wrike_config_no_wiki(self, temp_directory):
        """Wrike-style configuration without wiki section."""
        config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "app_http_error_rate",
                            "expr": "sum(rate(http_requests_total{status=~\"5..\",service=\"app-login-server\"}[5m])) / sum(rate(http_requests_total{service=\"app-login-server\"}[5m]))"
                        }
                    ]
                },
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "app_http_error_rate",
                            "expr": "app_http_error_rate >= {$HTTP.ERROR.RATE.MAX}",
                            "annotations": {
                                "description": "service: {{$labels.service}}, error_rate: {{$value}}",
                                "summary": "High HTTP error rate for {{$labels.service}}"
                            },
                            "labels": {
                                "__zbx_priority": "HIGH"
                            }
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "wrike_app_login_server_minimal",
                "name": "Template Module Prometheus Wrike app-login-server minimal",
                "hosts": [
                    {
                        "host_name": "app-login-server-minimal",
                        "visible_name": "App Login Server Minimal",
                        "host_groups": ["Kubernetes clusters", "Backend services"],
                        "link_templates": ["templ_module_promt_wrike_app_login_server_minimal"],
                        "status": "enabled",
                        "state": "present",
                        "proxy": "gce-infra-zbx-pr02",
                        "macros": [
                            {
                                "macro": "{$HTTP.ERROR.RATE.MAX}",
                                "value": 0.05,
                                "description": "Maximum HTTP error rate (5%)"
                            }
                        ]
                    }
                ]
            }
            # Intentionally no wiki section
        }
        
        config_file = temp_directory / "app-login-server-minimal-config.yaml"
        config_file.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
        return config_file

    @pytest.fixture
    def really_minimal_config(self, temp_directory):
        """Absolutely minimal configuration with only required fields."""
        config = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "simple_metric",
                            "expr": "1"
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "minimal_template"
            }
        }
        
        config_file = temp_directory / "minimal-config.yaml"
        config_file.write_text(yaml.dump(config, default_flow_style=False))
        return config_file

    def test_load_sysops_config_without_wiki(self, sysops_config_no_wiki):
        """Test loading sysops configuration without wiki section."""
        loader = DataLoader()
        config = loader.load_from_file(str(sysops_config_no_wiki))
        
        assert "groups" in config
        assert "zabbix" in config
        assert "prometheus" in config
        assert "wiki" not in config  # Verify wiki section is absent
        
        # Verify structure is still valid
        assert len(config["groups"]) == 2
        assert config["groups"][0]["name"] == "recording_rules"
        assert config["groups"][1]["name"] == "alerting_rules"
        assert config["zabbix"]["template"] == "sysops_service_postgres_minimal"

    def test_load_wrike_config_without_wiki(self, wrike_config_no_wiki):
        """Test loading wrike configuration without wiki section."""
        loader = DataLoader()
        config = loader.load_from_file(str(wrike_config_no_wiki))
        
        assert "groups" in config
        assert "zabbix" in config
        assert "wiki" not in config  # Verify wiki section is absent
        
        # Verify wrike-specific structure
        assert config["zabbix"]["template"] == "wrike_app_login_server_minimal"
        assert len(config["groups"][1]["rules"]) == 1
        assert config["groups"][1]["rules"][0]["alert"] == "app_http_error_rate"

    def test_load_really_minimal_config(self, really_minimal_config):
        """Test loading absolutely minimal configuration."""
        loader = DataLoader()
        config = loader.load_from_file(str(really_minimal_config))
        
        assert "groups" in config
        assert "zabbix" in config
        assert "wiki" not in config
        assert "prometheus" not in config
        assert "promabbix" not in config
        
        # Verify minimal structure
        assert len(config["groups"]) == 1
        assert config["groups"][0]["name"] == "recording_rules"
        assert config["zabbix"]["template"] == "minimal_template"

    def test_validation_without_wiki_should_pass(self, sysops_config_no_wiki):
        """Test that validation passes for configurations without wiki section."""
        loader = DataLoader()
        config = loader.load_from_file(str(sysops_config_no_wiki))
        
        # Should pass validation (wiki is optional)
        from promabbix.core.validation import ConfigValidator
        validator = ConfigValidator()
        validator.validate_config(config)  # Should not raise exception

    def test_no_cross_reference_validation_without_wiki(self, wrike_config_no_wiki):
        """Test that cross-reference validation is skipped when wiki section is absent."""
        loader = DataLoader()
        config = loader.load_from_file(str(wrike_config_no_wiki))
        
        # Should pass validation (no cross-reference check)
        from promabbix.core.validation import ConfigValidator
        validator = ConfigValidator()
        validator.validate_config(config)  # Should not raise exception

    def test_template_generation_without_wiki(self, sysops_config_no_wiki):
        """Test that template generation works without wiki section."""
        from promabbix.promabbix import PromabbixApp
        from unittest.mock import patch
        
        app = PromabbixApp()
        # Mock template rendering to avoid needing actual template files
        with patch('promabbix.core.template.Render.render_file', return_value='{"mock": "template"}'):
            with patch('sys.argv', ['promabbix', str(sysops_config_no_wiki)]):
                result = app.main()
                assert result == 0  # Should succeed

    def test_promabbix_app_minimal_config(self, really_minimal_config):
        """Test Promabbix app with absolutely minimal configuration."""
        from promabbix.promabbix import PromabbixApp
        from unittest.mock import patch
        
        app = PromabbixApp()
        # Mock template rendering to avoid needing actual template files
        with patch('promabbix.core.template.Render.render_file', return_value='{"mock": "template"}'):
            with patch('sys.argv', ['promabbix', str(really_minimal_config)]):
                result = app.main()
                assert result == 0  # Should handle minimal config correctly

    def test_mixed_configs_some_with_some_without_wiki(self, temp_directory):
        """Test handling multiple configurations where some have wiki and some don't."""
        # Config with wiki
        config_with_wiki = {
            "groups": [
                {"name": "recording_rules", "rules": [{"record": "metric1", "expr": "1"}]},
                {"name": "alerting_rules", "rules": [{"alert": "metric1", "expr": "metric1 > 0", "annotations": {"summary": "Test"}}]}
            ],
            "zabbix": {"template": "with_wiki"},
            "wiki": {
                "knowledgebase": {
                    "alerts": {
                        "alertings": {
                            "metric1": {"title": "Metric 1", "content": "Test metric"}
                        }
                    }
                }
            }
        }
        
        # Config without wiki
        config_without_wiki = {
            "groups": [
                {"name": "recording_rules", "rules": [{"record": "metric2", "expr": "2"}]},
                {"name": "alerting_rules", "rules": [{"alert": "metric2", "expr": "metric2 > 1", "annotations": {"summary": "Test"}}]}
            ],
            "zabbix": {"template": "without_wiki"}
        }
        
        config_with_wiki_file = temp_directory / "with-wiki.yaml"
        config_without_wiki_file = temp_directory / "without-wiki.yaml"
        
        config_with_wiki_file.write_text(yaml.dump(config_with_wiki))
        config_without_wiki_file.write_text(yaml.dump(config_without_wiki))
        
        loader = DataLoader()
        
        # Both should load successfully
        wiki_config = loader.load_from_file(str(config_with_wiki_file))
        no_wiki_config = loader.load_from_file(str(config_without_wiki_file))
        
        assert "wiki" in wiki_config
        assert "wiki" not in no_wiki_config
        
        # Both should validate successfully
        from promabbix.core.validation import ConfigValidator
        validator = ConfigValidator()
        validator.validate_config(wiki_config)  # Should validate cross-references
        validator.validate_config(no_wiki_config)  # Should skip cross-reference validation