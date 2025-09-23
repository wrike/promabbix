#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import pytest
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.validation import ConfigValidator, ValidationError


class TestWikiSectionOptional:
    """Test that wiki section is optional in unified configuration."""

    def test_config_valid_without_wiki_section(self):
        """Test that configuration without wiki section passes validation."""
        config_without_wiki = {
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
                "template": "test_template",
                "hosts": [
                    {
                        "host_name": "test-host",
                        "visible_name": "Test Host",
                        "host_groups": ["Test Group"],
                        "link_templates": ["test_template"],
                        "status": "enabled",
                        "state": "present"
                    }
                ]
            }
            # No wiki section - should be valid
        }
        
        # Should pass validation
        validator = ConfigValidator()
        validator.validate_config(config_without_wiki)  # Should not raise exception

    def test_config_valid_with_wiki_section(self):
        """Test that configuration with wiki section also passes validation."""
        config_with_wiki = {
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
            },
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
        
        # Should pass validation
        validator = ConfigValidator()
        validator.validate_config(config_with_wiki)  # Should not raise exception

    def test_cross_reference_validation_only_when_both_present(self):
        """Test that cross-reference validation only runs when both alerts and wiki are present."""
        # Config with alerts but no wiki - should not validate cross-references
        config_alerts_no_wiki = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "undocumented_alert",
                            "expr": "metric > 1",
                            "annotations": {"summary": "Test"}
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "test_template"
            }
            # No wiki section - cross-reference validation should be skipped
        }
        
        # Should pass validation (no cross-reference check)
        validator = ConfigValidator()
        validator.validate_config(config_alerts_no_wiki)  # Should not raise exception

    def test_cross_reference_validation_when_both_present(self):
        """Test that cross-reference validation runs when both alerts and wiki are present."""
        # Config with alerts and wiki but missing documentation
        config_missing_docs = {
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
        
        # Should fail validation (missing cross-reference)
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(config_missing_docs)

    def test_empty_wiki_section_allowed(self):
        """Test that empty wiki section is allowed."""
        config_empty_wiki = {
            "groups": [
                {
                    "name": "recording_rules",
                    "rules": [
                        {
                            "record": "test_metric",
                            "expr": "sum(metric)"
                        }
                    ]
                }
            ],
            "zabbix": {
                "template": "test_template"
            },
            "wiki": {}  # Empty wiki section should be allowed
        }
        
        # Should pass validation
        validator = ConfigValidator()
        validator.validate_config(config_empty_wiki)  # Should not raise exception

    def test_wiki_with_templates_only(self):
        """Test that wiki section with only templates (no knowledgebase) is valid."""
        config_templates_only = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "test_alert",
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
                "templates": {
                    "wrike_alert_config": {
                        "templates": [
                            {
                                "name": "test-service",
                                "title": "Test Service Configuration"
                            }
                        ]
                    }
                }
                # No knowledgebase section - should be valid, no cross-reference check
            }
        }
        
        # Should pass validation (no cross-reference check)
        validator = ConfigValidator()
        validator.validate_config(config_templates_only)  # Should not raise exception

    def test_wiki_with_knowledgebase_only(self):
        """Test that wiki section with only knowledgebase (no templates) is valid."""
        config_knowledgebase_only = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "test_alert",
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
                            "test_alert": {
                                "title": "Test Alert",
                                "content": "Documentation for test alert"
                            }
                        }
                    }
                }
                # No templates section - should be valid with cross-reference check
            }
        }
        
        # Should pass validation (cross-reference check passes)
        validator = ConfigValidator()
        validator.validate_config(config_knowledgebase_only)  # Should not raise exception

    def test_minimal_config_without_optional_sections(self):
        """Test minimal configuration with only required sections."""
        minimal_config = {
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
            # No prometheus, promabbix, or wiki sections - should be valid
        }
        
        # Should pass validation
        validator = ConfigValidator()
        validator.validate_config(minimal_config)  # Should not raise exception

    def test_cross_reference_validation_with_partial_wiki(self):
        """Test cross-reference validation when wiki has some but not all alert documentation."""
        config_partial_docs = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "alert_one",
                            "expr": "metric1 > 1",
                            "annotations": {"summary": "Alert One"}
                        },
                        {
                            "alert": "alert_two",
                            "expr": "metric2 > 2", 
                            "annotations": {"summary": "Alert Two"}
                        },
                        {
                            "alert": "alert_three",
                            "expr": "metric3 > 3",
                            "annotations": {"summary": "Alert Three"}
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
                            "alert_one": {
                                "title": "Alert One",
                                "content": "Documentation for alert one"
                            },
                            "alert_three": {
                                "title": "Alert Three",
                                "content": "Documentation for alert three"
                            }
                            # alert_two is missing documentation
                        }
                    }
                }
            }
        }
        
        # Should fail validation (alert_two missing docs)
        validator = ConfigValidator()
        with pytest.raises(ValidationError):
            validator.validate_config(config_partial_docs)

    def test_extra_wiki_documentation_allowed(self):
        """Test that extra wiki documentation (for non-existent alerts) is allowed."""
        config_extra_docs = {
            "groups": [
                {
                    "name": "alerting_rules",
                    "rules": [
                        {
                            "alert": "current_alert",
                            "expr": "metric > 1",
                            "annotations": {"summary": "Current Alert"}
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
                            "current_alert": {
                                "title": "Current Alert",
                                "content": "Documentation for current alert"
                            },
                            "legacy_alert": {  # No matching alert rule - should be allowed
                                "title": "Legacy Alert",
                                "content": "Documentation for legacy alert that was removed"
                            },
                            "future_alert": {  # No matching alert rule - should be allowed
                                "title": "Future Alert", 
                                "content": "Documentation for planned alert"
                            }
                        }
                    }
                }
            }
        }
        
        # Should pass validation (extra docs are OK)
        validator = ConfigValidator()
        validator.validate_config(config_extra_docs)  # Should not raise exception