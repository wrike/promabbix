# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#
"""Sync tests: import rules, host defaults, idempotency, failure isolation, and zero writes in dry-run."""

import copy
import json

import pytest

from promabbix.zabbix import sync as sync_mod
from promabbix.zabbix.client import WRITE_METHODS, ZabbixAPIError, ZabbixClient
from promabbix.zabbix.sync import (DryRunWriteError, SyncError, _version_tuple, build_desired_host,
                                   build_import_rules, sync_pseudo_hosts, sync_service, sync_template)
from tests.zabbix_fake import FakeZabbix, fake_template_doc

TEMPLATE = "templ_module_promt_svc"
AUTH = {"createMissing": True, "updateExisting": True, "deleteMissing": True}

EXPECTED_RULES_V7 = {
    "items": AUTH, "discoveryRules": AUTH, "graphs": AUTH, "httptests": AUTH, "triggers": AUTH,
    "templates": {"createMissing": True, "updateExisting": True},
    "host_groups": {"createMissing": True},
    "template_groups": {"createMissing": True},
    "templateLinkage": {"createMissing": True, "deleteMissing": True},
    "templateDashboards": AUTH,
    "valueMaps": {"createMissing": True, "updateExisting": True},
}

# Literal copies of the `update_rules` dict that community.zabbix 1.9.3 (zabbix_template.py, import_template())
# sends after its version switches, for Zabbix 7.0 and 6.0. Do not "simplify" these: they are the parity oracle.
CZ_193_RULES_7_0 = {
    "discoveryRules": {"createMissing": True, "updateExisting": True, "deleteMissing": True},
    "graphs": {"createMissing": True, "updateExisting": True, "deleteMissing": True},
    "host_groups": {"createMissing": True},
    "httptests": {"createMissing": True, "updateExisting": True, "deleteMissing": True},
    "items": {"createMissing": True, "updateExisting": True, "deleteMissing": True},
    "templates": {"createMissing": True, "updateExisting": True},
    "template_groups": {"createMissing": True},
    "templateLinkage": {"createMissing": True, "deleteMissing": True},
    "templateDashboards": {"createMissing": True, "updateExisting": True, "deleteMissing": True},
    "triggers": {"createMissing": True, "updateExisting": True, "deleteMissing": True},
    "valueMaps": {"createMissing": True, "updateExisting": True},
}
CZ_193_RULES_6_0 = {
    "discoveryRules": {"createMissing": True, "updateExisting": True, "deleteMissing": True},
    "graphs": {"createMissing": True, "updateExisting": True, "deleteMissing": True},
    "groups": {"createMissing": True},
    "httptests": {"createMissing": True, "updateExisting": True, "deleteMissing": True},
    "items": {"createMissing": True, "updateExisting": True, "deleteMissing": True},
    "templates": {"createMissing": True, "updateExisting": True},
    "templateLinkage": {"createMissing": True, "deleteMissing": True},
    "templateDashboards": {"createMissing": True, "updateExisting": True, "deleteMissing": True},
    "triggers": {"createMissing": True, "updateExisting": True, "deleteMissing": True},
    "valueMaps": {"createMissing": True, "updateExisting": True},
}

DEFAULT_IFACE = {"type": 1, "main": 1, "useip": 1, "ip": "127.0.0.1", "dns": "", "port": "10050"}


def client_for(fake, read_only=False):
    return ZabbixClient("https://zbx.example.com", "svc", "secret", transport=fake, read_only=read_only)


def config(*hosts):
    return {"zabbix": {"template": "svc", "hosts": list(hosts)}}


def host_entry(name="svc-prod", **extra):
    entry = {"host_name": name, "visible_name": "Svc " + name, "host_groups": ["Kubernetes"],
             "link_templates": [TEMPLATE]}
    entry.update(extra)
    return entry


@pytest.fixture
def fake():
    return FakeZabbix()


# ------------------------------------------------------------------------------------------- import rules

