# -*- coding: utf-8 -*-
#
# Copyright 2025 Wrike Inc.
#
"""Zabbix 6.0 behaviour (server 6.0.25): API shapes, auth and import rules against a strict 6.0 fake.

The fake enforces what the 6.0 API source enforces (CConfiguration.php:205-270, CHost.php, CLocalApiClient.php),
so a request the real 6.0 server would reject fails here instead of silently passing.
"""

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from promabbix.cli import sync_template as cli_mod
from promabbix.promabbix import cli
from promabbix.zabbix.client import WRITE_METHODS, ZabbixClient
from promabbix.zabbix.sync import build_import_rules, sync_pseudo_hosts, sync_template
from tests.zabbix60_export import export_60
from tests.zabbix_fake import RULES_60, FakeZabbix, fake_template_doc, version_tuple

VERSION = "6.0.25"
TEMPLATE = "templ_module_promt_svc"
EXAMPLE = Path(__file__).parent.parent / "examples" / "minikube-alert-config.yaml"
CREDS = ("--zabbix-url", "https://zbx.example.com", "--zabbix-user", "svc", "--zabbix-password", "secret")


def client_for(fake: FakeZabbix, **kw):
    return ZabbixClient("https://zbx.example.com", "svc", "secret", transport=fake, **kw)


def config(*hosts):
    return {"zabbix": {"template": "svc", "hosts": list(hosts)}}


def host_entry(name="svc-prod", **extra):
    entry = {"host_name": name, "visible_name": "Svc " + name, "host_groups": ["Kubernetes"],
             "link_templates": [TEMPLATE]}
    entry.update(extra)
    return entry


@pytest.fixture
def fake60():
    f = FakeZabbix(version=VERSION, groups=["New host maitenance", "Kubernetes"])
    f.templates[TEMPLATE] = "9"
    return f


class TestFakeIsStrict:
    """The fake itself: guards against it becoming permissive again."""

    def test_version_comparison_is_numeric(self):
        assert version_tuple("10.0.1") > version_tuple("6.2.0")
        assert version_tuple("6.0.25") < (6, 2)

    def test_import_rejects_unknown_rule_key(self):
        fake = FakeZabbix(version=VERSION)
        rules = {"items": {"createMissing": True}, "template_groups": {"createMissing": True}}
        resp = _raw(fake, "configuration.import", {"format": "json", "rules": rules, "source": "{}"}, auth="tok-123")
        assert "unexpected parameter \"template_groups\"" in resp["error"]["data"]

    def test_import_rejects_flag_not_allowed_for_key(self):
        fake = FakeZabbix(version=VERSION)
        rules = {"groups": {"createMissing": True, "deleteMissing": True}}
        resp = _raw(fake, "configuration.import", {"format": "json", "rules": rules, "source": "{}"}, auth="tok-123")
        assert "unexpected parameter \"deleteMissing\"" in resp["error"]["data"]

    def test_import_accepts_the_60_rules(self):
        assert set(build_import_rules((6, 0))) <= set(RULES_60)
        fake = FakeZabbix(version=VERSION)
        resp = _raw(fake, "configuration.import", {"format": "json", "rules": build_import_rules((6, 0)),
                                                   "source": json.dumps(fake_template_doc(TEMPLATE))},
                    auth="tok-123")
        assert resp["result"] is True

    def test_host_get_rejects_select_host_groups_below_62(self):
        fake = FakeZabbix(version=VERSION)
        resp = _raw(fake, "host.get", {"filter": {"host": ["x"]}, "selectHostGroups": ["groupid"]},
                    auth="tok-123")
        assert "selectHostGroups" in resp["error"]["data"]

    def test_auth_value_rejected_on_unauthenticated_methods(self):
        fake = FakeZabbix(version=VERSION)
        assert "without the \"auth\"" in _raw(fake, "apiinfo.version", {}, auth="x")["error"]["data"]
        assert "without the \"auth\"" in _raw(fake, "user.login", {"user": "svc", "password": "secret"},
                                              auth="x")["error"]["data"]

    def test_authenticated_method_without_session_is_refused(self):
        fake = FakeZabbix(version=VERSION)
        assert _raw(fake, "template.get", {"filter": {"host": []}})["error"]["message"] == "Not authorized."

    def test_60_ignores_the_bearer_header(self):
        fake = FakeZabbix(version=VERSION)
        resp = _raw(fake, "template.get", {"filter": {"host": []}}, headers={"Authorization": "Bearer tok-123"})
        assert resp["error"]["message"] == "Not authorized."

    def test_export_of_60_server_has_groups_and_version_60(self):
        fake = FakeZabbix(version=VERSION)
        doc = fake_template_doc(TEMPLATE)
        doc["zabbix_export"]["template_groups"] = doc["zabbix_export"].pop("groups")
        doc["zabbix_export"]["version"] = "7.0"
        fake.add_live_template(doc)
        exported = json.loads(_raw(fake, "configuration.export", {"options": {"templates": [fake.templates[TEMPLATE]]},
                                                                 "format": "json"}, auth="tok-123")["result"])
        assert exported["zabbix_export"]["version"] == "6.0"
        assert "groups" in exported["zabbix_export"] and "template_groups" not in exported["zabbix_export"]

    def test_export_of_70_server_has_template_groups(self):
        fake = FakeZabbix(version="7.0.5")
        fake.add_live_template(fake_template_doc(TEMPLATE))
        exported = json.loads(_raw(fake, "configuration.export", {"options": {"templates": [fake.templates[TEMPLATE]]},
                                                                 "format": "json"}, auth="tok-123")["result"])
        assert exported["zabbix_export"]["version"] == "7.0"
        assert "template_groups" in exported["zabbix_export"] and "groups" not in exported["zabbix_export"]


