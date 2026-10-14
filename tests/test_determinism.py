#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2025 Wrike Inc.
#

"""
Deterministic UUID tests (PM-3).

Every uuid in a generated Zabbix template must be derived from the stable identity of the
object (template full name + object kind + object key), never from the render time or from
the position of the object in the input.
"""

import copy
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.template import (  # noqa: E402
    Render, STABLE_UUID_NAMESPACE, stable_uuid, to_uuid4,
)

TEMPLATES_DIR = Path(__file__).parent.parent / "src" / "promabbix" / "templates"
TEMPLATE_NAME = "prometheus_alert_rules_to_zbx_template.j2"
HEX32 = re.compile(r"^[0-9a-f]{32}$")


def make_config() -> Dict[str, Any]:
    """Realistic unified config: several recording rules, several alerts, one LLD filter."""
    return {
        "groups": [
            {"name": "recording_rules", "rules": [
                {"record": "node_cpu:utilization:percent",
                 "expr": "100 * (1 - avg by(instance)(rate(node_cpu_seconds_total{mode=\"idle\"}[5m])))"},
                {"record": "node_memory:utilization:percent",
                 "expr": "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)"},
                {"record": "node_filesystem:utilization:percent",
                 "expr": "100 * (1 - node_filesystem_avail_bytes / node_filesystem_size_bytes)"},
            ]},
            {"name": "alerting_rules", "rules": [
                {"alert": "node_cpu:utilization:percent",
                 "expr": "node_cpu:utilization:percent > {$NODE.CPU.WARN}",
                 "for": "5m",
                 "annotations": {"summary": "CPU high on {{$labels.instance}}",
                                 "description": "cpu {{$value}} on {{$labels.instance}}"},
                 "labels": {"__zbx_priority": "WARNING"}},
                {"alert": "node_memory:utilization:percent",
                 "expr": "node_memory:utilization:percent > {$NODE.MEM.WARN}",
                 "annotations": {"summary": "Memory high on {{$labels.instance}}",
                                 "description": "mem {{$value}}"},
                 "labels": {}},
                {"alert": "node_filesystem:utilization:percent",
                 "expr": "node_filesystem:utilization:percent > {$NODE.FS.WARN}",
                 "annotations": {"summary": "Filesystem {{$labels.mountpoint}} full on {{$labels.instance}}",
                                 "description": "fs {{$value}}"},
                 "labels": {}},
            ]},
        ],
        "zabbix": {
            "template_prefix": "templ_module_promt",
            "template": "sysops_service_node_exporter",
            "name": "Template Module Prometheus SysOps service Node Exporter",
            "lld_filters": {"filter": {"evaltype": "AND", "conditions": [
                {"formulaid": "A", "macro": "{#INSTANCE}", "value": "{$NODE.INSTANCE.LLD.MATCHES}"},
            ]}},
            "macros": [{"macro": "{$NODE.CPU.WARN}", "value": "90"}],
        },
        "prometheus": {"api": {"url": "{$PROMT.API.URL}/query"}},
    }


def render_text(config: Dict[str, Any]) -> str:
    return Render().render_file(TEMPLATES_DIR, TEMPLATE_NAME, copy.deepcopy(config))


def render_json(config: Dict[str, Any]) -> Dict[str, Any]:
    text = render_text(config)
    assert text, "template rendered to an empty string (jinja error)"
    parsed: Dict[str, Any] = json.loads(text)
    return parsed


def iter_uuids(template: Dict[str, Any]) -> Iterator[str]:
    """Yield every uuid in a rendered template, depth first (template, items, LLD, prototypes, triggers)."""
    yield template["uuid"]
    for item in template["items"]:
        yield item["uuid"]
    for rule in template["discovery_rules"]:
        yield rule["uuid"]
        for proto in rule["item_prototypes"]:
            yield proto["uuid"]
            for trigger in proto["trigger_prototypes"]:
                yield trigger["uuid"]


def get_template(rendered: Dict[str, Any]) -> Dict[str, Any]:
    template: Dict[str, Any] = rendered["zabbix_export"]["templates"][0]
    return template


def triggers_by_name(template: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        trigger["name"]: trigger
        for rule in template["discovery_rules"]
        for proto in rule["item_prototypes"]
        for trigger in proto["trigger_prototypes"]
    }