class TestImportRules:
    def test_rules_exact_v7(self):
        assert build_import_rules((7, 0)) == EXPECTED_RULES_V7

    def test_rules_exact_62(self):
        assert build_import_rules((6, 2)) == EXPECTED_RULES_V7

    def test_rules_pre_62_use_groups(self):
        rules = build_import_rules((6, 0))
        assert rules["groups"] == {"createMissing": True}
        assert "host_groups" not in rules and "template_groups" not in rules
        assert {k: v for k, v in rules.items() if k != "groups"} == {
            k: v for k, v in EXPECTED_RULES_V7.items() if k not in ("host_groups", "template_groups")}

    def test_rules_identical_to_community_zabbix_193(self):
        assert build_import_rules((7, 0)) == CZ_193_RULES_7_0
        assert build_import_rules((6, 0)) == CZ_193_RULES_6_0
        assert build_import_rules((7, 0, 5)) == CZ_193_RULES_7_0  # patch level is accepted

    def test_deletemissing_only_where_authoritative(self):
        rules = build_import_rules((7, 0))
        assert {k for k, v in rules.items() if v.get("deleteMissing")} == {
            "items", "discoveryRules", "graphs", "httptests", "triggers", "templateLinkage", "templateDashboards"}

    def test_value_maps_and_templates_are_never_deleted(self):
        rules = build_import_rules((7, 0))
        assert "deleteMissing" not in rules["valueMaps"] and "deleteMissing" not in rules["templates"]

    @pytest.mark.parametrize("version,linkage_delete", [
        ((4, 0, 15), False), ((4, 0, 16), True), ((4, 2), False), ((4, 2, 8), False),
        ((4, 4, 3), False), ((4, 4, 4), True), ((5, 0), True), ((6, 0), True)])
    def test_template_linkage_delete_missing_follows_version(self, version, linkage_delete):
        assert build_import_rules(version)["templateLinkage"].get("deleteMissing", False) is linkage_delete

    @pytest.mark.parametrize("version,screens,dashboards,applications", [
        ((3, 2), True, False, True), ((4, 4, 4), True, False, True), ((5, 0), True, False, True),
        ((5, 2), False, True, True), ((5, 4), False, True, False), ((6, 0), False, True, False)])
    def test_screens_dashboards_and_applications_follow_version(self, version, screens, dashboards, applications):
        rules = build_import_rules(version)
        assert ("templateScreens" in rules) is screens
        assert ("templateDashboards" in rules) is dashboards
        assert ("applications" in rules) is applications
        if screens:
            assert rules["templateScreens"] == AUTH
        if dashboards:
            assert rules["templateDashboards"] == AUTH

    def test_applications_update_existing_only_up_to_3_2(self):
        assert build_import_rules((3, 2))["applications"] == {
            "createMissing": True, "deleteMissing": True, "updateExisting": True}
        assert build_import_rules((4, 0, 20))["applications"] == {"createMissing": True, "deleteMissing": True}

    def test_unparseable_version_is_refused_before_any_write(self, fake):
        fake.version = "garbage"
        with pytest.raises(ZabbixAPIError):
            sync_template(fake_template_doc(TEMPLATE), client_for(fake), dry_run=False)
        assert fake.write_calls == []

    def test_version_tuple_keeps_patch_level_and_drops_suffix(self):
        assert _version_tuple("7.0.5") == (7, 0, 5)
        assert _version_tuple("6.4.0rc1") == (6, 4, 0)
        assert _version_tuple("5.0") == (5, 0)
        with pytest.raises(SyncError):
            _version_tuple("7")

    def test_import_call_params_exact(self, fake):
        desired = fake_template_doc(TEMPLATE)
        result = sync_template(desired, client_for(fake), dry_run=False)
        imports = fake.calls_of("configuration.import")
        assert len(imports) == 1
        params = imports[0]["params"]
        assert set(params) == {"format", "rules", "source"}
        assert params["format"] == "json"
        assert params["rules"] == EXPECTED_RULES_V7
        assert json.loads(params["source"]) == desired
        assert result.imported and not result.exists

    def test_accepts_json_string(self, fake):
        desired = fake_template_doc(TEMPLATE)
        sync_template(json.dumps(desired), client_for(fake), dry_run=False)
        assert json.loads(fake.calls_of("configuration.import")[0]["params"]["source"]) == desired

    def test_accepts_a_version_string(self):
        assert build_import_rules("6.0.25") == CZ_193_RULES_6_0
        assert build_import_rules("7.0.5") == CZ_193_RULES_7_0
        assert build_import_rules("6.4.0rc1") == build_import_rules((6, 4, 0))

    def test_rejects_an_unparseable_version_string(self):
        with pytest.raises(SyncError):
            build_import_rules("seven")

    def test_rules_follow_server_version(self):
        fake = FakeZabbix(version="6.0.10")
        sync_template(fake_template_doc(TEMPLATE), client_for(fake), dry_run=False)
        assert fake.calls_of("configuration.import")[0]["params"]["rules"] == CZ_193_RULES_6_0


