#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2025 Wrike Inc.
#

"""
Wiki / runbook defaults (PM-4).

Expected values are hand-written from the oapw v7 template
(templates/prometheus_alert_rules_to_zbx_template_v7.j2):
  :108  "wiki_page_tag": (a_rule.alert | replace(':', '_'))      default trigger tag
  :143-151  __zbx_trigger_description set  -> lookup_template(...)
            else                           -> "Wiki: {$WIKI.TAG.URL}" + alert_rule.tags.wiki_page_tag
Tag precedence in v7 (low to high): default tags < zabbix.labels (common) < alert labels.
"""

import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.template import Render  # noqa: E402

TEMPLATES_DIR = Path(__file__).parent.parent / "src" / "promabbix" / "templates"
TEMPLATE_NAME = "prometheus_alert_rules_to_zbx_template.j2"
TEMPLATE_FULL_NAME = "templ_module_promt_sysops_service_node_exporter"
PROTO_SUFFIX = "[{#ZBX.ITEM.SUBKEY}]"


def make_config(alert_labels: Optional[Dict[str, Any]] = None,
                zabbix_labels: Optional[Dict[str, Any]] = None,
                alert: str = "node_cpu:utilization:percent") -> Dict[str, Any]:
    record = alert
    config: Dict[str, Any] = {
        "groups": [
            {"name": "recording_rules", "rules": [
                {"record": record, "expr": "100 * avg(rate(node_cpu_seconds_total[5m]))"},
            ]},
            {"name": "alerting_rules", "rules": [
                {"alert": alert,
                 "expr": record + " > {$NODE.CPU.WARN}",
                 "for": "5m",
                 "annotations": {"summary": "CPU high on {{$labels.instance}}",
                                 "description": "cpu {{$value}}"},
                 "labels": dict(alert_labels or {})},
            ]},
        ],
        "zabbix": {
            "template_prefix": "templ_module_promt",
            "template": "sysops_service_node_exporter",
            "name": "Template Module Prometheus SysOps service Node Exporter",
        },
        "prometheus": {"api": {"url": "{$PROMT.API.URL}/query"}},
    }
    if zabbix_labels is not None:
        config["zabbix"]["labels"] = dict(zabbix_labels)
    return config