def objects_by_identity(template: Dict[str, Any]) -> Dict[str, str]:
    """Map a human readable object identity to its uuid, independent of output order."""
    result = {"template": template["uuid"]}
    for item in template["items"]:
        result["item:" + item["key"]] = item["uuid"]
    for rule in template["discovery_rules"]:
        result["lld:" + rule["key"]] = rule["uuid"]
        for proto in rule["item_prototypes"]:
            result["proto:" + proto["key"]] = proto["uuid"]
            for trigger in proto["trigger_prototypes"]:
                result["trigger:" + proto["key"] + "|" + trigger["name"]] = trigger["uuid"]
    return result


class TestStableUuidFilter:
    """Unit tests for the stable_uuid filter itself."""

    def test_same_input_same_output(self) -> None:
        assert stable_uuid("tpl", "item", "key") == stable_uuid("tpl", "item", "key")

    def test_output_is_32_lowercase_hex_without_dashes(self) -> None:
        assert HEX32.match(stable_uuid("tpl", "item", "key"))

    def test_output_is_zabbix_acceptable_uuid4(self) -> None:
        # Zabbix rejects non-UUIDv4 values with 'UUIDv4 is expected'.
        parsed = uuid.UUID(hex=stable_uuid("tpl", "trigger_prototype", "some alert"))
        assert parsed.version == 4
        assert parsed.variant == uuid.RFC_4122

    @pytest.mark.parametrize("a,b", [
        (("tpl", "item", "key"), ("tpl2", "item", "key")),
        (("tpl", "item", "key"), ("tpl", "item_prototype", "key")),
        (("tpl", "item", "key"), ("tpl", "item", "key2")),
        # field boundaries must matter: ("a|b", "c") != ("a", "b|c")
        (("tpl", "a|b", "c"), ("tpl", "a", "b|c")),
        (("t", "pl", "item"), ("tp", "l", "item")),
    ])
    def test_every_identity_component_matters(self, a: Any, b: Any) -> None:
        assert stable_uuid(*a) != stable_uuid(*b)

    def test_known_value_pins_namespace_and_algorithm(self) -> None:
        # Guards against accidental namespace / algorithm changes, which would re-key
        # every object of every template in production.
        assert stable_uuid("templ_module_promt_node_exporter", "item", "node_cpu[utilization,percent]") == \
            "8a5345a61b37491885224b6d1fc535bc"
        assert str(STABLE_UUID_NAMESPACE) == "31dd64a2-6386-5080-b4c6-9bb65261c0d4"

    def test_unicode_and_empty_keys(self) -> None:
        assert HEX32.match(stable_uuid("tpl", "trigger_prototype", "Zaplnění disku"))
        assert HEX32.match(stable_uuid("", "", ""))
        assert stable_uuid("tpl", "item", "") != stable_uuid("tpl", "item", " ")

    def test_non_string_input_is_coerced(self) -> None:
        assert stable_uuid("tpl", "item", 5) == stable_uuid("tpl", "item", "5")  # type: ignore[arg-type]

    def test_registered_as_jinja_filter(self) -> None:
        out = Render().render("{{ 'tpl' | stable_uuid('item', 'key') }}", {})
        assert out == stable_uuid("tpl", "item", "key")