# --------------------------------------------------------------------------------------------- template

class TestSyncTemplate:
    def test_looks_up_live_by_host_name_then_exports(self, fake):
        live = fake_template_doc(TEMPLATE)
        fake.add_live_template(live)
        sync_template(live, client_for(fake), dry_run=True)
        assert fake.calls_of("template.get")[0]["params"]["filter"] == {"host": [TEMPLATE]}
        export = fake.calls_of("configuration.export")[0]["params"]
        assert export["options"] == {"templates": [fake.templates[TEMPLATE]]} and export["format"] == "json"

    def test_unchanged_is_not_imported(self, fake):
        live = fake_template_doc(TEMPLATE)
        fake.add_live_template(live)
        desired = copy.deepcopy(live)
        desired["zabbix_export"]["date"] = "2030-01-01T00:00:00Z"  # volatile; must not matter
        result = sync_template(desired, client_for(fake), dry_run=False)
        assert fake.write_calls == [] and not result.imported and not result.has_changes

    def test_live_only_template_link_and_dashboard_are_reported_as_removals_in_dry_run(self, fake):
        live = fake_template_doc(TEMPLATE)
        live["zabbix_export"]["templates"][0]["templates"] = [{"name": "Linked by hand"}]
        live["zabbix_export"]["templates"][0]["dashboards"] = [{"name": "Hand made dashboard"}]
        fake.add_live_template(live)
        result = sync_template(fake_template_doc(TEMPLATE), client_for(fake, read_only=True), dry_run=True)
        text = sync_mod.render_template_result(result, dry_run=True)
        assert result.has_changes and result.removals == 2
        assert '!!! REMOVE linked_template "Linked by hand"' in text
        assert '!!! REMOVE dashboard "Hand made dashboard"' in text
        assert "2 REMOVAL(S)" in text
        assert fake.write_calls == []

    def test_real_run_sends_the_rules_that_delete_those_links_and_dashboards(self, fake):
        live = fake_template_doc(TEMPLATE)
        live["zabbix_export"]["templates"][0]["templates"] = [{"name": "Linked by hand"}]
        fake.add_live_template(live)
        sync_template(fake_template_doc(TEMPLATE), client_for(fake), dry_run=False)
        rules = fake.calls_of("configuration.import")[0]["params"]["rules"]
        assert rules["templateLinkage"]["deleteMissing"] is True
        assert rules["templateDashboards"]["deleteMissing"] is True

    def test_changed_is_imported_and_reports_removals(self, fake):
        fake.add_live_template(fake_template_doc(TEMPLATE, items=("a", "b", "c")))
        desired = fake_template_doc(TEMPLATE, items=("a", "b"))
        result = sync_template(desired, client_for(fake), dry_run=False)
        assert result.imported and result.has_changes and result.exists
        assert result.removals >= 1  # item c and trigger c disappear => deleteMissing deletes them
        assert len(fake.calls_of("configuration.import")) == 1

    def test_second_sync_after_import_is_noop(self, fake):
        desired = fake_template_doc(TEMPLATE)
        sync_template(desired, client_for(fake), dry_run=False)
        sync_template(desired, client_for(fake), dry_run=False)
        assert len(fake.calls_of("configuration.import")) == 1

    def test_invalid_inputs(self, fake):
        with pytest.raises(SyncError, match="not valid JSON"):
            sync_template("{nope", client_for(fake), dry_run=True)
        with pytest.raises(SyncError, match="no zabbix_export.templates"):
            sync_template({"zabbix_export": {}}, client_for(fake), dry_run=True)
        assert fake.calls == []

    def test_export_returning_garbage(self, fake):
        fake.add_live_template(fake_template_doc(TEMPLATE))
        fake._m_configuration_export = lambda p: "not json"  # type: ignore[method-assign]
        with pytest.raises(SyncError, match="valid JSON"):
            sync_template(fake_template_doc(TEMPLATE), client_for(fake), dry_run=False)
        assert fake.write_calls == []

    def test_import_api_error_propagates(self, fake):
        fake.errors["configuration.import"] = (-32500, "Application error.", "bad template")
        with pytest.raises(ZabbixAPIError, match="bad template"):
            sync_template(fake_template_doc(TEMPLATE), client_for(fake), dry_run=False)

    def test_write_guard_refuses_unregistered_method(self, fake):
        with pytest.raises(SyncError, match="not a registered write method"):
            sync_mod._write(client_for(fake), False, "host.get", {})

    def test_write_guard_refuses_in_dry_run(self, fake):
        with pytest.raises(DryRunWriteError):
            sync_mod._write(client_for(fake), True, "host.update", {})
        assert fake.calls == []