def _raw(fake: FakeZabbix, method: str, params, auth=None, headers=None):
    import urllib.request
    body = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    if auth is not None:
        body["auth"] = auth
    req = urllib.request.Request("https://zbx.example.com/api_jsonrpc.php", data=json.dumps(body).encode(),
                                 headers=headers or {}, method="POST")
    return json.loads(fake(req, 5.0))


class TestClient60:
    def test_write_calls_carry_body_auth_and_no_bearer_header(self, fake60):
        sync_pseudo_hosts(config(host_entry()), client_for(fake60), dry_run=False)
        writes = fake60.write_calls
        assert [c["method"] for c in writes] == ["host.create"]
        for call in writes:
            assert call["auth"] == "tok-123"
            assert "authorization" not in call["headers"]

    def test_login_and_version_calls_carry_no_auth(self, fake60):
        sync_pseudo_hosts(config(host_entry()), client_for(fake60), dry_run=True)
        for call in fake60.calls_of("apiinfo.version") + fake60.calls_of("user.login"):
            assert call["auth"] is None and "authorization" not in call["headers"]
        assert fake60.calls_of("user.login")[0]["params"] == {"user": "svc", "password": "secret"}

    def test_import_write_carries_body_auth(self):
        fake60 = FakeZabbix(version=VERSION)
        sync_template(fake_template_doc(TEMPLATE), client_for(fake60), dry_run=False)
        call = fake60.calls_of("configuration.import")[0]
        assert call["auth"] == "tok-123" and "authorization" not in call["headers"]
        assert call["params"]["rules"] == build_import_rules("6.0.25")  # accepted by the strict fake


class TestHosts60:
    def test_host_get_sends_select_groups_not_select_host_groups(self, fake60):
        sync_pseudo_hosts(config(host_entry()), client_for(fake60), dry_run=True)
        params = fake60.calls_of("host.get")[0]["params"]
        assert params["selectGroups"] == ["groupid", "name"]
        assert "selectHostGroups" not in params
        assert "proxy_hostid" in params["output"] and "proxyid" not in params["output"]

    def test_proxy_get_requests_host(self, fake60):
        sync_pseudo_hosts(config(host_entry()), client_for(fake60), dry_run=True)
        assert fake60.calls_of("proxy.get")[0]["params"]["output"] == ["proxyid", "host"]

    def test_host_create_uses_proxy_hostid(self, fake60):
        sync_pseudo_hosts(config(host_entry()), client_for(fake60), dry_run=False)
        params = fake60.calls_of("host.create")[0]["params"]
        assert params["proxy_hostid"] == fake60.proxies["gce-infra-zabbix-proxy-pgsql-2"]
        assert "proxyid" not in params and "monitored_by" not in params
        assert params["groups"] == [{"groupid": fake60.groups["Kubernetes"]}]

    def test_second_run_is_idempotent(self, fake60):
        cfg = config(host_entry())
        sync_pseudo_hosts(cfg, client_for(fake60), dry_run=False)
        again = sync_pseudo_hosts(cfg, client_for(fake60), dry_run=False)
        assert [h.action for h in again.hosts] == ["unchanged"]
        assert fake60.calls_of("host.update") == []


