# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#
"""CLI tests for syncTemplate / syncPseudoHosts: credentials, dry-run, --exit-code, failure exit codes."""

import copy
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from promabbix.cli import sync_template as cli_mod
from promabbix.cli.sync_template import CredentialsError, resolve_credentials
from promabbix.promabbix import cli
from promabbix.zabbix.client import WRITE_METHODS, ZabbixClient
from tests.zabbix_fake import FakeZabbix

EXAMPLE = Path(__file__).parent.parent / "examples" / "minikube-alert-config.yaml"
SERVICE_DIR = Path(__file__).parent / "fixtures" / "directory_input" / "node_exporter"
COMMON_DIR = Path(__file__).parent / "fixtures" / "directory_input" / "common"
DIR_TEMPLATE = "templ_module_promt_sysops_service_node_exporter"
HOST_TEMPLATE = "templ_module_promt_kube_minikube"


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    for k in ("ZABBIX_URL", "ZABBIX_USER", "ZABBIX_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    return h


@pytest.fixture
def fake(monkeypatch, home):
    f = FakeZabbix(groups=["New host maitenance", "Kubernetes"])
    created = []

    def factory(url, user, password, timeout, read_only):
        created.append({"url": url, "user": user, "password": password, "timeout": timeout, "read_only": read_only})
        return ZabbixClient(url, user, password, timeout=timeout, read_only=read_only, transport=f)

    monkeypatch.setattr(cli_mod, "_default_client_factory", factory)
    f.clients = created  # type: ignore[attr-defined]
    return f


@pytest.fixture
def cfg(tmp_path):
    p = tmp_path / "svc.yaml"
    shutil.copy(EXAMPLE, p)
    return str(p)


def invoke(*args, env=None):
    return CliRunner(mix_stderr=False).invoke(cli, list(args), env=env, catch_exceptions=False)


CREDS = ("--zabbix-url", "https://zbx.example.com", "--zabbix-user", "svc", "--zabbix-password", "secret")


class TestRegistration:
    def test_help_lists_commands(self):
        out = invoke("--help").stdout
        assert "syncTemplate" in out and "syncPseudoHosts" in out and "generateTemplate" in out

    @pytest.mark.parametrize("cmd", ["syncTemplate", "syncPseudoHosts"])
    def test_flags_documented(self, cmd):
        out = invoke(cmd, "--help").stdout
        for flag in ("--common", "--dry-run", "--exit-code", "--zabbix-url", "--zabbix-user", "--zabbix-password"):
            assert flag in out


class TestCredentialPrecedence:
    def write_auth(self, home, name=".zbx_auth.yml", **kv):
        data = {"zbx_url": "https://file", "zbx_username": "file-user", "zbx_password": "file-pass"}
        data.update(kv)
        (home / name).write_text(yaml.safe_dump(data))

    def test_cli_beats_env_beats_file(self, home):
        self.write_auth(home)
        env = {"ZABBIX_URL": "https://env", "ZABBIX_USER": "env-user", "ZABBIX_PASSWORD": "env-pass"}
        assert resolve_credentials("https://cli", "cli-user", "cli-pass", env) == ("https://cli", "cli-user", "cli-pass")
        assert resolve_credentials(None, None, None, env) == ("https://env", "env-user", "env-pass")
        assert resolve_credentials(None, None, None, {}) == ("https://file", "file-user", "file-pass")

    def test_sources_mix_per_field(self, home):
        self.write_auth(home)
        assert resolve_credentials("https://cli", None, None, {"ZABBIX_PASSWORD": "env-pass"}) == (
            "https://cli", "file-user", "env-pass")

    def test_process_environment_is_used_by_default(self, home, monkeypatch):
        monkeypatch.setenv("ZABBIX_URL", "https://env")
        monkeypatch.setenv("ZABBIX_USER", "u")
        monkeypatch.setenv("ZABBIX_PASSWORD", "p")
        assert resolve_credentials(None, None, None) == ("https://env", "u", "p")

    def test_auth_file_not_read_when_not_needed(self, home):
        (home / ".zbx_auth.yml").write_text(":::not yaml:::\n  - [")
        assert resolve_credentials("a", "b", "c", {}) == ("a", "b", "c")

    def test_alternative_auth_file_names(self, home):
        self.write_auth(home, ".zbx_auth.json")
        assert resolve_credentials(None, None, None, {})[0] == "https://file"

    def test_missing_everything_names_every_source(self, home):
        with pytest.raises(CredentialsError) as ei:
            resolve_credentials(None, None, None, {})
        msg = str(ei.value)
        assert "url, user, password" in msg and "ZABBIX_URL" in msg and ".zbx_auth.yml" in msg

    def test_partial_file_reports_only_missing_fields(self, home):
        (home / ".zbx_auth.yml").write_text("zbx_url: https://x\nzbx_username: u\n")
        with pytest.raises(CredentialsError, match="missing Zabbix password"):
            resolve_credentials(None, None, None, {})

    @pytest.mark.parametrize("content", ["- a\n- b\n", "{{{"])
    def test_malformed_auth_file(self, home, content):
        (home / ".zbx_auth.yml").write_text(content)
        with pytest.raises(CredentialsError):
            resolve_credentials(None, None, None, {})

    def test_cli_end_to_end_uses_file_credentials(self, home, fake, cfg):
        self.write_auth(home, zbx_url="https://zbx.file")
        fake.password = "file-pass"
        r = invoke("syncTemplate", cfg, "--dry-run")
        assert r.exit_code == 0, r.stderr
        assert fake.clients[0]["url"] == "https://zbx.file" and fake.clients[0]["user"] == "file-user"

    def test_cli_missing_credentials_exits_1_without_api_calls(self, home, fake, cfg):
        r = invoke("syncTemplate", cfg, "--dry-run")
        assert r.exit_code == 1 and "missing Zabbix" in r.stderr
        assert fake.calls == [] and fake.clients == []


class TestSyncTemplateCommand:
    def test_real_run_imports_and_logs_out(self, fake, cfg):
        r = invoke("syncTemplate", cfg, *CREDS)
        assert r.exit_code == 0, r.stderr
        imports = fake.calls_of("configuration.import")
        assert len(imports) == 1
        assert HOST_TEMPLATE in json.loads(imports[0]["params"]["source"])["zabbix_export"]["templates"][0]["template"]
        assert fake.methods[-1] == "user.logout"
        assert fake.clients[0]["read_only"] is False
        assert "created" in r.stdout
        assert fake.calls_of("host.create") == []  # syncTemplate never touches hosts

    def test_second_run_is_noop_with_real_render(self, fake, cfg):
        invoke("syncTemplate", cfg, *CREDS)
        # the fake's export is the imported source; the diff engine ignores uuids.
        r = invoke("syncTemplate", cfg, *CREDS)
        assert r.exit_code == 0
        assert len(fake.calls_of("configuration.import")) == 1
        assert "unchanged" in r.stdout

    def test_timeout_option_reaches_transport(self, fake, cfg):
        invoke("syncTemplate", cfg, *CREDS, "--timeout", "12")
        assert {c["timeout"] for c in fake.calls} == {12.0}

    def test_invalid_config_exits_1_before_touching_zabbix(self, fake, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("groups: 5\nzabbix: {}\n")
        r = invoke("syncTemplate", str(bad), *CREDS)
        assert r.exit_code == 1 and fake.calls == []

    def test_missing_file_exits_1(self, fake, tmp_path):
        r = invoke("syncTemplate", str(tmp_path / "nope.yaml"), *CREDS)
        assert r.exit_code == 1 and "not found" in r.stderr and fake.calls == []

    def test_empty_directory_input_exits_1_before_touching_zabbix(self, fake, tmp_path):
        r = invoke("syncTemplate", str(tmp_path), *CREDS)
        assert r.exit_code == 1 and "No *.yaml" in r.stderr and fake.calls == []

    def test_common_with_a_file_input_is_rejected(self, fake, cfg, tmp_path):
        r = invoke("syncTemplate", cfg, "--common", str(tmp_path), *CREDS)
        assert r.exit_code == 1 and "--common" in r.stderr and fake.calls == []

    def test_directory_input_goes_through_adapter(self, fake, cfg, monkeypatch, tmp_path):
        seen = {}

        def loader(path, common):
            seen["args"] = (path, list(common))
            return yaml.safe_load(Path(cfg).read_text())

        monkeypatch.setattr(cli_mod, "_load_config", loader)
        r = invoke("syncTemplate", str(tmp_path), "--common", "c1", "--common", "c2", "--dry-run", *CREDS)
        assert r.exit_code == 0 and seen["args"] == (str(tmp_path), ["c1", "c2"])

    def test_login_failure_exits_1_with_message(self, fake, cfg):
        fake.password = "different"
        r = invoke("syncTemplate", cfg, *CREDS)
        assert r.exit_code == 1 and "login failed" in r.stderr and "secret" not in r.stderr
        assert fake.write_calls == []

    def test_api_error_exits_1(self, fake, cfg):
        fake.errors["configuration.import"] = (-32500, "Application error.", "item key conflict")
        r = invoke("syncTemplate", cfg, *CREDS)
        assert r.exit_code == 1 and "item key conflict" in r.stderr

    def test_http_failure_exits_1(self, fake, cfg):
        fake.http_status = 502
        r = invoke("syncTemplate", cfg, *CREDS)
        assert r.exit_code == 1 and "502" in r.stderr


class TestDryRun:
    @pytest.mark.parametrize("cmd", ["syncTemplate", "syncPseudoHosts"])
    def test_dry_run_zero_writes_no_live_template(self, fake, cfg, cmd):
        r = invoke(cmd, cfg, "--dry-run", *CREDS)
        assert r.exit_code == 0, r.stderr
        assert fake.write_calls == [] and not (set(fake.methods) & WRITE_METHODS)
        assert fake.clients[0]["read_only"] is True
        assert "would create" in r.stdout

    @pytest.mark.parametrize("cmd", ["syncTemplate", "syncPseudoHosts"])
    def test_dry_run_zero_writes_after_real_sync(self, fake, cfg, cmd):
        invoke("syncPseudoHosts", cfg, *CREDS)
        writes = len(fake.write_calls)
        r = invoke(cmd, cfg, "--dry-run", *CREDS)
        assert r.exit_code == 0 and len(fake.write_calls) == writes
        assert "would" not in r.stdout

    def test_dry_run_with_drift_prints_diff_but_writes_nothing(self, fake, cfg):
        invoke("syncPseudoHosts", cfg, *CREDS)
        writes = len(fake.write_calls)
        name = next(iter(fake.templates))
        doc = fake.exports[name]
        doc["zabbix_export"]["templates"][0]["items"].append({"uuid": "x", "name": "stale", "key": "stale.item"})
        fake.hosts["minikube"]["description"] = "drifted"
        r = invoke("syncPseudoHosts", cfg, "--dry-run", *CREDS)
        assert r.exit_code == 0
        assert len(fake.write_calls) == writes
        assert "would update" in r.stdout and '!!! REMOVE item "stale.item"' in r.stdout
        assert "host minikube: would update" in r.stdout

    def test_dry_run_api_error_midway_exit_1_no_writes(self, fake, cfg):
        fake.errors["host.get"] = (-32500, "Application error.", "db down")
        r = invoke("syncPseudoHosts", cfg, "--dry-run", *CREDS)
        assert r.exit_code == 1 and fake.write_calls == []
        assert "db down" in r.stderr or "db down" in r.stdout


class TestExitCode:
    def test_default_exit_0_even_with_changes(self, fake, cfg):
        assert invoke("syncPseudoHosts", cfg, "--dry-run", *CREDS).exit_code == 0

    def test_exit_code_2_when_changes(self, fake, cfg):
        r = invoke("syncPseudoHosts", cfg, "--dry-run", "--exit-code", *CREDS)
        assert r.exit_code == 2 and fake.write_calls == []

    def test_exit_code_0_when_converged(self, fake, cfg):
        invoke("syncPseudoHosts", cfg, *CREDS)
        r = invoke("syncPseudoHosts", cfg, "--dry-run", "--exit-code", *CREDS)
        assert r.exit_code == 0

    def test_exit_code_2_for_host_only_change(self, fake, cfg):
        invoke("syncPseudoHosts", cfg, *CREDS)
        fake.hosts["minikube"]["status"] = "1"
        r = invoke("syncPseudoHosts", cfg, "--dry-run", "--exit-code", *CREDS)
        assert r.exit_code == 2
        assert invoke("syncTemplate", cfg, "--dry-run", "--exit-code", *CREDS).exit_code == 0

    def test_exit_code_2_for_template_change_with_syncTemplate(self, fake, cfg):
        r = invoke("syncTemplate", cfg, "--dry-run", "--exit-code", *CREDS)
        assert r.exit_code == 2

    def test_error_beats_changes(self, fake, cfg):
        fake.errors["host.get"] = (-32500, "Application error.", "x")
        assert invoke("syncPseudoHosts", cfg, "--dry-run", "--exit-code", *CREDS).exit_code == 1

    def test_exit_code_flag_ignored_for_real_runs(self, fake, cfg):
        assert invoke("syncPseudoHosts", cfg, "--exit-code", *CREDS).exit_code == 0


class TestSyncPseudoHostsCommand:
    def test_real_run_creates_template_then_host_with_defaults(self, fake, cfg):
        r = invoke("syncPseudoHosts", cfg, *CREDS)
        assert r.exit_code == 0, r.stderr
        assert fake.methods.index("configuration.import") < fake.methods.index("host.create")
        p = fake.calls_of("host.create")[0]["params"]
        assert p["host"] == "minikube" and p["name"] == "minikube"
        assert p["groups"] == [{"groupid": fake.groups["Kubernetes"]}]
        assert p["templates"] == [{"templateid": fake.templates[HOST_TEMPLATE]}]
        assert p["proxyid"] == fake.proxies["gce-infra-zabbix-proxy-pgsql-2"]
        assert p["interfaces"] == [{"type": 1, "main": 1, "useip": 1, "ip": "127.0.0.1", "dns": "", "port": "10050"}]
        assert p["macros"][0]["macro"] == "{$CPU.UTIL.NODE.MAX}"
        assert "host minikube: created" in r.stdout

    def test_second_run_no_writes_at_all(self, fake, cfg):
        invoke("syncPseudoHosts", cfg, *CREDS)
        writes = len(fake.write_calls)
        r = invoke("syncPseudoHosts", cfg, *CREDS)
        assert r.exit_code == 0 and len(fake.write_calls) == writes
        assert "host minikube: unchanged" in r.stdout

    def test_failed_host_exits_nonzero_but_others_are_processed(self, fake, cfg, tmp_path):
        data = yaml.safe_load(Path(cfg).read_text())
        base = data["zabbix"]["hosts"][0]
        data["zabbix"]["hosts"] = [dict(base, host_name="bad"), dict(base, host_name="good")]
        multi = tmp_path / "multi.yaml"
        multi.write_text(yaml.safe_dump(data))
        fake.errors["host.create"] = lambda p: (-32500, "Application error.", "dup") if p["host"] == "bad" else None
        r = invoke("syncPseudoHosts", str(multi), *CREDS)
        assert r.exit_code == 1
        assert "good" in fake.hosts and "bad" not in fake.hosts
        assert "host bad: FAILED" in r.stdout and "host bad failed" in r.stderr
        assert fake.methods[-1] == "user.logout"

    def test_service_without_hosts_only_syncs_template(self, fake, cfg, tmp_path):
        data = yaml.safe_load(Path(cfg).read_text())
        del data["zabbix"]["hosts"]
        p = tmp_path / "nohosts.yaml"
        p.write_text(yaml.safe_dump(data))
        r = invoke("syncPseudoHosts", str(p), *CREDS)
        assert r.exit_code == 0 and len(fake.calls_of("configuration.import")) == 1
        assert fake.calls_of("host.get") == []

    def test_password_never_printed(self, fake, cfg):
        r = invoke("syncPseudoHosts", cfg, *CREDS)
        assert "secret" not in r.stdout + r.stderr


class TestDirectoryInputDryRun:
    """syncPseudoHosts on a real-layout service DIR + --common, against the fake Zabbix, with A9's diff engine."""

    @pytest.fixture
    def dir_fake(self, fake, tmp_path):
        fake.groups.update({"Production hosts": "50", "Prometheus pseudo hosts": "51"})
        out = tmp_path / "rendered.json"
        r = invoke("generateTemplate", str(SERVICE_DIR), "--common", str(COMMON_DIR), "-o", str(out))
        assert r.exit_code == 0, r.stderr
        fake.rendered = json.loads(out.read_text())  # type: ignore[attr-defined]
        return fake

    def live_with(self, fake, mutate=None, mutate_export=None):
        live = copy.deepcopy(fake.rendered)
        if mutate:
            mutate(live["zabbix_export"]["templates"][0])
        if mutate_export:
            mutate_export(live["zabbix_export"])
        fake.add_live_template(live)

    def args(self, *extra):
        return ("syncPseudoHosts", str(SERVICE_DIR), "--common", str(COMMON_DIR), "--dry-run", *extra, *CREDS)

    def test_removed_item_is_rendered_by_the_real_diff_engine_and_nothing_is_written(self, dir_fake):
        self.live_with(dir_fake, lambda t: t["items"].append(
            {"uuid": "x", "name": "stale", "key": "stale.item", "type": "TRAP", "value_type": "TEXT"}))
        r = invoke(*self.args())
        assert r.exit_code == 0, r.stderr
        assert dir_fake.write_calls == [] and not (set(dir_fake.methods) & WRITE_METHODS)
        assert dir_fake.clients[0]["read_only"] is True
        assert f"template {DIR_TEMPLATE}: would update" in r.stdout
        assert '!!! REMOVE item "stale.item"' in r.stdout
        assert "!!! 1 object(s) would be DELETED" in r.stdout
        assert "1 REMOVAL(S)" in r.stdout and "1 removal(s) would be applied" in re.sub(r"\x1b\[[0-9;]*m", "", r.stderr)
        # the host does not exist yet; its create shows up with the service's desired state
        assert "host node-exporter-prod: would create" in r.stdout
        assert "would be created" in r.stdout

    def test_removed_discovery_rule_and_trigger_are_destructive_too(self, dir_fake):
        def mutate(tpl):
            tpl["discovery_rules"].append({"uuid": "y", "name": "old lld", "key": "old.lld", "type": "TRAP"})

        def mutate_export(export):
            export.setdefault("triggers", []).append({"uuid": "z", "name": "old trigger", "expression": "last(/x/y)=1"})
        self.live_with(dir_fake, mutate, mutate_export)
        r = invoke(*self.args())
        assert '!!! REMOVE discovery_rule "old.lld"' in r.stdout
        assert '!!! REMOVE trigger "old trigger"' in r.stdout
        assert dir_fake.write_calls == []

    def test_converged_live_template_is_unchanged_despite_new_uuids(self, dir_fake):
        def mutate(tpl):
            tpl["uuid"] = "f" * 32
            for rule in tpl["discovery_rules"]:
                rule["uuid"] = "e" * 32
        self.live_with(dir_fake, mutate)
        r = invoke(*self.args("--exit-code"))
        assert f"template {DIR_TEMPLATE}: unchanged" in r.stdout
        assert "REMOVE" not in r.stdout
        assert dir_fake.write_calls == []
        assert r.exit_code == 2  # the host does not exist yet, so there is still a change

    def test_pm4_wiki_difference_is_reported_as_a_change_not_a_removal(self, dir_fake):
        def mutate(tpl):
            for rule in tpl["discovery_rules"]:
                for proto in rule["item_prototypes"]:
                    for trig in proto.get("trigger_prototypes", []):
                        trig.pop("description", None)
                        trig["tags"] = [t for t in trig.get("tags", []) if t["tag"] != "wiki_page_tag"]
        self.live_with(dir_fake, mutate)
        r = invoke(*self.args())
        assert r.exit_code == 0
        assert "Wiki: {$WIKI.TAG.URL}" in r.stdout
        assert "REMOVE" not in r.stdout and "REMOVAL" not in r.stdout
        assert dir_fake.write_calls == []

    def test_real_run_then_dry_run_converges(self, dir_fake):
        r = invoke("syncPseudoHosts", str(SERVICE_DIR), "--common", str(COMMON_DIR), *CREDS)
        assert r.exit_code == 0, r.stderr
        writes = len(dir_fake.write_calls)
        assert writes == 2  # configuration.import + host.create
        r = invoke(*self.args("--exit-code"))
        assert r.exit_code == 0, r.stdout
        assert "would" not in r.stdout and len(dir_fake.write_calls) == writes
        host = dir_fake.hosts["node-exporter-prod"]
        assert host["description"] == ""