# ----------------------------------------------------------------------------------- dry-run: zero writes

class TestDryRunNeverWrites:
    def assert_no_writes(self, fake):
        assert fake.write_calls == [], f"write RPCs in dry-run: {[c['method'] for c in fake.write_calls]}"
        assert not (set(fake.methods) & WRITE_METHODS)

    def test_template_missing_live(self, fake):
        r = sync_template(fake_template_doc(TEMPLATE), client_for(fake, read_only=True), dry_run=True)
        assert r.has_changes and not r.exists and not r.imported
        self.assert_no_writes(fake)

    def test_template_unchanged(self, fake):
        fake.add_live_template(fake_template_doc(TEMPLATE))
        r = sync_template(fake_template_doc(TEMPLATE), client_for(fake, read_only=True), dry_run=True)
        assert not r.has_changes
        self.assert_no_writes(fake)

    def test_template_changed(self, fake):
        fake.add_live_template(fake_template_doc(TEMPLATE, items=("a", "b", "c")))
        r = sync_template(fake_template_doc(TEMPLATE, items=("a",)), client_for(fake, read_only=True), dry_run=True)
        assert r.has_changes and r.removals >= 1 and not r.imported
        self.assert_no_writes(fake)

    def test_host_missing(self, fake):
        fake.templates[TEMPLATE] = "9"
        r = sync_pseudo_hosts(config(host_entry()), client_for(fake, read_only=True), dry_run=True)
        assert [(h.action, h.applied) for h in r.hosts] == [("create", False)]
        assert fake.hosts == {}
        self.assert_no_writes(fake)

    def test_host_missing_and_template_not_yet_created(self, fake):
        r = sync_pseudo_hosts(config(host_entry()), client_for(fake, read_only=True), dry_run=True)
        assert r.hosts[0].action == "create"
        self.assert_no_writes(fake)

    def test_host_differs(self, fake):
        fake.templates[TEMPLATE] = "9"
        sync_pseudo_hosts(config(host_entry()), client_for(fake), dry_run=False)
        before = len(fake.write_calls)
        changed = host_entry(description="new description", host_groups=["Kubernetes", "Production hosts"])
        r = sync_pseudo_hosts(config(changed), client_for(fake, read_only=True), dry_run=True)
        assert r.hosts[0].action == "update" and not r.hosts[0].applied
        assert len(fake.write_calls) == before
        assert fake.hosts["svc-prod"]["description"] == ""

    def test_host_state_absent(self, fake):
        fake.templates[TEMPLATE] = "9"
        sync_pseudo_hosts(config(host_entry()), client_for(fake), dry_run=False)
        before = len(fake.write_calls)
        r = sync_pseudo_hosts(config(host_entry(state="absent")), client_for(fake, read_only=True), dry_run=True)
        assert r.hosts[0].action == "delete" and "svc-prod" in fake.hosts
        assert len(fake.write_calls) == before

    def test_api_error_mid_way_in_template(self, fake):
        fake.add_live_template(fake_template_doc(TEMPLATE))
        fake.errors["configuration.export"] = (-32500, "Application error.", "boom")
        with pytest.raises(ZabbixAPIError):
            sync_template(fake_template_doc(TEMPLATE, items=("z",)), client_for(fake, read_only=True), dry_run=True)
        self.assert_no_writes(fake)

    def test_api_error_mid_way_in_hosts(self, fake):
        fake.templates[TEMPLATE] = "9"
        fake.errors["host.get"] = lambda p: (-32500, "Application error.", "db down") if p["filter"]["host"] == ["bad"] else None
        r = sync_pseudo_hosts(config(host_entry("ok1"), host_entry("bad"), host_entry("ok2")),
                              client_for(fake, read_only=True), dry_run=True)
        assert [h.action for h in r.hosts] == ["create", "failed", "create"]
        self.assert_no_writes(fake)

    def test_full_service_all_paths(self, fake):
        cfg = config(host_entry("a"), host_entry("b"))
        r = sync_service(cfg, fake_template_doc(TEMPLATE), client_for(fake, read_only=True), dry_run=True)
        assert r.has_changes and not r.failed
        self.assert_no_writes(fake)

    def test_service_template_failure_in_dry_run(self, fake):
        fake.errors["template.get"] = (-32500, "Application error.", "nope")
        r = sync_service(config(host_entry()), fake_template_doc(TEMPLATE), client_for(fake, read_only=True), dry_run=True)
        assert r.failed and r.hosts.hosts == []
        self.assert_no_writes(fake)

    def test_login_failure_makes_no_writes(self):
        fake = FakeZabbix(password="other")
        with pytest.raises(ZabbixAPIError):
            sync_template(fake_template_doc(TEMPLATE), client_for(fake, read_only=True), dry_run=True)
        self.assert_no_writes(fake)

    def test_dry_run_even_with_writable_client_never_writes(self, fake):
        fake.add_live_template(fake_template_doc(TEMPLATE, items=("a", "b", "c")))
        sync_service(config(host_entry()), fake_template_doc(TEMPLATE, items=("a",)), client_for(fake), dry_run=True)
        self.assert_no_writes(fake)


