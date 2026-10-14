#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

"""Tests for directory input: common/ merge, groups normalisation, all *_alerts.yaml consumed."""

import copy
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.data_utils import deep_merge_append  # noqa: E402
from promabbix.core.loader import (  # noqa: E402
    ServiceLoadError, list_yaml_files, load_service, normalize_groups,
)
from promabbix.core.migration import (  # noqa: E402
    _find_alerts_files, migrate_legacy_service,
)
from promabbix.core import migration  # noqa: E402


def write_yaml(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def alerts_file(path: Path, records=(), alerts=(), split_groups=False) -> Path:
    """Write an alerts file in the real layout: recording_rules group + alerting_rules group."""
    rec = [{"record": r, "expr": f"sum({r}_total)"} for r in records]
    alr = [{"alert": a, "expr": f"{a} > 1", "annotations": {"summary": a}} for a in alerts]
    groups = []
    if rec or split_groups:
        groups.append({"name": "recording_rules", "rules": rec})
    if alr or split_groups:
        groups.append({"name": "alerting_rules", "rules": alr})
    return write_yaml(path, {"groups": groups})


def rule_names(config, group):
    g = next(g for g in config["groups"] if g["name"] == group)
    return [r.get("record") or r.get("alert") for r in g["rules"]]


@pytest.fixture
def svc(tmp_path):
    """A service directory with two alert files and a zabbix_vars file, plus an empty common dir."""
    service = tmp_path / "service" / "demo"
    common = tmp_path / "common"
    common.mkdir()
    alerts_file(service / "cpu_alerts.yaml", records=["cpu:a", "cpu:b"], alerts=["cpu_alert"])
    alerts_file(service / "oom_alerts.yaml", records=["oom:a"], alerts=["oom_alert_1", "oom_alert_2"])
    write_yaml(service / "zabbix_vars.yaml", {"zabbix": {"template": "demo", "name": "Demo"}})
    return service, common


class TestDeepMergeAppend:
    def test_scalar_later_wins(self):
        assert deep_merge_append({"a": 1, "b": 2}, {"a": 9}) == {"a": 9, "b": 2}

    def test_nested_dicts_merged(self):
        base = {"zabbix": {"labels": {"x": "1", "y": "2"}, "name": "base"}}
        over = {"zabbix": {"labels": {"y": "OVR", "z": "3"}}}
        assert deep_merge_append(base, over) == {
            "zabbix": {"labels": {"x": "1", "y": "OVR", "z": "3"}, "name": "base"}}

    def test_lists_appended_in_order(self):
        assert deep_merge_append({"l": [1, 2]}, {"l": [3]}) == {"l": [1, 2, 3]}

    def test_lists_not_deduplicated(self):
        # yq '*+' appends blindly; duplicates are the caller's business
        assert deep_merge_append({"l": [1]}, {"l": [1]}) == {"l": [1, 1]}

    def test_type_change_override_wins(self):
        assert deep_merge_append({"a": {"x": 1}}, {"a": "str"}) == {"a": "str"}
        assert deep_merge_append({"a": [1]}, {"a": {"x": 1}}) == {"a": {"x": 1}}
        assert deep_merge_append({"a": "s"}, {"a": [1]}) == {"a": [1]}

    def test_null_override_wins(self):
        assert deep_merge_append({"a": {"x": 1}}, {"a": None}) == {"a": None}

    def test_inputs_not_mutated_and_result_not_aliased(self):
        base = {"l": [{"k": 1}], "d": {"a": 1}}
        over = {"l": [{"k": 2}], "d": {"b": 2}}
        base_copy, over_copy = copy.deepcopy(base), copy.deepcopy(over)
        result = deep_merge_append(base, over)
        result["l"][0]["k"] = "changed"
        result["d"]["a"] = "changed"
        assert base == base_copy and over == over_copy


class TestNormalizeGroups:
    def test_collapses_many_groups_to_exactly_two(self):
        cfg = {"groups": [
            {"name": "recording_rules", "rules": [{"record": "r1", "expr": "1"}]},
            {"name": "alerting_rules", "rules": [{"alert": "a1", "expr": "1"}]},
            {"name": "recording_rules", "rules": [{"record": "r2", "expr": "1"}]},
            {"name": "alerting_rules", "rules": [{"alert": "a2", "expr": "1"}, {"alert": "a3", "expr": "1"}]},
            {"name": "recording_rules", "rules": [{"record": "r3", "expr": "1"}]},
        ]}
        normalize_groups(cfg)
        assert [g["name"] for g in cfg["groups"]] == ["recording_rules", "alerting_rules"]
        assert rule_names(cfg, "recording_rules") == ["r1", "r2", "r3"]
        assert rule_names(cfg, "alerting_rules") == ["a1", "a2", "a3"]

    def test_recording_group_always_first_even_when_input_is_alerting_first(self):
        cfg = {"groups": [
            {"name": "alerting_rules", "rules": [{"alert": "a1", "expr": "1"}]},
            {"name": "recording_rules", "rules": [{"record": "r1", "expr": "1"}]},
        ]}
        normalize_groups(cfg)
        assert [g["name"] for g in cfg["groups"]] == ["recording_rules", "alerting_rules"]

    def test_only_alerting_rules_still_yields_two_groups_with_empty_recording(self):
        cfg = {"groups": [{"name": "alerting_rules", "rules": [{"alert": "a1", "expr": "1"}]}]}
        normalize_groups(cfg)
        assert cfg["groups"] == [
            {"name": "recording_rules", "rules": []},
            {"name": "alerting_rules", "rules": [{"alert": "a1", "expr": "1"}]},
        ]

    def test_rules_none_treated_as_empty(self):
        cfg = {"groups": [{"name": "recording_rules", "rules": None},
                          {"name": "alerting_rules", "rules": [{"alert": "a", "expr": "1"}]}]}
        normalize_groups(cfg)
        assert rule_names(cfg, "recording_rules") == []

    def test_unknown_group_kept_after_canonical_two_so_schema_can_reject_it(self):
        cfg = {"groups": [{"name": "alerting_rules", "rules": [{"alert": "a", "expr": "1"}]},
                          {"name": "bogus", "rules": []}]}
        normalize_groups(cfg)
        assert [g["name"] for g in cfg["groups"]] == ["recording_rules", "alerting_rules", "bogus"]

    @pytest.mark.parametrize("cfg", [{}, {"groups": []}, {"groups": None}, {"groups": "x"}])
    def test_missing_groups_is_clear_error(self, cfg):
        with pytest.raises(ServiceLoadError, match="No 'groups' found"):
            normalize_groups(cfg)

    def test_groups_without_any_rules_is_error(self):
        cfg = {"groups": [{"name": "recording_rules", "rules": []},
                          {"name": "alerting_rules", "rules": []}]}
        with pytest.raises(ServiceLoadError, match="No rules found"):
            normalize_groups(cfg)

    def test_non_mapping_group_is_error(self):
        with pytest.raises(ServiceLoadError, match="Invalid group entry"):
            normalize_groups({"groups": ["oops"]})

    def test_non_list_rules_is_error(self):
        with pytest.raises(ServiceLoadError, match="'rules' must be a list"):
            normalize_groups({"groups": [{"name": "alerting_rules", "rules": {"a": 1}}]})


class TestLoadServiceMultipleAlertFiles:
    def test_all_alert_files_are_kept(self, svc):
        service, common = svc
        cfg = load_service(service, [common])
        # cpu: 2 rec + 1 alert, oom: 1 rec + 2 alerts. Dropping a file would lose rules (R1).
        assert sorted(rule_names(cfg, "recording_rules")) == ["cpu:a", "cpu:b", "oom:a"]
        assert sorted(rule_names(cfg, "alerting_rules")) == ["cpu_alert", "oom_alert_1", "oom_alert_2"]

    def test_rule_count_scales_with_number_of_files(self, tmp_path):
        service = tmp_path / "svc"
        for i in range(7):
            alerts_file(service / f"f{i}_alerts.yaml", records=[f"r{i}"], alerts=[f"a{i}", f"a{i}x"])
        write_yaml(service / "zabbix_vars.yaml", {"zabbix": {"template": "t"}})
        cfg = load_service(service)
        assert len(cfg["groups"]) == 2
        assert len(rule_names(cfg, "recording_rules")) == 7
        assert len(rule_names(cfg, "alerting_rules")) == 14

    def test_files_not_named_alerts_with_groups_are_consumed_too(self, tmp_path):
        service = tmp_path / "svc"
        alerts_file(service / "a_alerts.yaml", alerts=["a1"])
        alerts_file(service / "extra.yaml", alerts=["extra1"])
        assert rule_names(load_service(service), "alerting_rules") == ["a1", "extra1"]

    def test_yml_extension_supported(self, tmp_path):
        service = tmp_path / "svc"
        alerts_file(service / "a_alerts.yml", alerts=["a1"])
        assert rule_names(load_service(service), "alerting_rules") == ["a1"]

    def test_non_yaml_and_hidden_files_ignored(self, svc):
        service, common = svc
        (service / "README.md").write_text("not: [yaml")
        (service / ".hidden.yaml").write_text("groups: broken: [")
        (service / "sub").mkdir()
        write_yaml(service / "sub" / "nested_alerts.yaml", {"groups": [{"name": "alerting_rules", "rules": [
            {"alert": "nested", "expr": "1"}]}]})
        assert "nested" not in rule_names(load_service(service, [common]), "alerting_rules")


class TestLoadServiceCommonMerge:
    def test_common_scalar_overridden_by_service(self, svc):
        service, common = svc
        write_yaml(common / "common_vars.yaml", {"zabbix": {"name": "Common name", "template_prefix": "pfx"}})
        cfg = load_service(service, [common])
        assert cfg["zabbix"]["name"] == "Demo"             # service wins
        assert cfg["zabbix"]["template_prefix"] == "pfx"   # common-only key survives
        assert cfg["zabbix"]["template"] == "demo"

    def test_lists_appended_common_first_then_service(self, svc):
        service, common = svc
        write_yaml(common / "common_vars.yaml", {"zabbix": {
            "tags": [{"tag": "scope", "value": "sysops"}],
            "macros": [{"macro": "{$COMMON}", "value": "1"}]}})
        write_yaml(service / "zabbix_vars.yaml", {"zabbix": {
            "template": "demo",
            "tags": [{"tag": "service_kind", "value": "demo"}],
            "macros": [{"macro": "{$SERVICE}", "value": "2"}]}})
        cfg = load_service(service, [common])
        assert [t["tag"] for t in cfg["zabbix"]["tags"]] == ["scope", "service_kind"]
        assert [m["macro"] for m in cfg["zabbix"]["macros"]] == ["{$COMMON}", "{$SERVICE}"]

    def test_labels_dicts_merged_service_label_overrides(self, svc):
        service, common = svc
        write_yaml(common / "common_vars.yaml", {"zabbix": {"labels": {"__event_recovery_notify": "1", "k": "c"}}})
        write_yaml(service / "zabbix_vars.yaml", {"zabbix": {"template": "demo", "labels": {"k": "s", "n": "x"}}})
        assert load_service(service, [common])["zabbix"]["labels"] == {
            "__event_recovery_notify": "1", "k": "s", "n": "x"}

    def test_multiple_common_dirs_later_overrides_earlier_service_overrides_all(self, svc, tmp_path):
        service, _ = svc
        c1, c2 = tmp_path / "c1", tmp_path / "c2"
        write_yaml(c1 / "v.yaml", {"prometheus": {"api": {"url": "c1", "username": "u1"}}, "only_c1": 1})
        write_yaml(c2 / "v.yaml", {"prometheus": {"api": {"url": "c2"}}, "only_c2": 2})
        cfg = load_service(service, [c1, c2])
        assert cfg["prometheus"]["api"] == {"url": "c2", "username": "u1"}
        assert (cfg["only_c1"], cfg["only_c2"]) == (1, 2)
        write_yaml(service / "zabbix_vars.yaml", {"zabbix": {"template": "demo"}, "prometheus": {"api": {"url": "svc"}}})
        assert load_service(service, [c1, c2])["prometheus"]["api"]["url"] == "svc"
        # reversed common order flips the winner among commons
        assert load_service(service, [c2, c1])["only_c1"] == 1

    def test_common_groups_are_merged_with_service_groups(self, svc):
        service, common = svc
        alerts_file(common / "shared_alerts.yaml", records=["shared:r"], alerts=["shared_alert"])
        cfg = load_service(service, [common])
        assert len(cfg["groups"]) == 2
        assert rule_names(cfg, "alerting_rules")[0] == "shared_alert"   # common applied first
        assert len(rule_names(cfg, "alerting_rules")) == 4

    def test_common_dir_not_modified_between_calls(self, svc):
        service, common = svc
        write_yaml(common / "common_vars.yaml", {"zabbix": {"tags": [{"tag": "t", "value": "v"}]}})
        first = load_service(service, [common])
        second = load_service(service, [common])
        assert first == second
        assert len(second["zabbix"]["tags"]) == 1   # no accumulation across calls

    def test_no_common_dirs(self, svc):
        service, _ = svc
        assert load_service(service)["zabbix"]["template"] == "demo"
        assert load_service(service, None) == load_service(service, [])

    def test_missing_common_dir_is_error(self, svc, tmp_path):
        service, _ = svc
        with pytest.raises(ServiceLoadError, match="Directory not found"):
            load_service(service, [tmp_path / "nope"])


class TestWikiVarsExcluded:
    WIKI = {"wiki": {"url": "https://wiki.example", "base_space_path": "SysOps/Monitoring"}}

    def test_common_wiki_vars_file_excluded(self, svc):
        service, common = svc
        write_yaml(common / "common_wiki_vars.yaml", self.WIKI)
        write_yaml(common / "common_vars.yaml", {"zabbix": {"template_prefix": "pfx"}})
        cfg = load_service(service, [common])
        assert "wiki" not in cfg
        assert cfg["zabbix"]["template_prefix"] == "pfx"

    @pytest.mark.parametrize("name", ["common_wiki_vars.yaml", "wiki_vars.yml", "Common_Wiki_Vars.YAML"])
    def test_wiki_vars_naming_variants_excluded(self, svc, name):
        service, common = svc
        write_yaml(common / name, self.WIKI)
        assert "wiki" not in load_service(service, [common])

    def test_list_yaml_files_wiki_skip_is_opt_in(self, tmp_path):
        write_yaml(tmp_path / "common_wiki_vars.yaml", self.WIKI)
        write_yaml(tmp_path / "common_vars.yaml", {"a": 1})
        assert [f.name for f in list_yaml_files(tmp_path)] == ["common_vars.yaml", "common_wiki_vars.yaml"]
        assert [f.name for f in list_yaml_files(tmp_path, skip_wiki_vars=True)] == ["common_vars.yaml"]

    def test_service_level_wiki_vars_is_merged(self, svc):
        service, common = svc
        write_yaml(common / "common_wiki_vars.yaml", self.WIKI)
        write_yaml(service / "wiki_vars.yaml", {"wiki": {"knowledgebase": {"alerts": {"alertings": {
            "cpu_alert": {"title": "t", "content": "c"}}}}}})
        cfg = load_service(service, [common])
        assert set(cfg["wiki"]) == {"knowledgebase"}      # no url / base_space_path leaked
        assert "cpu_alert" in cfg["wiki"]["knowledgebase"]["alerts"]["alertings"]

    def test_wiki_keys_would_fail_schema_if_not_excluded(self, svc):
        """Guards the reason for the exclusion rule: the schema really rejects these keys."""
        from promabbix.core.validation import ConfigValidator, ValidationError
        service, common = svc
        cfg = load_service(service, [common])
        ConfigValidator().validate_config(cfg)          # excluded -> valid
        cfg["wiki"] = copy.deepcopy(self.WIKI["wiki"])  # leaked -> rejected
        with pytest.raises(ValidationError, match="Additional properties"):
            ConfigValidator().validate_config(cfg)


class TestDeterministicOrder:
    def test_files_loaded_in_sorted_name_order(self, tmp_path):
        service = tmp_path / "svc"
        # created in non-alphabetical order on purpose
        for name in ["z", "m", "a", "b"]:
            alerts_file(service / f"{name}_alerts.yaml", alerts=[f"alert_{name}"])
        write_yaml(service / "zabbix_vars.yaml", {"zabbix": {"template": "t"}})
        assert rule_names(load_service(service), "alerting_rules") == [
            "alert_a", "alert_b", "alert_m", "alert_z"]

    def test_scalar_conflict_resolved_by_sorted_order_last_file_wins(self, tmp_path):
        service = tmp_path / "svc"
        alerts_file(service / "a_alerts.yaml", alerts=["x"])
        write_yaml(service / "b_vars.yaml", {"zabbix": {"template": "from_b"}})
        write_yaml(service / "a_vars.yaml", {"zabbix": {"template": "from_a"}})
        assert load_service(service)["zabbix"]["template"] == "from_b"

    def test_repeated_loads_identical(self, svc):
        service, common = svc
        assert load_service(service, [common]) == load_service(service, [common])

    def test_list_yaml_files_sorted_by_name(self, tmp_path):
        for n in ["c.yaml", "a.yml", "b.yaml"]:
            (tmp_path / n).write_text("{}")
        assert [f.name for f in list_yaml_files(tmp_path)] == ["a.yml", "b.yaml", "c.yaml"]


class TestErrors:
    def test_empty_service_dir(self, tmp_path):
        service = tmp_path / "empty"
        service.mkdir()
        with pytest.raises(ServiceLoadError, match="No \\*.yaml / \\*.yml files found"):
            load_service(service)

    def test_service_dir_missing(self, tmp_path):
        with pytest.raises(ServiceLoadError, match="Directory not found"):
            load_service(tmp_path / "nope")

    def test_service_dir_is_a_file(self, tmp_path):
        f = tmp_path / "f.yaml"
        f.write_text("a: 1")
        with pytest.raises(ServiceLoadError, match="Directory not found"):
            load_service(f)

    def test_service_without_alerts_names_the_service_dir(self, tmp_path):
        service = tmp_path / "wrike-global"
        write_yaml(service / "zabbix_vars.yaml", {"zabbix": {"template": "t"}})
        with pytest.raises(ServiceLoadError) as exc:
            load_service(service)
        assert "wrike-global" in str(exc.value) and "No 'groups' found" in str(exc.value)

    def test_alerts_with_no_rules_at_all(self, tmp_path):
        service = tmp_path / "svc"
        alerts_file(service / "a_alerts.yaml", split_groups=True)   # both groups, zero rules
        with pytest.raises(ServiceLoadError, match="No rules found"):
            load_service(service)

    def test_alerts_may_come_from_common_when_service_has_none(self, tmp_path):
        service = tmp_path / "svc"
        write_yaml(service / "zabbix_vars.yaml", {"zabbix": {"template": "t"}})
        common = tmp_path / "common"
        alerts_file(common / "c_alerts.yaml", alerts=["c"])
        assert rule_names(load_service(service, [common]), "alerting_rules") == ["c"]

    def test_invalid_yaml_names_the_file(self, svc):
        service, _ = svc
        (service / "broken.yaml").write_text("a: b: c: [")
        with pytest.raises(ServiceLoadError, match="broken.yaml"):
            load_service(service)

    def test_top_level_list_rejected(self, svc):
        service, _ = svc
        (service / "list.yaml").write_text("- 1\n- 2\n")
        with pytest.raises(ServiceLoadError, match="top level must be a mapping"):
            load_service(service)

    def test_empty_yaml_file_is_skipped(self, svc):
        service, common = svc
        (service / "empty.yaml").write_text("")
        (common / "comment_only.yaml").write_text("# nothing\n")
        assert len(load_service(service, [common])["groups"]) == 2

    def test_service_load_error_is_value_error(self):
        assert issubclass(ServiceLoadError, ValueError)


class TestLegacyMigrationConsumesAllAlertFiles:
    """core/migration.py: _find_alerts_file used to return only alert_files[0]."""

    def make(self, tmp_path):
        service = tmp_path / "legacy"
        alerts_file(service / "cpu_alerts.yaml", records=["cpu:a"], alerts=["cpu_alert"])
        alerts_file(service / "oom_alerts.yaml", records=["oom:a"], alerts=["oom_alert"])
        alerts_file(service / "net_alerts.yaml", records=["net:a"], alerts=["net_alert"])
        write_yaml(service / "zabbix_vars.yaml", {"zabbix": {"template": "t"}})
        return service

    def test_find_alerts_files_returns_all_sorted(self, tmp_path):
        service = self.make(tmp_path)
        assert [f.name for f in _find_alerts_files(service)] == [
            "cpu_alerts.yaml", "net_alerts.yaml", "oom_alerts.yaml"]

    def test_find_alerts_files_none_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No \\*_alerts.yaml"):
            _find_alerts_files(tmp_path)

    def test_migrate_keeps_every_rule_in_two_groups(self, tmp_path):
        cfg = migrate_legacy_service(self.make(tmp_path))
        assert [g["name"] for g in cfg["groups"]] == ["recording_rules", "alerting_rules"]
        assert rule_names(cfg, "recording_rules") == ["cpu:a", "net:a", "oom:a"]
        assert rule_names(cfg, "alerting_rules") == ["cpu_alert", "net_alert", "oom_alert"]

    def test_migrate_does_not_inject_defaults(self, tmp_path):
        """Defaults live only in the Jinja2 template."""
        cfg = migrate_legacy_service(self.make(tmp_path))
        assert "prometheus" not in cfg and "promabbix" not in cfg

    def test_default_sections_helper_removed(self):
        assert not hasattr(migration, "_add_default_sections")
        assert not hasattr(migration, "_find_alerts_file")

    def test_migrate_invalid_alerts_file_still_reported(self, tmp_path):
        service = self.make(tmp_path)
        (service / "bad_alerts.yaml").write_text("other: 1\n")
        with pytest.raises(ValueError, match="Invalid alerts file format"):
            migrate_legacy_service(service)

    def test_load_service_reexported_from_migration(self):
        assert migration.load_service is load_service