class TestRenderDeterminism:
    """Rendering the same configuration must yield byte-identical output."""

    def test_two_renders_are_byte_identical(self) -> None:
        config = make_config()
        assert render_text(config) == render_text(config)

    def test_renders_identical_across_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The old implementation used the wall clock; freeze two different instants."""
        import promabbix.core.template as tpl
        config = make_config()
        monkeypatch.setattr(tpl.time, "time", lambda: 1_700_000_000.0)
        first = render_text(config)
        monkeypatch.setattr(tpl.time, "time", lambda: 1_800_000_000.123456)
        second = render_text(config)
        # only the (hour granular) export date may differ, never a uuid
        strip_date = re.compile(r'"date": "[^"]*"')
        assert strip_date.sub("", first) == strip_date.sub("", second)
        assert first != "" and len(re.findall(r'"uuid"', first)) > 10

    def test_uuids_identical_between_renders(self) -> None:
        config = make_config()
        a = list(iter_uuids(get_template(render_json(config))))
        b = list(iter_uuids(get_template(render_json(config))))
        assert a == b

    def test_expected_uuid_count(self) -> None:
        # 1 template + 3 items + 3 LLD rules + 3 item prototypes + 3 trigger prototypes
        assert len(list(iter_uuids(get_template(render_json(make_config()))))) == 13

    def test_all_uuids_are_32_hex_and_unique(self) -> None:
        uuids = list(iter_uuids(get_template(render_json(make_config()))))
        assert all(HEX32.match(u) for u in uuids), uuids
        assert len(set(uuids)) == len(uuids)

    def test_all_uuids_are_zabbix_valid_uuid4(self) -> None:
        for u in iter_uuids(get_template(render_json(make_config()))):
            parsed = uuid.UUID(hex=u)
            assert parsed.version == 4 and parsed.variant == uuid.RFC_4122

    def test_template_uuid_is_derived_from_full_name_as_before(self) -> None:
        """The template uuid was already deterministic; it must stay compatible with live Zabbix."""
        config = make_config()
        template = get_template(render_json(config))
        assert template["template"] == "templ_module_promt_sysops_service_node_exporter"
        assert template["uuid"] == to_uuid4(template["template"]).replace("-", "")

    def test_template_name_default_prefix_consistent_with_uuid(self) -> None:
        config = make_config()
        del config["zabbix"]["template_prefix"]
        template = get_template(render_json(config))
        assert template["template"] == "templ_module_promt_kube_sysops_service_node_exporter"
        assert template["uuid"] == to_uuid4(template["template"]).replace("-", "")

    def test_object_uuids_match_documented_identity(self) -> None:
        """uuid = stable_uuid(template full name, kind, key) with the keys Zabbix itself uses."""
        template = get_template(render_json(make_config()))
        full = template["template"]
        item = template["items"][0]
        assert item["key"] == "node_cpu[utilization,percent]"
        assert item["uuid"] == stable_uuid(full, "item", item["key"])
        rule = [r for r in template["discovery_rules"] if r["key"] == "node_cpu[utilization,percent,ldd]"][0]
        assert rule["uuid"] == stable_uuid(full, "discovery_rule", rule["key"])
        proto = rule["item_prototypes"][0]
        assert proto["key"] == "node_cpu[utilization,percent,{#ZBX.ITEM.SUBKEY}]"
        assert proto["uuid"] == stable_uuid(full, "item_prototype", proto["key"])
        trigger = proto["trigger_prototypes"][0]
        assert trigger["uuid"] == stable_uuid(full, "trigger_prototype", proto["key"] + "|" + trigger["name"])


class TestIdentityBasedUuids:
    """A uuid must follow the object's identity, not its position or its neighbours."""

    def test_different_alert_names_give_different_uuids(self) -> None:
        template = get_template(render_json(make_config()))
        uuids = [t["uuid"] for t in triggers_by_name(template).values()]
        assert len(uuids) == 3 and len(set(uuids)) == 3

    def test_renaming_alert_summary_changes_only_that_trigger_uuid(self) -> None:
        base = make_config()
        renamed = make_config()
        renamed["groups"][1]["rules"][1]["annotations"]["summary"] = "Memory pressure on {{$labels.instance}}"
        before = objects_by_identity(get_template(render_json(base)))
        after = objects_by_identity(get_template(render_json(renamed)))
        changed = {k for k in before if k in after and before[k] != after[k]}
        assert changed == set()  # only the trigger's own identity changed; every other object is untouched
        removed = set(before) - set(after)
        added = set(after) - set(before)
        assert len(removed) == 1 and len(added) == 1
        assert next(iter(removed)).startswith("trigger:node_memory[utilization,percent,{#ZBX.ITEM.SUBKEY}]|Memory high")

    def test_reordering_alerts_does_not_change_object_uuids(self) -> None:
        base = make_config()
        shuffled = make_config()
        shuffled["groups"][1]["rules"].reverse()
        assert objects_by_identity(get_template(render_json(base))) == \
            objects_by_identity(get_template(render_json(shuffled)))

    def test_reordering_recording_rules_does_not_change_object_uuids(self) -> None:
        base = make_config()
        shuffled = make_config()
        shuffled["groups"][0]["rules"].reverse()
        shuffled["groups"][1]["rules"] = shuffled["groups"][1]["rules"][1:] + shuffled["groups"][1]["rules"][:1]
        assert objects_by_identity(get_template(render_json(base))) == \
            objects_by_identity(get_template(render_json(shuffled)))

    def test_adding_an_alert_does_not_change_existing_uuids(self) -> None:
        base = make_config()
        extended = make_config()
        extended["groups"][0]["rules"].append(
            {"record": "node_load:avg:five", "expr": "node_load5"})
        extended["groups"][1]["rules"].insert(0, {
            "alert": "node_load:avg:five", "expr": "node_load:avg:five > {$NODE.LOAD.WARN}",
            "annotations": {"summary": "Load high", "description": "load {{$value}}"}, "labels": {}})
        before = objects_by_identity(get_template(render_json(base)))
        after = objects_by_identity(get_template(render_json(extended)))
        assert len(after) == len(before) + 4  # item + lld + prototype + trigger
        assert all(after[k] == v for k, v in before.items())

    def test_removing_an_alert_does_not_change_remaining_uuids(self) -> None:
        base = make_config()
        reduced = make_config()
        del reduced["groups"][1]["rules"][0]
        before = objects_by_identity(get_template(render_json(base)))
        after = objects_by_identity(get_template(render_json(reduced)))
        assert all(before[k] == v for k, v in after.items())

    def test_different_template_gives_different_uuids_for_same_objects(self) -> None:
        other = make_config()
        other["zabbix"]["template"] = "sysops_service_other"
        a = list(iter_uuids(get_template(render_json(make_config()))))
        b = list(iter_uuids(get_template(render_json(other))))
        assert set(a).isdisjoint(b)

    def test_different_prefix_gives_different_uuids(self) -> None:
        other = make_config()
        other["zabbix"]["template_prefix"] = "templ_module_promt_kube"
        a = list(iter_uuids(get_template(render_json(make_config()))))
        b = list(iter_uuids(get_template(render_json(other))))
        assert set(a).isdisjoint(b)

    def test_unrelated_config_changes_do_not_change_uuids(self) -> None:
        """Macros, tags, URL, expression or description edits must not re-key objects."""
        base = make_config()
        edited = make_config()
        edited["zabbix"]["macros"].append({"macro": "{$NEW}", "value": "1"})
        edited["prometheus"]["api"]["url"] = "http://other:9090/api/v1/query"
        edited["groups"][0]["rules"][0]["expr"] = "vector(1)"
        edited["groups"][1]["rules"][0]["annotations"]["description"] = "different"
        edited["groups"][1]["rules"][0]["labels"]["__zbx_priority"] = "HIGH"
        assert objects_by_identity(get_template(render_json(base))) == \
            objects_by_identity(get_template(render_json(edited)))

    def test_duplicate_trigger_names_still_get_unique_uuids(self) -> None:
        """Two alerts for the same record with the same summary must not collide in Zabbix."""
        config = make_config()
        dup = copy.deepcopy(config["groups"][1]["rules"][0])
        dup["expr"] = "node_cpu:utilization:percent > 99"
        config["groups"][1]["rules"].append(dup)
        template = get_template(render_json(config))
        uuids = list(iter_uuids(template))
        assert len(uuids) == 14
        assert len(set(uuids)) == len(uuids)
        assert all(HEX32.match(u) for u in uuids)
        # and it is still deterministic
        assert uuids == list(iter_uuids(get_template(render_json(config))))

    def test_alert_without_recording_rule_generates_nothing_and_does_not_shift_uuids(self) -> None:
        base = make_config()
        orphan = make_config()
        orphan["groups"][1]["rules"].insert(0, {
            "alert": "does:not:exist", "expr": "does:not:exist > 1",
            "annotations": {"summary": "x", "description": "y"}, "labels": {}})
        assert objects_by_identity(get_template(render_json(base))) == \
            objects_by_identity(get_template(render_json(orphan)))

    def test_recording_rule_without_alert_is_not_emitted(self) -> None:
        config = make_config()
        config["groups"][0]["rules"].append({"record": "unused:metric:x", "expr": "vector(1)"})
        template = get_template(render_json(config))
        assert len(template["items"]) == 3
        assert len(list(iter_uuids(template))) == 13

    def test_uuid_set_has_no_overlap_across_object_kinds(self) -> None:
        template = get_template(render_json(make_config()))
        by_kind: List[List[str]] = [
            [i["uuid"] for i in template["items"]],
            [r["uuid"] for r in template["discovery_rules"]],
            [p["uuid"] for r in template["discovery_rules"] for p in r["item_prototypes"]],
            [t["uuid"] for t in triggers_by_name(template).values()],
        ]
        flat = [u for group in by_kind for u in group]
        assert len(flat) == len(set(flat)) == 12