# --------------------------------------------------------------------------------------------- hosts

class TestHostDefaults:
    def test_defaults_exact(self):
        d = build_desired_host({"host_name": "h", "visible_name": "H", "link_templates": [TEMPLATE]})
        assert d == {
            "host_name": "h", "visible_name": "H", "description": "",
            "host_groups": ["New host maitenance"], "link_templates": [TEMPLATE], "status": "enabled",
            "proxy": "gce-infra-zabbix-proxy-pgsql-2", "macros": [], "interfaces": [DEFAULT_IFACE],
        }

    def test_overrides_win(self):
        d = build_desired_host({"host_name": "h", "visible_name": "H", "link_templates": [], "description": "d",
                                "host_groups": ["Kubernetes"], "status": "disabled", "proxy": "other-proxy",
                                "macros": [{"macro": "{$A}", "value": 5}]})
        assert (d["description"], d["host_groups"], d["status"], d["proxy"]) == ("d", ["Kubernetes"], "disabled", "other-proxy")
        assert d["macros"] == [{"macro": "{$A}", "value": "5", "description": ""}]

    def test_explicit_null_proxy_means_no_proxy(self):
        assert build_desired_host({"host_name": "h", "visible_name": "H", "link_templates": [], "proxy": None})["proxy"] is None

    def test_defaults_do_not_alias_module_constants(self):
        d = build_desired_host({"host_name": "h", "visible_name": "H", "link_templates": []})
        d["host_groups"].append("x")
        d["interfaces"][0]["ip"] = "1.1.1.1"
        again = build_desired_host({"host_name": "h", "visible_name": "H", "link_templates": []})
        assert again["host_groups"] == ["New host maitenance"] and again["interfaces"] == [DEFAULT_IFACE]

    def test_host_create_params_exact_v7(self, fake):
        fake.templates[TEMPLATE] = "42"
        sync_pseudo_hosts(config({"host_name": "h1", "visible_name": "H One", "link_templates": [TEMPLATE]}),
                          client_for(fake), dry_run=False)
        creates = fake.calls_of("host.create")
        assert len(creates) == 1
        assert creates[0]["params"] == {
            "host": "h1", "name": "H One", "description": "", "status": 0,
            "groups": [{"groupid": fake.groups["New host maitenance"]}],
            "templates": [{"templateid": "42"}], "macros": [],
            "interfaces": [DEFAULT_IFACE],
            "monitored_by": 1, "proxyid": fake.proxies["gce-infra-zabbix-proxy-pgsql-2"],
        }

    def test_host_create_params_pre_7_use_proxy_hostid(self):
        fake = FakeZabbix(version="6.4.3")
        fake.templates[TEMPLATE] = "42"
        sync_pseudo_hosts(config(host_entry()), client_for(fake), dry_run=False)
        p = fake.calls_of("host.create")[0]["params"]
        assert p["proxy_hostid"] == fake.proxies["gce-infra-zabbix-proxy-pgsql-2"]
        assert "proxyid" not in p and "monitored_by" not in p
        assert "selectHostGroups" in fake.calls_of("host.get")[0]["params"]

    def test_disabled_host_and_macros_sent(self, fake):
        fake.templates[TEMPLATE] = "42"
        sync_pseudo_hosts(config(host_entry(status="disabled", macros=[{"macro": "{$X}", "value": "1", "description": "d"}])),
                          client_for(fake), dry_run=False)
        p = fake.calls_of("host.create")[0]["params"]
        assert p["status"] == 1 and p["macros"] == [{"macro": "{$X}", "value": "1", "description": "d"}]

    def test_no_proxy_host(self, fake):
        fake.templates[TEMPLATE] = "42"
        sync_pseudo_hosts(config(host_entry(proxy=None)), client_for(fake), dry_run=False)
        p = fake.calls_of("host.create")[0]["params"]
        assert p["monitored_by"] == 0 and p["proxyid"] == "0"
        assert fake.calls_of("proxy.get") == []

    def test_no_hosts_makes_no_calls(self, fake):
        r = sync_pseudo_hosts({"zabbix": {"template": "x"}}, client_for(fake), dry_run=False)
        assert r.hosts == [] and fake.calls == []

    def test_missing_prerequisites_fail_the_host(self, fake):
        # template not in Zabbix, real run -> failure, not a silent unlinked host
        r = sync_pseudo_hosts(config(host_entry()), client_for(fake), dry_run=False)
        assert r.hosts[0].failed and "does not exist" in r.hosts[0].error
        assert fake.write_calls == []
        fake.templates[TEMPLATE] = "9"
        r = sync_pseudo_hosts(config(host_entry(host_groups=["Nope"])), client_for(fake), dry_run=False)
        assert "host group 'Nope'" in r.hosts[0].error
        r = sync_pseudo_hosts(config(host_entry(proxy="ghost")), client_for(fake), dry_run=False)
        assert "proxy 'ghost'" in r.hosts[0].error
        assert fake.write_calls == []


