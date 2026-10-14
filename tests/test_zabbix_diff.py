#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#
"""Tests for the pure-Python Zabbix diff engine (PM-6 + --dry-run)."""

import copy
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from promabbix.cli.generate_template import GenerateTemplateCommand
from promabbix.zabbix.diff import (
    HostDiff,
    TemplateDiff,
    diff_host,
    diff_template,
    normalize_host,
    normalize_template,
    should_import,
)

FIXTURES = Path(__file__).parent / "fixtures" / "zabbix_diff"
TPL = "templ_t"
KEY = "cpu[usage]"
LLD = "disk[ldd]"
PROTO = "disk[used,{#ZBX.ITEM.SUBKEY}]"


def trigger(expr: str = "last(/templ_t/cpu[usage])>90", name: str = "CPU high", **extra: Any) -> Dict[str, Any]:
    return {"uuid": "t" * 32, "expression": expr, "name": name, "priority": "WARNING", **extra}


def make_export(**overrides: Any) -> Dict[str, Any]:
    """A small but complete Zabbix 7 style export."""
    tpl: Dict[str, Any] = {
        "uuid": "a" * 32,
        "template": TPL,
        "name": "Template T",
        "groups": [{"name": "Templates"}],
        "items": [
            {"uuid": "b" * 32, "name": "cpu", "type": "HTTP_AGENT", "key": KEY, "delay": "30s",
             "value_type": "TEXT", "tags": [{"tag": "Application", "value": "Metrics"}],
             "triggers": [trigger()]},
            {"uuid": "c" * 32, "name": "mem", "key": "mem[usage]", "delay": "1m"},
        ],
        "discovery_rules": [
            {"uuid": "d" * 32, "name": LLD, "type": "DEPENDENT", "key": LLD, "lifetime": "2h",
             "item_prototypes": [
                 {"uuid": "e" * 32, "name": "disk used", "type": "DEPENDENT", "key": PROTO,
                  "master_item": {"key": KEY},
                  "preprocessing": [{"type": "JSONPATH", "parameters": ["$.a"]},
                                    {"type": "DISCARD_UNCHANGED_HEARTBEAT", "parameters": ["2m"]}],
                  "tags": [{"tag": "{#TAG0KEY}", "value": "{#TAG0VAL}"}],
                  "trigger_prototypes": [trigger("last(/templ_t/disk[used,{#ZBX.ITEM.SUBKEY}])>80", "Disk full")]},
             ]},
        ],
        "macros": [{"macro": "{$A}", "value": "1"}, {"macro": "{$B}", "value": "2"}],
        "tags": [{"tag": "Application", "value": "T"}, {"tag": "Env", "value": "prod"}],
    }
    export: Dict[str, Any] = {"version": "7.0", "date": "2025-01-01T00:00:00Z",
                              "template_groups": [{"uuid": "g" * 32, "name": "Templates"}],
                              "templates": [tpl]}
    export.update(overrides)
    return {"zabbix_export": export}