def render_triggers(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = Render().render_file(TEMPLATES_DIR, TEMPLATE_NAME, copy.deepcopy(config))
    assert text, "template rendered to an empty string (jinja error)"
    template = json.loads(text)["zabbix_export"]["templates"][0]
    return [
        trigger
        for rule in template["discovery_rules"]
        for proto in rule["item_prototypes"]
        for trigger in proto["trigger_prototypes"]
    ]


def render_trigger(config: Dict[str, Any]) -> Dict[str, Any]:
    triggers = render_triggers(config)
    assert len(triggers) == 1
    return triggers[0]


def tags_of(trigger: Dict[str, Any]) -> Dict[str, str]:
    return {t["tag"]: t["value"] for t in trigger["tags"]}


class TestDefaultWikiPageTag:
    def test_default_tag_present(self) -> None:
        assert "wiki_page_tag" in tags_of(render_trigger(make_config()))

    def test_default_tag_is_alert_name_with_colons_replaced(self) -> None:
        tags = tags_of(render_trigger(make_config(alert="node_cpu:utilization:percent")))
        assert tags["wiki_page_tag"] == "node_cpu_utilization_percent"
        assert ":" not in tags["wiki_page_tag"]

    def test_default_tag_equals_alert_tag(self) -> None:
        tags = tags_of(render_trigger(make_config()))
        assert tags["alert"] == tags["wiki_page_tag"]

    def test_alert_name_without_colon_is_unchanged(self) -> None:
        tags = tags_of(render_trigger(make_config(alert="simple_alert")))
        assert tags["wiki_page_tag"] == "simple_alert"

    def test_single_colon(self) -> None:
        assert tags_of(render_trigger(make_config(alert="a:b")))["wiki_page_tag"] == "a_b"

    def test_explicit_alert_label_wins(self) -> None:
        tags = tags_of(render_trigger(make_config(alert_labels={"wiki_page_tag": "custom_runbook"})))
        assert tags["wiki_page_tag"] == "custom_runbook"
        assert tags["alert"] == "node_cpu_utilization_percent"

    def test_explicit_service_level_label_wins(self) -> None:
        """Like service/node_exporter: zabbix.labels.wiki_page_tag applies to every trigger."""
        tags = tags_of(render_trigger(make_config(zabbix_labels={"wiki_page_tag": "node_exporter"})))
        assert tags["wiki_page_tag"] == "node_exporter"

    def test_alert_label_beats_service_level_label(self) -> None:
        trigger = render_trigger(make_config(alert_labels={"wiki_page_tag": "alert_level"},
                                             zabbix_labels={"wiki_page_tag": "service_level"}))
        assert tags_of(trigger)["wiki_page_tag"] == "alert_level"

    def test_exactly_one_wiki_page_tag_entry(self) -> None:
        trigger = render_trigger(make_config(alert_labels={"wiki_page_tag": "x"}))
        assert [t["tag"] for t in trigger["tags"]].count("wiki_page_tag") == 1

    def test_each_alert_gets_its_own_default(self) -> None:
        config = make_config()
        config["groups"][0]["rules"].append({"record": "node_mem:used:percent", "expr": "vector(1)"})
        config["groups"][1]["rules"].append({
            "alert": "node_mem:used:percent", "expr": "node_mem:used:percent > 1",
            "annotations": {"summary": "Mem", "description": "m"}, "labels": {}})
        tags = sorted(tags_of(t)["wiki_page_tag"] for t in render_triggers(config))
        assert tags == ["node_cpu_utilization_percent", "node_mem_used_percent"]

    def test_tags_are_sorted_by_tag_name(self) -> None:
        trigger = render_trigger(make_config(zabbix_labels={"__event_recovery_notify": "1"}))
        names = [t["tag"] for t in trigger["tags"]]
        assert names == sorted(names)
        assert names == ["__event_delay", "__event_recovery_notify", "alert", "wiki_page_tag"]


class TestDefaultTriggerDescription:
    def test_default_description_generated(self) -> None:
        trigger = render_trigger(make_config())
        assert trigger["description"] == "Wiki: {$WIKI.TAG.URL}node_cpu_utilization_percent"

    def test_wiki_url_macro_is_left_for_zabbix_to_expand(self) -> None:
        assert "{$WIKI.TAG.URL}" in render_trigger(make_config())["description"]

    def test_default_description_follows_explicit_wiki_page_tag(self) -> None:
        trigger = render_trigger(make_config(alert_labels={"wiki_page_tag": "custom_runbook"}))
        assert trigger["description"] == "Wiki: {$WIKI.TAG.URL}custom_runbook"

    def test_default_description_follows_service_level_wiki_page_tag(self) -> None:
        trigger = render_trigger(make_config(zabbix_labels={"wiki_page_tag": "node_exporter"}))
        assert trigger["description"] == "Wiki: {$WIKI.TAG.URL}node_exporter"

    def test_explicit_trigger_description_wins(self) -> None:
        trigger = render_trigger(make_config(alert_labels={"__zbx_trigger_description": "Runbook: see wiki"}))
        assert trigger["description"] == "Runbook: see wiki"

    def test_explicit_description_is_rendered_with_item_context(self) -> None:
        trigger = render_trigger(make_config(
            alert_labels={"__zbx_trigger_description": "item {{item_full_key}} expr {{trigger_expression}}"}))
        key = "/" + TEMPLATE_FULL_NAME + "/node_cpu[utilization,percent" + ",{#ZBX.ITEM.SUBKEY}]"
        assert trigger["description"].startswith("item " + key + " expr ")
        assert "last(" + key + ")" in trigger["description"]

    def test_explicit_description_from_service_level_labels(self) -> None:
        trigger = render_trigger(make_config(zabbix_labels={"__zbx_trigger_description": "common text"}))
        assert trigger["description"] == "common text"

    def test_alert_level_description_beats_service_level(self) -> None:
        trigger = render_trigger(make_config(alert_labels={"__zbx_trigger_description": "alert text"},
                                             zabbix_labels={"__zbx_trigger_description": "common text"}))
        assert trigger["description"] == "alert text"

    def test_empty_explicit_description_falls_back_to_default(self) -> None:
        """v7 tests truthiness of __zbx_trigger_description, so an empty string means 'not set'."""
        trigger = render_trigger(make_config(alert_labels={"__zbx_trigger_description": ""}))
        assert trigger["description"] == "Wiki: {$WIKI.TAG.URL}node_cpu_utilization_percent"

    def test_explicit_description_does_not_remove_wiki_tag(self) -> None:
        trigger = render_trigger(make_config(alert_labels={"__zbx_trigger_description": "x"}))
        assert tags_of(trigger)["wiki_page_tag"] == "node_cpu_utilization_percent"

    def test_zbx_prefixed_label_is_not_leaked_into_tags(self) -> None:
        trigger = render_trigger(make_config(alert_labels={"__zbx_trigger_description": "x"}))
        assert "__zbx_trigger_description" not in tags_of(trigger)


class TestGoldenAgainstOapwV7:
    """
    One realistic fixture; expected tags/descriptions were derived by reading the oapw v7
    template and cross-checked by rendering the same data through both templates.
    """

    @pytest.fixture
    def triggers(self) -> Dict[str, Dict[str, Any]]:
        config = make_config(
            alert_labels={"wiki_page_tag": "cpu_runbook", "__zbx_priority": "WARNING"},
            zabbix_labels={"__event_recovery_notify": "1", "slack_alarm_channel_name": "alerts"},
        )
        config["groups"][0]["rules"] += [
            {"record": "node_memory:utilization:percent", "expr": "vector(1)"},
            {"record": "node_disk:io:percent", "expr": "vector(2)"},
        ]
        config["groups"][1]["rules"] += [
            {"alert": "node_memory:utilization:percent",
             "expr": "node_memory:utilization:percent > {$NODE.MEM.WARN}",
             "annotations": {"summary": "Memory high on {{$labels.instance}}", "description": "m {{$value}}"},
             "labels": {"owner": "team-x"}},
            {"alert": "node_disk:io:percent",
             "expr": "node_disk:io:percent > {$NODE.DISK.WARN}",
             "annotations": {"summary": "Disk busy on {{$labels.instance}}", "description": "d {{$value}}"},
             "labels": {"__zbx_trigger_description": "Disk runbook for {{$labels.instance}}"}},
        ]
        return {t["name"]: t for t in render_triggers(config)}

    def test_trigger_count(self, triggers: Dict[str, Dict[str, Any]]) -> None:
        assert sorted(triggers) == [
            "CPU high on {#INSTANCE}", "Disk busy on {#INSTANCE}", "Memory high on {#INSTANCE}"]

    def test_cpu_alert_explicit_tag(self, triggers: Dict[str, Dict[str, Any]]) -> None:
        t = triggers["CPU high on {#INSTANCE}"]
        assert t["tags"] == [
            {"tag": "__event_delay", "value": "5m"},
            {"tag": "__event_recovery_notify", "value": "1"},
            {"tag": "alert", "value": "node_cpu_utilization_percent"},
            {"tag": "slack_alarm_channel_name", "value": "alerts"},
            {"tag": "wiki_page_tag", "value": "cpu_runbook"},
        ]
        assert t["description"] == "Wiki: {$WIKI.TAG.URL}cpu_runbook"
        assert t["priority"] == "WARNING"

    def test_memory_alert_defaults(self, triggers: Dict[str, Dict[str, Any]]) -> None:
        t = triggers["Memory high on {#INSTANCE}"]
        assert t["tags"] == [
            {"tag": "__event_recovery_notify", "value": "1"},
            {"tag": "alert", "value": "node_memory_utilization_percent"},
            {"tag": "owner", "value": "team-x"},
            {"tag": "slack_alarm_channel_name", "value": "alerts"},
            {"tag": "wiki_page_tag", "value": "node_memory_utilization_percent"},
        ]
        assert t["description"] == "Wiki: {$WIKI.TAG.URL}node_memory_utilization_percent"

    def test_disk_alert_explicit_description(self, triggers: Dict[str, Dict[str, Any]]) -> None:
        t = triggers["Disk busy on {#INSTANCE}"]
        assert t["description"] == "Disk runbook for {#INSTANCE}"
        assert {"tag": "wiki_page_tag", "value": "node_disk_io_percent"} in t["tags"]