class TestHostIdempotency:
    def test_second_sync_makes_no_update(self, fake):
        fake.templates[TEMPLATE] = "9"
        cfg = config(host_entry(macros=[{"macro": "{$N}", "value": "60"}]), host_entry("svc-qa", status="disabled"))
        first = sync_pseudo_hosts(cfg, client_for(fake), dry_run=False)
        assert [h.action for h in first.hosts] == ["create", "create"]
        second = sync_pseudo_hosts(cfg, client_for(fake), dry_run=False)
        assert [h.action for h in second.hosts] == ["unchanged", "unchanged"]
        assert len(fake.calls_of("host.create")) == 2 and fake.calls_of("host.update") == []

    def test_idempotent_on_pre_7(self):
        fake = FakeZabbix(version="6.0.10")
        fake.templates[TEMPLATE] = "9"
        cfg = config(host_entry())
        sync_pseudo_hosts(cfg, client_for(fake), dry_run=False)
        sync_pseudo_hosts(cfg, client_for(fake), dry_run=False)
        assert fake.calls_of("host.update") == []

    def test_change_triggers_exactly_one_update_keeping_interface_id(self, fake):
        fake.templates[TEMPLATE] = "9"
        sync_pseudo_hosts(config(host_entry()), client_for(fake), dry_run=False)
        iface_id = fake.hosts["svc-prod"]["interfaces"][0]["interfaceid"]
        r = sync_pseudo_hosts(config(host_entry(description="changed")), client_for(fake), dry_run=False)
        assert r.hosts[0].action == "update" and r.hosts[0].applied
        updates = fake.calls_of("host.update")
        assert len(updates) == 1
        assert updates[0]["params"]["hostid"] == fake.hosts["svc-prod"]["hostid"]
        assert updates[0]["params"]["description"] == "changed"
        assert updates[0]["params"]["interfaces"][0]["interfaceid"] == iface_id
        assert "host" not in updates[0]["params"]
        again = sync_pseudo_hosts(config(host_entry(description="changed")), client_for(fake), dry_run=False)
        assert again.hosts[0].action == "unchanged"

    def test_drift_in_each_field_is_detected(self, fake):
        fake.templates[TEMPLATE] = "9"
        fake.templates["other"] = "10"
        sync_pseudo_hosts(config(host_entry()), client_for(fake), dry_run=False)
        variants = [dict(visible_name="Other"), dict(status="disabled"), dict(proxy="other-proxy"),
                    dict(host_groups=["Production hosts"]), dict(link_templates=["other"]),
                    dict(macros=[{"macro": "{$M}", "value": "1"}])]
        for v in variants:
            entry = host_entry()
            entry.update(v)
            assert sync_pseudo_hosts(config(entry), client_for(fake), dry_run=True).hosts[0].action == "update", v

    def test_absent_deletes_only_when_present(self, fake):
        fake.templates[TEMPLATE] = "9"
        assert sync_pseudo_hosts(config(host_entry(state="absent")), client_for(fake), dry_run=False).hosts[0].action == "unchanged"
        sync_pseudo_hosts(config(host_entry()), client_for(fake), dry_run=False)
        r = sync_pseudo_hosts(config(host_entry(state="absent")), client_for(fake), dry_run=False)
        assert r.hosts[0].action == "delete" and fake.hosts == {}
        assert len(fake.calls_of("host.delete")) == 1

    def test_live_host_with_drifted_interface_gets_fixed(self, fake):
        fake.templates[TEMPLATE] = "9"
        sync_pseudo_hosts(config(host_entry()), client_for(fake), dry_run=False)
        fake.hosts["svc-prod"]["interfaces"][0]["ip"] = "10.0.0.1"
        r = sync_pseudo_hosts(config(host_entry()), client_for(fake), dry_run=False)
        assert r.hosts[0].action == "update"
        assert fake.hosts["svc-prod"]["interfaces"][0]["ip"] == "127.0.0.1"