def tpl_of(export: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = export["zabbix_export"]["templates"][0]
    return result


def paths(entries: Any) -> list:
    """Entry paths relative to the root object (template / host)."""
    return [e.path.split(" > ", 1)[1] if " > " in e.path else e.path for e in entries]


def rel(path: str) -> str:
    return path.split(" > ", 1)[1] if " > " in path else path


# ---------------------------------------------------------------------------
# normalize_template
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_drops_volatile_fields_everywhere(self) -> None:
        norm = normalize_template(make_export())["zabbix_export"]
        assert "version" not in norm and "date" not in norm and "template_groups" not in norm
        assert "uuid" not in json.dumps(norm)
        assert "triggerid" not in json.dumps(norm)

    def test_does_not_mutate_input(self) -> None:
        export = make_export()
        before = copy.deepcopy(export)
        normalize_template(export)
        assert export == before

    def test_sorts_lists_by_stable_key(self) -> None:
        export = make_export()
        tpl = tpl_of(export)
        tpl["items"].reverse()
        tpl["macros"].reverse()
        tpl["tags"].reverse()
        norm = tpl_of(normalize_template(export))
        assert [i["key"] for i in norm["items"]] == sorted([KEY, "mem[usage]"])
        assert [m["macro"] for m in norm["macros"]] == ["{$A}", "{$B}"]
        assert [t["tag"] for t in norm["tags"]] == ["Application", "Env"]

    def test_triggers_sorted_by_name_and_expression(self) -> None:
        export = make_export()
        export["zabbix_export"]["triggers"] = [trigger("b>1", "Same"), trigger("a>1", "Same"), trigger("z", "A")]
        names = [(t["name"], t["expression"]) for t in normalize_template(export)["zabbix_export"]["triggers"]]
        assert names == [("A", "z"), ("CPU high", "last(/templ_t/cpu[usage])>90"), ("Same", "a>1"), ("Same", "b>1")]

    def test_preprocessing_order_is_preserved(self) -> None:
        proto = tpl_of(normalize_template(make_export()))["discovery_rules"][0]["item_prototypes"][0]
        assert [s["type"] for s in proto["preprocessing"]] == ["JSONPATH", "DISCARD_UNCHANGED_HEARTBEAT"]

    def test_nested_triggers_hoisted_to_export_layout(self) -> None:
        norm = normalize_template(make_export())["zabbix_export"]
        assert [t["name"] for t in norm["triggers"]] == ["CPU high"]
        rule = norm["templates"][0]["discovery_rules"][0]
        assert [t["name"] for t in rule["trigger_prototypes"]] == ["Disk full"]
        assert "trigger_prototypes" not in rule["item_prototypes"][0]
        assert "triggers" not in norm["templates"][0]["items"][0]

    def test_defaults_omission_missing_equals_default(self) -> None:
        a = make_export()
        b = make_export()
        # Export omits default valued fields; an explicit default must normalise away.
        tpl_of(b)["items"][1].update({"status": "ENABLED", "history": "90d", "value_type": "FLOAT", "type": "ZABBIX_PASSIVE"})
        tpl_of(b)["items"][0]["triggers"][0].update({"status": "ENABLED", "manual_close": "NO", "recovery_mode": "EXPRESSION"})
        assert normalize_template(a) == normalize_template(b)

    def test_non_default_value_is_kept(self) -> None:
        export = make_export()
        tpl_of(export)["items"][1]["status"] = "DISABLED"
        item = [i for i in tpl_of(normalize_template(export))["items"] if i["key"] == "mem[usage]"][0]
        assert item["status"] == "DISABLED"

    def test_empty_values_and_numbers_normalised(self) -> None:
        a = make_export()
        b = make_export()
        tpl_of(b)["items"][1].update({"description": "", "tags": [], "preprocessing": [], "headers": {}})
        tpl_of(b)["items"][1]["delay"] = "1m"
        tpl_of(a)["discovery_rules"][0]["item_prototypes"][0]["preprocessing"][0]["parameters"] = [5]
        tpl_of(b)["discovery_rules"][0]["item_prototypes"][0]["preprocessing"][0]["parameters"] = ["5"]
        assert normalize_template(a) == normalize_template(b)

    def test_dependent_delay_ignored(self) -> None:
        a = make_export()
        b = make_export()
        tpl_of(b)["discovery_rules"][0]["delay"] = "0"
        tpl_of(b)["discovery_rules"][0]["item_prototypes"][0]["delay"] = "0"
        assert normalize_template(a) == normalize_template(b)

    def test_lld_filter_conditions_sorted(self) -> None:
        export = make_export()
        rule = tpl_of(export)["discovery_rules"][0]
        rule["filter"] = {"evaltype": "AND_OR", "conditions": [
            {"macro": "{#B}", "value": "x", "formulaid": "B", "operator": "MATCHES_REGEX"},
            {"macro": "{#A}", "value": "y", "formulaid": "A"},
        ]}
        norm_rule = tpl_of(normalize_template(export))["discovery_rules"][0]
        assert [c["formulaid"] for c in norm_rule["filter"]["conditions"]] == ["A", "B"]
        assert "evaltype" not in norm_rule["filter"]  # default
        assert "operator" not in norm_rule["filter"]["conditions"][1]  # default

    @pytest.mark.parametrize("wrapped", [True, False])
    def test_accepts_bare_inner_object_and_json_text(self, wrapped: bool) -> None:
        export = make_export()
        inner = export["zabbix_export"]
        reference = normalize_template(export)
        assert normalize_template(inner) == reference
        assert normalize_template(json.dumps(export if wrapped else inner)) == reference
        assert normalize_template(json.dumps(inner).encode()) == reference

    @pytest.mark.parametrize("bad", [[1], 5, {"zabbix_export": [1]}])
    def test_rejects_garbage(self, bad: Any) -> None:
        with pytest.raises(TypeError):
            normalize_template(bad)

    def test_non_dict_children_are_skipped(self) -> None:
        export = make_export()
        tpl_of(export)["items"].append("garbage")
        assert len(tpl_of(normalize_template(export))["items"]) == 2


# ---------------------------------------------------------------------------
# diff_template
# ---------------------------------------------------------------------------

class TestDiffTemplate:
    def test_identical_has_no_changes(self) -> None:
        diff = diff_template(make_export(), make_export())
        assert isinstance(diff, TemplateDiff)
        assert not diff.has_changes
        assert diff.removals == 0
        assert (diff.added, diff.removed, diff.changed) == ([], [], [])
        assert diff.render() == f"Template {TPL}: no changes"

    def test_different_uuid_order_and_volatile_fields_is_no_change(self) -> None:
        live = make_export()
        desired = make_export(version="6.0", date="2030-01-01T00:00:00Z")
        for tpl in (tpl_of(live), tpl_of(desired)):
            tpl["items"].reverse()
            tpl["macros"].reverse()
        tpl_of(desired)["uuid"] = "0" * 32
        for it in tpl_of(desired)["items"]:
            it["uuid"] = "9" * 32
        tpl_of(desired)["discovery_rules"][0]["item_prototypes"][0]["trigger_prototypes"][0]["uuid"] = "8" * 32
        desired["zabbix_export"]["groups"] = [{"uuid": "7" * 32, "name": "Templates"}]  # Zabbix 6 spelling
        assert not diff_template(live, desired).has_changes

    def test_added_item(self) -> None:
        desired = make_export()
        tpl_of(desired)["items"].append({"name": "new", "key": "new[x]", "delay": "5m"})
        diff = diff_template(make_export(), desired)
        assert diff.has_changes and diff.removals == 0
        assert paths(diff.added) == ['item "new[x]"']
        assert diff.removed == [] and diff.changed == []
        assert "+ item \"new[x]\"" in diff.render()

    def test_removed_item_is_a_destructive_removal(self) -> None:
        desired = make_export()
        tpl_of(desired)["items"] = [i for i in tpl_of(desired)["items"] if i["key"] != "mem[usage]"]
        diff = diff_template(make_export(), desired)
        assert diff.has_changes
        assert diff.removals == 1
        assert paths(diff.removed) == ['item "mem[usage]"']
        text = diff.render()
        assert '!!! REMOVE item "mem[usage]"' in text
        assert "!!! 1 object(s) would be DELETED" in text

    def test_changed_trigger_expression(self) -> None:
        desired = make_export()
        tpl_of(desired)["items"][0]["triggers"][0]["expression"] = "last(/templ_t/cpu[usage])>95"
        diff = diff_template(make_export(), desired)
        assert diff.removals == 0
        assert diff.added == [] and diff.removed == []
        (change,) = diff.changed
        assert change.path == 'trigger "CPU high"'
        (fc,) = change.fields
        assert fc.field == "expression"
        assert fc.old.endswith(">90") and fc.new.endswith(">95")
        text = diff.render()
        assert '~ trigger "CPU high"' in text
        assert "- expression: " in text and "+ expression: " in text

    def test_changed_trigger_priority_and_description(self) -> None:
        desired = make_export()
        tpl_of(desired)["items"][0]["triggers"][0].update({"priority": "HIGH", "description": "Wiki: x"})
        (change,) = diff_template(make_export(), desired).changed
        assert {f.field: (f.old, f.new) for f in change.fields} == {
            "priority": ("WARNING", "HIGH"), "description": (None, "Wiki: x")}

    def test_changed_macro_value(self) -> None:
        desired = make_export()
        tpl_of(desired)["macros"][1]["value"] = "42"
        diff = diff_template(make_export(), desired)
        (change,) = diff.changed
        assert rel(change.path) == 'macro "{$B}"'
        assert change.fields[0].old == "2" and change.fields[0].new == "42"
        assert "~ macro \"{$B}\"" in diff.render()
        assert diff.removals == 0

    def test_added_and_removed_macro_and_tag_are_not_destructive(self) -> None:
        desired = make_export()
        tpl_of(desired)["macros"][0] = {"macro": "{$C}", "value": "3"}
        tpl_of(desired)["tags"][1]["value"] = "stage"
        diff = diff_template(make_export(), desired)
        assert 'macro "{$A}"' in paths(diff.removed)
        assert 'macro "{$C}"' in paths(diff.added)
        # tag "Env" changed value: tag name is the fallback identity, so it is a change, not remove + add
        assert [rel(c.path) for c in diff.changed] == ['tag "Env/stage"']
        assert diff.removals == 0
        assert '- macro "{$A}"' in diff.render()
        assert "!!!" not in diff.render()

    def test_changed_item_field(self) -> None:
        desired = make_export()
        tpl_of(desired)["items"][0]["delay"] = "60s"
        (change,) = diff_template(make_export(), desired).changed
        assert rel(change.path) == 'item "cpu[usage]"'
        assert (change.fields[0].old, change.fields[0].new) == ("30s", "60s")

    def test_removed_lld_prototype_counts_as_removal(self) -> None:
        desired = make_export()
        tpl_of(desired)["discovery_rules"][0]["item_prototypes"] = []
        diff = diff_template(make_export(), desired)
        # item prototype and its trigger prototype (nested in the export layout) both go
        assert diff.removals == 2
        assert paths(diff.removed) == [
            f'discovery_rule "{LLD}" > item_prototype "{PROTO}"',
            f'discovery_rule "{LLD}" > trigger_prototype "Disk full"',
        ]
        text = diff.render()
        assert f'!!! REMOVE discovery_rule "{LLD}" > item_prototype "{PROTO}"' in text
        assert "!!! 2 object(s) would be DELETED" in text

    def test_removed_trigger_prototype_only(self) -> None:
        desired = make_export()
        del tpl_of(desired)["discovery_rules"][0]["item_prototypes"][0]["trigger_prototypes"]
        diff = diff_template(make_export(), desired)
        assert diff.removals == 1
        assert paths(diff.removed) == [f'discovery_rule "{LLD}" > trigger_prototype "Disk full"']

    def test_removed_discovery_rule_counts_rule_and_children(self) -> None:
        desired = make_export()
        tpl_of(desired)["discovery_rules"] = []
        diff = diff_template(make_export(), desired)
        assert diff.removals == 3  # rule + item prototype + trigger prototype
        assert rel(diff.removed[0].path) == f'discovery_rule "{LLD}"'

    def test_removed_trigger_counts(self) -> None:
        desired = make_export()
        tpl_of(desired)["items"][0]["triggers"] = []
        diff = diff_template(make_export(), desired)
        assert diff.removals == 1
        assert paths(diff.removed) == ['trigger "CPU high"']

    def test_removed_graph_httptest_and_host_prototype_count(self) -> None:
        live = make_export(graphs=[{"name": "G", "graph_items": [{"item": {"host": TPL, "key": KEY}}]}])
        tpl_of(live)["httptests"] = [{"name": "web", "steps": [{"name": "s", "url": "http://x"}]}]
        tpl_of(live)["discovery_rules"][0]["host_prototypes"] = [{"host": "{#H}", "name": "{#H}"}]
        diff = diff_template(live, make_export())
        assert diff.removals == 3
        assert set(paths(diff.removed)) == {
            'graph "G"', 'httptest "web"', f'discovery_rule "{LLD}" > host_prototype "{{#H}}"'}

    def test_changed_graph_in_place(self) -> None:
        live = make_export(graphs=[{"name": "G", "width": "400"}])
        desired = make_export(graphs=[{"name": "G", "width": "900"}])  # 900 is the default
        (change,) = diff_template(live, desired).changed
        assert change.fields[0].new is None  # default omitted == unset

    def test_live_only_valuemaps_are_ignored(self) -> None:
        live = make_export()
        tpl_of(live)["valuemaps"] = [{"name": "VM", "mappings": [{"value": "0", "newvalue": "Down"}]}]
        diff = diff_template(live, make_export())
        assert not diff.has_changes and diff.removals == 0

    def test_live_only_linked_template_and_dashboard_are_destructive_removals(self) -> None:
        live = make_export()
        tpl_of(live)["templates"] = [{"name": "Linked by hand"}]
        tpl_of(live)["dashboards"] = [{"name": "Dash", "pages": [{"widgets": []}]}]
        diff = diff_template(live, make_export())
        assert diff.has_changes and diff.removals == 2
        assert paths(diff.removed) == ['linked_template "Linked by hand"', 'dashboard "Dash"']
        text = diff.render().splitlines()
        assert '!!! REMOVE linked_template "Linked by hand"' in text
        assert '!!! REMOVE dashboard "Dash"' in text

    def test_linked_template_and_dashboard_present_on_both_sides_are_no_change(self) -> None:
        live, desired = make_export(), make_export()
        for doc in (live, desired):
            tpl_of(doc)["templates"] = [{"name": "Linux by Zabbix agent"}]
            tpl_of(doc)["dashboards"] = [{"name": "Dash"}]
        assert not diff_template(live, desired).has_changes

    def test_desired_linked_template_is_added(self) -> None:
        desired = make_export()
        tpl_of(desired)["templates"] = [{"name": "Linux by Zabbix agent"}]
        diff = diff_template(make_export(), desired)
        assert paths(diff.added) == ['linked_template "Linux by Zabbix agent"']
        assert diff.removals == 0

    def test_other_live_templates_in_export_are_ignored(self) -> None:
        live = make_export()
        live["zabbix_export"]["templates"].append({"template": "other", "name": "other", "items": [{"key": "x"}]})
        assert not diff_template(live, make_export()).has_changes

    def test_live_none_everything_added_no_removals(self) -> None:
        diff = diff_template(None, make_export())
        assert diff.has_changes and diff.removals == 0
        assert diff.removed == [] and diff.changed == []
        kinds = sorted({a.kind for a in diff.added})
        assert kinds == ["discovery_rule", "group", "item", "item_prototype", "macro", "tag", "template",
                         "trigger", "trigger_prototype"]
        text = diff.render()
        assert text.splitlines()[0] == f"Template {TPL}: NEW, would be created"
        assert "2 item" in text and "2 macro" in text
        assert "REMOVE" not in text

    def test_live_none_with_nothing_desired(self) -> None:
        diff = diff_template(None, {"zabbix_export": {"templates": []}})
        assert diff.has_changes  # create (nothing) is still a create request
        assert diff.render().endswith("+ 0 object(s)")
        assert diff.title == "(none)"

    def test_json_text_inputs(self) -> None:
        diff = diff_template(json.dumps(make_export()), json.dumps(make_export()))
        assert not diff.has_changes

    def test_trigger_rename_with_same_name_pairs_as_change_not_remove_add(self) -> None:
        desired = make_export()
        tpl_of(desired)["items"][0]["triggers"][0]["expression"] = "last(/templ_t/cpu[usage])>1"
        diff = diff_template(make_export(), desired)
        assert diff.added == [] and diff.removed == []

    def test_two_triggers_same_name_different_expressions_are_not_paired(self) -> None:
        live = make_export()
        live["zabbix_export"]["triggers"] = [trigger("a>1", "Dup"), trigger("b>1", "Dup"), trigger("x>1", "Dup")]
        desired = make_export()
        desired["zabbix_export"]["triggers"] = [trigger("a>1", "Dup"), trigger("c>1", "Dup"), trigger("d>1", "Dup")]
        diff = diff_template(live, desired)
        assert (len(diff.added), len(diff.removed), len(diff.changed)) == (2, 2, 0)
        assert diff.removals == 2

    def test_unique_leftover_trigger_with_same_name_is_a_change(self) -> None:
        live = make_export()
        live["zabbix_export"]["triggers"] = [trigger("a>1", "Dup"), trigger("b>1", "Dup")]
        desired = make_export()
        desired["zabbix_export"]["triggers"] = [trigger("a>1", "Dup"), trigger("c>1", "Dup")]
        diff = diff_template(live, desired)
        assert (len(diff.added), len(diff.removed), len(diff.changed)) == (0, 0, 1)
        assert diff.changed[0].fields[0].field == "expression"

    def test_duplicate_identical_objects_are_matched_one_to_one(self) -> None:
        live = make_export(triggers=[trigger("a>1", "Dup")])
        desired = make_export(triggers=[trigger("a>1", "Dup"), trigger("a>1", "Dup")])
        diff = diff_template(live, desired)
        assert len(diff.added) == 1 and diff.removals == 0

    def test_long_values_render_as_unified_diff(self) -> None:
        script = "\n".join(f"line {i}" for i in range(30))
        live, desired = make_export(), make_export()
        tpl_of(live)["items"][1]["preprocessing"] = [{"type": "JAVASCRIPT", "parameters": [script]}]
        tpl_of(desired)["items"][1]["preprocessing"] = [
            {"type": "JAVASCRIPT", "parameters": [script.replace("line 15", "line fifteen")]}]
        text = diff_template(live, desired).render()
        assert "    ~ preprocessing:" in text
        assert any(line.startswith("      -") and "line 15" in line for line in text.splitlines())
        assert any(line.startswith("      +") and "line fifteen" in line for line in text.splitlines())

    def test_long_value_added_from_nothing_renders(self) -> None:
        desired = make_export()
        tpl_of(desired)["items"][1]["description"] = "x" * 150
        text = diff_template(make_export(), desired).render()
        assert "    ~ description:" in text and "+" + "x" * 150 in text

    def test_nested_ids_inside_plain_values_are_dropped(self) -> None:
        live, desired = make_export(), make_export()
        tpl_of(live)["items"][1]["master_item"] = {"key": KEY, "itemid": "77"}
        tpl_of(desired)["items"][1]["master_item"] = {"key": KEY}
        assert not diff_template(live, desired).has_changes

    def test_field_added_only_in_live_is_reported(self) -> None:
        live = make_export()
        tpl_of(live)["items"][1]["description"] = "manual note"
        (change,) = diff_template(live, make_export()).changed
        assert (change.fields[0].old, change.fields[0].new) == ("manual note", None)
        assert "+ description: <unset>" in diff_template(live, make_export()).render()

    def test_render_orders_removals_first_and_is_stable(self) -> None:
        live = make_export()
        desired = make_export()
        tpl_of(desired)["items"] = [i for i in tpl_of(desired)["items"] if i["key"] != "mem[usage]"]
        tpl_of(desired)["items"].append({"name": "new", "key": "new[x]"})
        tpl_of(desired)["macros"][0]["value"] = "100"
        text = diff_template(live, desired).render()
        assert text == "\n".join([
            f"Template {TPL}: CHANGES",
            '!!! REMOVE item "mem[usage]"',
            '~ macro "{$A}"',
            '    - value: "1"',
            '    + value: "100"',
            '+ item "new[x]"',
            "Summary: 1 added, 1 removed, 1 changed",
            "!!! 1 object(s) would be DELETED, history and data will be lost",
        ])
        assert diff_template(live, desired).render() == text  # deterministic


class TestShouldImport:
    def test_missing_live_means_import(self) -> None:
        assert should_import(None, make_export()) is True

    def test_identical_skips(self) -> None:
        assert should_import(make_export(), make_export()) is False

    def test_uuid_and_date_noise_skips(self) -> None:
        desired = make_export(date="2031-01-01T00:00:00Z")
        tpl_of(desired)["uuid"] = "1" * 32
        assert should_import(make_export(), desired) is False

    def test_any_change_imports(self) -> None:
        desired = make_export()
        tpl_of(desired)["macros"][0]["value"] = "9"
        assert should_import(make_export(), desired) is True

    def test_removal_imports(self) -> None:
        desired = make_export()
        tpl_of(desired)["items"].pop()
        assert should_import(make_export(), desired) is True


# ---------------------------------------------------------------------------
# Realistic fixture: promabbix rendering vs hand-made Zabbix export
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rendered_desired(tmp_path_factory: pytest.TempPathFactory) -> Dict[str, Any]:
    out = tmp_path_factory.mktemp("zbx_diff") / "template.json"
    rc = GenerateTemplateCommand().execute(str(FIXTURES / "service_alerts.yaml"), str(out),
                                           None, "prometheus_alert_rules_to_zbx_template.j2", False)
    assert rc == 0
    result: Dict[str, Any] = json.loads(out.read_text())
    return result


@pytest.fixture
def hand_made_live() -> Dict[str, Any]:
    result: Dict[str, Any] = json.loads((FIXTURES / "live_export_node_exporter.json").read_text())
    return result


def export_style(rendered: Dict[str, Any]) -> Dict[str, Any]:
    """What Zabbix 7 would hand back for ``rendered``: triggers on the rule, new uuids, other order."""
    live = copy.deepcopy(rendered)
    exp = live["zabbix_export"]
    exp["version"] = "7.0"
    exp["template_groups"] = exp.pop("groups")
    tpl = exp["templates"][0]
    tpl["uuid"] = "f" * 32
    tpl["vendor"] = {"name": "x", "version": "1"}
    for rule in tpl["discovery_rules"]:
        rule.pop("delay", None)
        rule["trigger_prototypes"] = []
        for proto in rule["item_prototypes"]:
            proto.pop("delay", None)
            rule["trigger_prototypes"] += proto.pop("trigger_prototypes")
        for obj in (rule, *rule["item_prototypes"], *rule["trigger_prototypes"]):
            obj["uuid"] = "e" * 32
    tpl["items"].reverse()
    tpl["discovery_rules"].reverse()
    return live


class TestRealisticTemplate:
    def test_rendered_template_has_expected_shape(self, rendered_desired: Dict[str, Any]) -> None:
        tpl = tpl_of(rendered_desired)
        assert tpl["template"] == "templ_module_promt_kube_node_exporter"
        assert len(tpl["items"]) == 2 and len(tpl["discovery_rules"]) == 2

    def test_export_style_copy_of_rendered_is_no_change(self, rendered_desired: Dict[str, Any]) -> None:
        live = export_style(rendered_desired)
        diff = diff_template(live, rendered_desired)
        assert not diff.has_changes, diff.render()
        assert should_import(live, rendered_desired) is False

    def test_rendered_twice_differs_only_in_volatile_fields(self, rendered_desired: Dict[str, Any]) -> None:
        other = copy.deepcopy(rendered_desired)
        other["zabbix_export"]["date"] = "1999-01-01T00:00:00Z"
        tpl_of(other)["uuid"] = "0" * 32
        for rule in tpl_of(other)["discovery_rules"]:
            rule["uuid"] = "0" * 32
        assert not diff_template(rendered_desired, other).has_changes

    def test_hand_made_live_export_diff(self, rendered_desired: Dict[str, Any],
                                        hand_made_live: Dict[str, Any]) -> None:
        diff = diff_template(hand_made_live, rendered_desired)
        assert diff.has_changes
        # live carries a legacy item + LLD rule (with prototype and trigger prototype) not in git
        assert diff.removals == 4
        removed = paths(diff.removed)
        assert 'item "node_disk[utilization,percent]"' in removed
        assert 'discovery_rule "node_disk[utilization,percent,ldd]"' in removed
        assert any("item_prototype" in p and "node_disk" in p for p in removed)
        assert any("trigger_prototype" in p and "Disk utilization" in p for p in removed)
        # drift: macro value and memory trigger expression
        changed = {c.path.split(" > ")[-1]: c for c in diff.changed}
        macro = changed['macro "{$NODE.MEM.UTIL.MAX}"']
        assert {f.field: (f.old, f.new) for f in macro.fields} == {"value": ("80", "85")}
        trig = [c for p, c in changed.items() if p.startswith('trigger_prototype "Memory')][0]
        by_field = {f.field: f for f in trig.fields}
        # exactly the intended drift: wiki description and wiki_page_tag (PM-4) match on both sides
        assert set(by_field) == {"expression"}
        assert by_field["expression"].old.endswith(">{$NODE.MEM.UTIL.MAX}")
        assert by_field["expression"].new.endswith(">={$NODE.MEM.UTIL.MAX}")
        # the CPU trigger, items and tags are the same in both
        assert not any('CPU' in p for p in changed)
        assert len(changed) == 2
        assert diff.added == []

    def test_wiki_description_and_tag_drift_is_reported(self, rendered_desired: Dict[str, Any],
                                                        hand_made_live: Dict[str, Any]) -> None:
        # live from before PM-4: no runbook description, no wiki_page_tag
        for rule in tpl_of(hand_made_live)["discovery_rules"]:
            for trig in rule["trigger_prototypes"]:
                if trig["name"].startswith("CPU"):
                    trig.pop("description", None)
                    trig["tags"] = [t for t in trig["tags"] if t["tag"] != "wiki_page_tag"]
        diff = diff_template(hand_made_live, rendered_desired)
        cpu = [c for c in diff.changed if c.path.endswith('trigger_prototype "CPU utilization on {#INSTANCE} '
                                                          'above {$NODE.CPU.UTIL.MAX}%"')]
        assert len(cpu) == 1
        by_field = {f.field: f for f in cpu[0].fields}
        assert by_field["description"].old is None
        assert by_field["description"].new == "Wiki: {$WIKI.TAG.URL}node_cpu_utilization_percent"
        assert "wiki_page_tag" in json.dumps(by_field["tags"].new)
        assert "wiki_page_tag" not in json.dumps(by_field["tags"].old)

    def test_hand_made_live_render(self, rendered_desired: Dict[str, Any], hand_made_live: Dict[str, Any]) -> None:
        text = diff_template(hand_made_live, rendered_desired).render()
        lines = text.splitlines()
        assert lines[0] == "Template templ_module_promt_kube_node_exporter: CHANGES"
        assert lines[1:5] == [
            '!!! REMOVE item "node_disk[utilization,percent]"',
            '!!! REMOVE discovery_rule "node_disk[utilization,percent,ldd]"',
            '!!! REMOVE discovery_rule "node_disk[utilization,percent,ldd]" > item_prototype '
            '"node_disk[utilization,percent,{#ZBX.ITEM.SUBKEY}]"',
            '!!! REMOVE discovery_rule "node_disk[utilization,percent,ldd]" > trigger_prototype '
            '"Disk utilization on {#INSTANCE}"',
        ]
        assert '~ macro "{$NODE.MEM.UTIL.MAX}"' in lines
        assert '    - value: "80"' in lines and '    + value: "85"' in lines
        assert lines[-1] == "!!! 4 object(s) would be DELETED, history and data will be lost"
        assert lines[-2].startswith("Summary: 0 added, 4 removed, 2")

    def test_new_template_against_none(self, rendered_desired: Dict[str, Any]) -> None:
        diff = diff_template(None, rendered_desired)
        assert diff.removals == 0
        assert len([a for a in diff.added if a.kind == "item"]) == 2
        assert len([a for a in diff.added if a.kind == "trigger_prototype"]) == 2


# ---------------------------------------------------------------------------
# Host diff
# ---------------------------------------------------------------------------

def live_host(**overrides: Any) -> Dict[str, Any]:
    """host.get style (selectGroups/selectParentTemplates/selectInterfaces/selectMacros/selectProxy)."""
    host: Dict[str, Any] = {
        "hostid": "10001", "host": "svc", "name": "Service", "status": "0", "description": "",
        "proxyid": "0",
        "groups": [{"groupid": "1", "name": "Linux"}, {"groupid": "2", "name": "Prod"}],
        "parentTemplates": [{"templateid": "5", "host": "templ_a", "name": "A"}],
        "interfaces": [{"interfaceid": "7", "type": "1", "main": "1", "useip": "1", "ip": "127.0.0.1",
                        "dns": "", "port": "10050", "details": []}],
        "macros": [{"hostmacroid": "3", "macro": "{$M}", "value": "1", "type": "0", "description": ""}],
    }
    host.update(overrides)
    return host


def desired_host(**overrides: Any) -> Dict[str, Any]:
    """promabbix ``zabbix.hosts[]`` + PM-5 defaults."""
    host: Dict[str, Any] = {
        "host_name": "svc", "visible_name": "Service", "host_groups": ["Prod", "Linux"],
        "link_templates": ["templ_a"], "status": "enabled", "description": "",
        "macros": [{"macro": "{$M}", "value": "1"}],
        "interfaces": [{"type": 1, "main": 1, "useip": 1, "ip": "127.0.0.1", "dns": "", "port": 10050}],
    }
    host.update(overrides)
    return host


class TestDiffHost:
    def test_noop_across_api_and_config_shapes(self) -> None:
        diff = diff_host(live_host(), desired_host())
        assert isinstance(diff, HostDiff)
        assert not diff.has_changes and diff.removals == 0
        assert diff.render() == "Host svc: no changes"

    def test_noop_with_partial_desired(self) -> None:
        # only groups are specified: everything else is left alone
        assert not diff_host(live_host(), {"host_name": "svc", "host_groups": ["Linux", "Prod"]}).has_changes

    def test_group_change(self) -> None:
        diff = diff_host(live_host(), desired_host(host_groups=["Linux", "Staging"]))
        assert paths(diff.added) == ['group "Staging"']
        assert paths(diff.removed) == ['group "Prod"']
        assert diff.removals == 0  # unlinking a group keeps the host and its history
        text = diff.render()
        assert '- group "Prod"' in text and '+ group "Staging"' in text
        assert text.splitlines()[0] == "Host svc: CHANGES"

    def test_interface_change(self) -> None:
        iface = {"type": 1, "main": 1, "useip": 1, "ip": "10.1.2.3", "dns": "", "port": 10050}
        diff = diff_host(live_host(), desired_host(interfaces=[iface]))
        (change,) = diff.changed
        assert rel(change.path) == 'interface "1/10.1.2.3/10050"'
        assert change.fields == (type(change.fields[0])("ip", "127.0.0.1", "10.1.2.3"),)
        assert '+ ip: "10.1.2.3"' in diff.render()

    def test_interface_added_and_removed(self) -> None:
        snmp = {"type": 2, "main": 1, "useip": 1, "ip": "10.0.0.1", "dns": "", "port": 161}
        diff = diff_host(live_host(), desired_host(interfaces=[snmp]))
        assert len(diff.added) == 1 and len(diff.removed) == 1

    def test_template_link_change(self) -> None:
        diff = diff_host(live_host(), desired_host(link_templates=["templ_b"]))
        assert paths(diff.added) == ['linked_template "templ_b"']
        assert paths(diff.removed) == ['linked_template "templ_a"']

    def test_macro_value_change_added_removed(self) -> None:
        diff = diff_host(live_host(), desired_host(macros=[{"macro": "{$M}", "value": "2"}, {"macro": "{$N}", "value": "x"}]))
        assert paths(diff.changed) == ['macro "{$M}"']
        assert paths(diff.added) == ['macro "{$N}"']
        diff = diff_host(live_host(), desired_host(macros=[]))
        assert paths(diff.removed) == ['macro "{$M}"']

    def test_secret_macro_value_not_compared(self) -> None:
        live = live_host(macros=[{"macro": "{$S}", "type": "1"}])
        desired = desired_host(macros=[{"macro": "{$S}", "value": "hunter2", "type": "1"}])
        assert not diff_host(live, desired).has_changes

    def test_status_and_description_and_visible_name(self) -> None:
        diff = diff_host(live_host(), desired_host(status="disabled", description="d", visible_name="New"))
        (change,) = diff.changed
        assert change.path == 'host "svc"'
        assert {f.field: (f.old, f.new) for f in change.fields} == {
            "status": ("enabled", "disabled"), "description": ("", "d"), "name": ("Service", "New")}
        assert '~ host "svc"' in diff.render()

    def test_status_numeric_and_default(self) -> None:
        assert not diff_host(live_host(status="1"), desired_host(status="disabled")).has_changes
        # PM-5 default: status enabled when omitted
        assert normalize_host({"host": "x"})["status"] == "enabled"

    def test_proxy_by_name(self) -> None:
        live = live_host(proxy={"proxyid": "9", "name": "proxy-1"})
        assert not diff_host(live, desired_host(proxy="proxy-1")).has_changes
        diff = diff_host(live, desired_host(proxy="proxy-2"))
        assert (diff.changed[0].fields[0].old, diff.changed[0].fields[0].new) == ("proxy-1", "proxy-2")

    def test_proxy_dropped_and_unresolved_id(self) -> None:
        live = live_host(proxy={"proxyid": "9", "host": "proxy-1"})
        assert diff_host(live, desired_host(proxy=None)).changed[0].fields[0].new == ""
        unresolved = diff_host(live_host(proxyid="9"), desired_host(proxy="proxy-1"))
        assert unresolved.changed[0].fields[0].old == "<id 9>"
        assert not diff_host(live_host(proxyid="0"), desired_host(proxy=None)).has_changes

    def test_live_none_would_create(self) -> None:
        diff = diff_host(None, desired_host())
        assert diff.has_changes and diff.removals == 0 and diff.removed == []
        text = diff.render()
        assert text.splitlines()[0] == "Host svc: NEW, would be created"
        assert "group" in text and "interface" in text

    def test_state_absent(self) -> None:
        diff = diff_host(live_host(), desired_host(state="absent"))
        assert diff.removals == 1
        assert '!!! REMOVE host "svc"' in diff.render()
        assert not diff_host(None, desired_host(state="absent")).has_changes

    def test_requires_a_host_name(self) -> None:
        with pytest.raises(ValueError):
            diff_host(live_host(), {"visible_name": "x"})

    def test_group_names_as_plain_strings_and_objects(self) -> None:
        assert not diff_host(live_host(), desired_host(host_groups=[{"name": "Linux"}, "Prod"])).has_changes

    def test_unmanaged_fields_are_ignored(self) -> None:
        live = live_host(inventory_mode="1", tags=[{"tag": "x"}])
        assert not diff_host(live, desired_host()).has_changes