class TestTemplate60:
    def test_second_sync_of_the_rendered_template_is_skipped_against_a_60_export(self, fake60, tmp_path):
        """PM-6 end to end on a 6.0 server: the stored template is returned as a 6.0 export (groups, defaults
        omitted, LLD filter renumbered) and the next sync must not import again."""
        fixtures = Path(__file__).parent / "fixtures" / "zabbix_diff"
        from promabbix.cli.generate_template import GenerateTemplateCommand
        out = tmp_path / "t.json"
        assert GenerateTemplateCommand().execute(str(fixtures / "service_alerts_lld_filter.yaml"), str(out), None,
                                                 "prometheus_alert_rules_to_zbx_template.j2", False) == 0
        desired = json.loads(out.read_text())
        name = desired["zabbix_export"]["templates"][0]["template"]
        fake = FakeZabbix(version=VERSION)
        first = sync_template(desired, client_for(fake), dry_run=False)
        assert first.imported
        # what the 6.0 server would hand back for what it stored
        fake.exports[name] = export_60(desired)
        second = sync_template(desired, client_for(fake), dry_run=False)
        assert not second.has_changes and not second.imported
        assert len(fake.calls_of("configuration.import")) == 1


class TestCli60:
    @pytest.fixture
    def home(self, tmp_path, monkeypatch):
        h = tmp_path / "home"
        h.mkdir()
        monkeypatch.setenv("HOME", str(h))
        for k in ("ZABBIX_URL", "ZABBIX_USER", "ZABBIX_PASSWORD"):
            monkeypatch.delenv(k, raising=False)
        return h

    @pytest.fixture
    def fake(self, monkeypatch, home):
        f = FakeZabbix(version=VERSION, groups=["New host maitenance", "Kubernetes"])

        def factory(url, user, password, timeout, read_only):
            return ZabbixClient(url, user, password, timeout=timeout, read_only=read_only, transport=f)

        monkeypatch.setattr(cli_mod, "_default_client_factory", factory)
        return f

    @pytest.fixture
    def cfg(self, tmp_path):
        p = tmp_path / "svc.yaml"
        shutil.copy(EXAMPLE, p)
        return str(p)

    def invoke(self, *args):
        return CliRunner(mix_stderr=False).invoke(cli, list(args), catch_exceptions=False)

    def test_sync_pseudo_hosts_dry_run_against_60(self, fake, cfg):
        r = self.invoke("syncPseudoHosts", cfg, "--dry-run", *CREDS)
        assert r.exit_code == 0, r.stderr
        assert fake.write_calls == [] and not (set(fake.methods) & WRITE_METHODS)
        assert "would create" in r.stdout and "host minikube: would create" in r.stdout
        host_get = fake.calls_of("host.get")[0]["params"]
        assert "selectGroups" in host_get and "selectHostGroups" not in host_get
        assert all(c["auth"] in (None, "tok-123") and "authorization" not in c["headers"] for c in fake.calls)

    def test_real_run_then_dry_run_converges_on_60(self, fake, cfg):
        r = self.invoke("syncPseudoHosts", cfg, *CREDS)
        assert r.exit_code == 0, r.stderr
        assert fake.calls_of("host.create")[0]["params"]["proxy_hostid"] == fake.proxies["gce-infra-zabbix-proxy-pgsql-2"]
        writes = len(fake.write_calls)
        again = self.invoke("syncPseudoHosts", cfg, "--dry-run", "--exit-code", *CREDS)
        assert again.exit_code == 0, again.stdout
        assert len(fake.write_calls) == writes and "would" not in again.stdout