class TestPerHostFailureIsolation:
    def test_one_host_raises_others_still_processed(self, fake):
        fake.templates[TEMPLATE] = "9"
        fake.errors["host.create"] = lambda p: (-32500, "Application error.", "duplicate") if p["host"] == "bad" else None
        r = sync_pseudo_hosts(config(host_entry("ok1"), host_entry("bad"), host_entry("ok2")),
                              client_for(fake), dry_run=False)
        assert [(h.host_name, h.action) for h in r.hosts] == [("ok1", "create"), ("bad", "failed"), ("ok2", "create")]
        assert set(fake.hosts) == {"ok1", "ok2"}
        assert len(r.failures) == 1 and "duplicate" in r.failures[0].error and "ZabbixAPIError" in r.failures[0].error

    def test_non_api_exception_is_isolated_too(self, fake):
        fake.templates[TEMPLATE] = "9"
        r = sync_pseudo_hosts(config(host_entry("a"), {"visible_name": "no host name"}, host_entry("b")),
                              client_for(fake), dry_run=False)
        assert [h.action for h in r.hosts] == ["create", "failed", "create"]
        assert r.hosts[1].host_name == "<unnamed>"

    def test_non_dict_entry_is_isolated(self, fake):
        fake.templates[TEMPLATE] = "9"
        r = sync_pseudo_hosts(config("oops", host_entry("b")), client_for(fake), dry_run=False)
        assert [h.action for h in r.hosts] == ["failed", "create"]

    def test_service_hosts_skipped_when_template_fails(self, fake):
        fake.errors["configuration.import"] = (-32500, "Application error.", "bad")
        r = sync_service(config(host_entry()), fake_template_doc(TEMPLATE), client_for(fake), dry_run=False)
        assert r.failed and "hosts skipped" in r.error and fake.calls_of("host.create") == []

    def test_service_success_orders_template_before_hosts(self, fake):
        r = sync_service(config(host_entry()), fake_template_doc(TEMPLATE), client_for(fake), dry_run=False)
        assert not r.failed
        methods = fake.methods
        assert methods.index("configuration.import") < methods.index("host.create")
        assert fake.hosts["svc-prod"]["parentTemplates"][0]["host"] == TEMPLATE

    def test_service_second_run_is_all_noop(self, fake):
        cfg = config(host_entry())
        tpl = fake_template_doc(TEMPLATE)
        sync_service(cfg, tpl, client_for(fake), dry_run=False)
        writes = len(fake.write_calls)
        r = sync_service(cfg, tpl, client_for(fake), dry_run=False)
        assert not r.has_changes and len(fake.write_calls) == writes


class TestRendering:
    def test_render_flags_removals_and_dry_run_wording(self, fake):
        fake.add_live_template(fake_template_doc(TEMPLATE, items=("a", "b")))
        r = sync_service(config(host_entry()), fake_template_doc(TEMPLATE, items=("a",)), client_for(fake), dry_run=True)
        text = sync_mod.render_service_result(r, dry_run=True)
        assert "would update" in text and "REMOVAL" in text and "would create" in text
        assert "host svc-prod" in text

    def test_render_real_run_wording_and_failure(self, fake):
        fake.add_live_template(fake_template_doc(TEMPLATE, items=("old",)))
        fake.errors["host.create"] = (-32500, "Application error.", "dup")
        r = sync_service(config(host_entry()), fake_template_doc(TEMPLATE), client_for(fake), dry_run=False)
        text = sync_mod.render_service_result(r, dry_run=False)
        assert "template templ_module_promt_svc: updated" in text
        # the verbs are past tense; the engine's own diff text still says "would be DELETED"
        assert "would create" not in text and "would update" not in text
        assert "host svc-prod: FAILED" in text and "dup" in text
