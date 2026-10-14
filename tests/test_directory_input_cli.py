#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

"""CLI-level tests for ``generateTemplate <service_dir> --common <dir>`` on real-layout fixtures."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promabbix.core.data_utils import deep_merge_append  # noqa: E402
from promabbix.core.loader import list_yaml_files, load_service  # noqa: E402
from promabbix.core.validation import ConfigValidator  # noqa: E402
from promabbix.promabbix import cli  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "directory_input"
SERVICE = FIXTURES / "node_exporter"
COMMON = FIXTURES / "common"


def flat(text):
    """Strip ANSI colours and collapse whitespace (rich wraps long error lines)."""
    return " ".join(re.sub(r"\x1b\[[0-9;]*m", "", text).split())


def count_rules(config, group):
    return len(next(g for g in config["groups"] if g["name"] == group)["rules"])


@pytest.fixture
def runner():
    return CliRunner()


class TestFixtureLayoutMirrorsRealRepo:
    def test_fixture_has_several_alert_files_and_a_common_wiki_file(self):
        assert len(list(SERVICE.glob("*_alerts.yaml"))) >= 2
        assert (COMMON / "common_wiki_vars.yaml").is_file()
        assert (COMMON / "common_wiki_vars.yaml").read_text().count("base_space_path") == 1

    def test_load_service_keeps_every_rule_from_every_alerts_file(self):
        expected_rec = expected_alr = 0
        for f in SERVICE.glob("*_alerts.yaml"):
            for group in yaml.safe_load(f.read_text())["groups"]:
                if group["name"] == "recording_rules":
                    expected_rec += len(group["rules"])
                else:
                    expected_alr += len(group["rules"])
        assert expected_rec >= 7 and expected_alr >= 8   # guards against a trivially small fixture
        cfg = load_service(SERVICE, [COMMON])
        assert len(cfg["groups"]) == 2
        assert count_rules(cfg, "recording_rules") == expected_rec
        assert count_rules(cfg, "alerting_rules") == expected_alr

    def test_merged_fixture_validates_against_schema(self):
        cfg = load_service(SERVICE, [COMMON])
        ConfigValidator().validate_config(cfg)
        assert "wiki" in cfg and "url" not in cfg["wiki"] and "base_space_path" not in cfg["wiki"]

    def test_merge_matches_yq_eval_all_reduce(self):
        """The documented equivalence: `yq eval-all '. as $item ireduce ({}; . *+ $item)'` over common + service."""
        yq = shutil.which("yq")
        if yq is None:
            pytest.skip("yq not installed")
        files = list_yaml_files(COMMON, skip_wiki_vars=True) + list_yaml_files(SERVICE)
        proc = subprocess.run(
            [yq, "eval-all", "-o=json", ". as $item ireduce ({}; . *+ $item)", *map(str, files)],
            capture_output=True, text=True)
        if proc.returncode != 0 or not proc.stdout.strip():
            pytest.skip(f"yq not usable here: {proc.stderr[:200]}")
        if "mikefarah" not in subprocess.run([yq, "--version"], capture_output=True, text=True).stdout:
            pytest.skip("not mikefarah/yq")
        expected = json.loads(proc.stdout)
        expected_groups = expected.pop("groups")
        cfg = load_service(SERVICE, [COMMON])
        groups = cfg.pop("groups")
        assert cfg == expected
        # yq leaves 2N groups; after normalisation the rules are the same, in order
        assert [r for g in expected_groups if g["name"] == "alerting_rules" for r in g["rules"]] == groups[1]["rules"]
        assert [r for g in expected_groups if g["name"] == "recording_rules" for r in g["rules"]] == groups[0]["rules"]

    def test_deep_merge_helper_is_the_same_as_reduce_over_files(self):
        files = list_yaml_files(COMMON, skip_wiki_vars=True) + list_yaml_files(SERVICE)
        merged = {}
        for f in files:
            merged = deep_merge_append(merged, yaml.safe_load(f.read_text()))
        assert len(merged["groups"]) > 2   # un-normalised: 2 groups per alerts file


class TestCliDirectoryInput:
    def test_end_to_end_generates_template_from_directory(self, runner, tmp_path):
        out = tmp_path / "out.json"
        result = runner.invoke(cli, ["generateTemplate", str(SERVICE), "--common", str(COMMON), "-o", str(out)])
        assert result.exit_code == 0, result.output
        doc = json.loads(out.read_text())
        template = doc["zabbix_export"]["templates"][0]

        # common/ values reached the output
        assert template["tags"][0] == {"tag": "__metric_source", "value": "prometheus"}
        assert [t["tag"] for t in template["tags"]] == ["__metric_source", "scope", "service_kind"]
        assert all(i["url"] == "{$PROMT.API.URL}/query" for i in template["items"])
        # service values
        assert template["name"] == "Template Module Prometheus SysOps service Node Exporter"

        # every recording rule from every alerts file became a discovery rule + item prototype,
        # every alerting rule a trigger prototype (nothing dropped)
        cfg = load_service(SERVICE, [COMMON])
        records = [r["record"] for r in next(g for g in cfg["groups"] if g["name"] == "recording_rules")["rules"]]
        alerts = [r["alert"] for r in next(g for g in cfg["groups"] if g["name"] == "alerting_rules")["rules"]]
        assert len(records) >= 7 and len(alerts) >= 8
        assert len(template["items"]) == len(records)   # one master item per recording rule
        protos = [i for dr in template["discovery_rules"] for i in dr["item_prototypes"]]
        triggers = [t for i in protos for t in i["trigger_prototypes"]]
        assert len(protos) == len(records)
        # the template emits an alert as a trigger prototype of the recording rule with the SAME name;
        # node_cpu:system_crit:percent has no recording rule of its own and is (pre-existing behaviour) not emitted
        matched = [a for a in alerts if a in records]
        assert len(matched) == len(alerts) - 1
        assert len(triggers) == len(matched)
        # rules from both alerts files are present (cpu_alerts.yaml and kernel_alerts.yaml)
        assert any("OOM killer" in t["name"] for t in triggers)
        assert any("CPU" in t["name"] for t in triggers)

    def test_validate_only_on_directory_succeeds(self, runner):
        result = runner.invoke(cli, ["generateTemplate", str(SERVICE), "--common", str(COMMON), "--validate-only"])
        assert result.exit_code == 0, result.output

    def test_short_option_and_repeated_common(self, runner, tmp_path):
        extra = tmp_path / "extra"
        extra.mkdir()
        (extra / "more.yaml").write_text(yaml.safe_dump({"zabbix": {"labels": {"extra_label": "yes"}}}))
        out = tmp_path / "out.json"
        result = runner.invoke(cli, ["generateTemplate", str(SERVICE), "-c", str(COMMON), "-c", str(extra),
                                     "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert "extra_label" in out.read_text()

    def test_without_common_item_url_falls_back_to_template_default(self, runner, tmp_path):
        """The template owns the default Prometheus URL: no injection by the loader."""
        out = tmp_path / "out.json"
        # no common: zabbix.template_prefix and prometheus.api.url missing; still schema-valid
        result = runner.invoke(cli, ["generateTemplate", str(SERVICE), "-o", str(out)])
        assert result.exit_code == 0, result.output
        template = json.loads(out.read_text())["zabbix_export"]["templates"][0]
        assert {i["url"] for i in template["items"]} == {"http://localhost:9090/api/v1/query"}

    def test_stdout_output(self, runner):
        result = runner.invoke(cli, ["generateTemplate", str(SERVICE), "--common", str(COMMON)])
        assert result.exit_code == 0
        assert '"zabbix_export"' in result.output

    def test_help_documents_directory_input_and_wiki_rule(self, runner):
        result = runner.invoke(cli, ["generateTemplate", "--help"])
        assert result.exit_code == 0
        for needle in ("--common", "DIRECTORY", "APPENDED", "wiki_vars", "exactly two"):
            assert needle in result.output

    def test_empty_service_dir_clear_error(self, runner, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = runner.invoke(cli, ["generateTemplate", str(empty), "--common", str(COMMON), "--validate-only"])
        assert result.exit_code == 1
        assert "No *.yaml / *.yml files found" in flat(result.output)

    def test_service_without_alerts_clear_error(self, runner, tmp_path):
        svc = tmp_path / "wrike-global"
        svc.mkdir()
        (svc / "zabbix_vars.yaml").write_text(yaml.safe_dump({"zabbix": {"template": "t"}}))
        result = runner.invoke(cli, ["generateTemplate", str(svc), "--common", str(COMMON), "--validate-only"])
        assert result.exit_code == 1
        assert "No 'groups' found" in flat(result.output) and "wrike-global" in flat(result.output)

    def test_missing_common_dir_clear_error(self, runner, tmp_path):
        result = runner.invoke(cli, ["generateTemplate", str(SERVICE), "--common", str(tmp_path / "nope"),
                                     "--validate-only"])
        assert result.exit_code == 1
        assert "Directory not found" in flat(result.output)

    def test_common_with_file_input_is_rejected(self, runner, tmp_path):
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.safe_dump(load_service(SERVICE, [COMMON]), sort_keys=False))
        result = runner.invoke(cli, ["generateTemplate", str(cfg_file), "--common", str(COMMON), "--validate-only"])
        assert result.exit_code == 1
        assert "--common can only be used" in flat(result.output)

    def test_common_with_stdin_input_is_rejected(self, runner):
        result = runner.invoke(cli, ["generateTemplate", "-", "--common", str(COMMON), "--validate-only"],
                               input="groups: []\n")
        assert result.exit_code == 1
        assert "--common can only be used" in flat(result.output)

    def test_leaked_wiki_keys_in_service_dir_are_still_rejected_by_schema(self, runner, tmp_path):
        """Exclusion applies to --common only; a service-level wiki.url is the author's error."""
        svc = tmp_path / "svc"
        shutil.copytree(SERVICE, svc)
        (svc / "wiki_vars.yaml").write_text(yaml.safe_dump({"wiki": {"url": "https://x", "base_space_path": "y"}}))
        result = runner.invoke(cli, ["generateTemplate", str(svc), "--common", str(COMMON), "--validate-only"])
        assert result.exit_code == 1
        assert "Additional properties" in flat(result.output)

    def test_legacy_keys_still_rejected_by_strict_schema(self, runner, tmp_path):
        """No compat layer (D1): a legacy common_vars.yaml is reported, not silently translated."""
        common = tmp_path / "common"
        common.mkdir()
        (common / "common_vars.yaml").write_text(yaml.safe_dump({
            "zabbix_template_prefix": "templ_module_promt", "zabbix": {"labels": {"__event_recovery_notify": 1}}}))
        result = runner.invoke(cli, ["generateTemplate", str(SERVICE), "--common", str(common), "--validate-only"])
        assert result.exit_code == 1
        assert "zabbix_template_prefix" in flat(result.output)

    def test_file_input_still_works(self, runner, tmp_path):
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.safe_dump(load_service(SERVICE, [COMMON]), sort_keys=False))
        result = runner.invoke(cli, ["generateTemplate", str(cfg_file), "--validate-only"])
        assert result.exit_code == 0, result.output

    def test_directory_and_equivalent_file_input_generate_identical_output(self, runner, tmp_path):
        """Directory input is only a loader: same merged config -> same template (modulo timestamp UUIDs)."""
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.safe_dump(load_service(SERVICE, [COMMON]), sort_keys=False))
        a = runner.invoke(cli, ["generateTemplate", str(SERVICE), "--common", str(COMMON)])
        b = runner.invoke(cli, ["generateTemplate", str(cfg_file)])
        assert a.exit_code == b.exit_code == 0

        scrub = lambda text: re.sub(r'"uuid": "[0-9a-f]{32}"', '"uuid": "X"', text)  # noqa: E731
        assert scrub(a.output) == scrub(b.output)
