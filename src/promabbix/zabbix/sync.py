#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#
"""Template and pseudo-host synchronisation against the Zabbix API.

Behaviour mirrors ``community.zabbix`` 1.9.3 (``zabbix_template`` / ``zabbix_host``) as used by the
``zbx_template.yml`` / ``zbx_host.yml`` playbooks, plus an export-compare step so unchanged objects are
never written. Every write goes through :func:`_write`, which refuses to run in dry-run mode.
"""

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from .client import WRITE_METHODS, ZabbixClient
from .diff import HostDiff, TemplateDiff, diff_host, diff_template

DEFAULT_HOST_GROUPS = ["New host maitenance"]  # sic: the existing Zabbix group name
DEFAULT_PROXY = "gce-infra-zabbix-proxy-pgsql-2"
DEFAULT_INTERFACE: Dict[str, Any] = {
    "type": 1, "main": 1, "useip": 1, "ip": "127.0.0.1", "dns": "", "port": "10050",
}

_AUTHORITATIVE = {"createMissing": True, "updateExisting": True, "deleteMissing": True}


class SyncError(Exception):
    """Sync could not proceed (bad input, missing prerequisite in Zabbix)."""


class DryRunWriteError(SyncError):
    """A write was attempted while dry-run is active. Always a bug."""


def _write(client: ZabbixClient, dry_run: bool, method: str, params: Any) -> Any:
    if method not in WRITE_METHODS:
        raise SyncError(f"{method} is not a registered write method")
    if dry_run:
        raise DryRunWriteError(f"refusing to call {method} in dry-run mode")
    return client.call(method, params)


def _version_tuple(version: str) -> Tuple[int, ...]:
    """``"7.0.5"`` -> ``(7, 0, 5)``; a suffix such as ``rc1`` is ignored."""
    parts = []
    for part in version.split("."):
        match = re.match(r"\d+", part)
        if match is None:
            break
        parts.append(int(match.group()))
        if match.end() != len(part):  # "0rc1": the numeric prefix is the last usable component
            break
    if len(parts) < 2:
        raise SyncError(f"unparseable Zabbix API version {version!r}")
    return tuple(parts)


def build_import_rules(version: Tuple[int, ...]) -> Dict[str, Dict[str, bool]]:
    """Import rules for the given Zabbix version, e.g. ``(7, 0)`` or ``(7, 0, 5)``.

    Parity reference: ``import_template()`` of community.zabbix 1.9.3
    (plugins/modules/zabbix_template.py). Same rules, same version switches, so a native import behaves
    exactly like the ``zbx_template.yml`` playbook it replaces. Notably ``deleteMissing`` is on for items,
    discovery rules, graphs, httptests, triggers, template linkage and template dashboards: whatever is
    not in the template JSON is deleted from Zabbix.
    """
    rules: Dict[str, Dict[str, bool]] = {
        "applications": {"createMissing": True, "deleteMissing": True},
        "discoveryRules": dict(_AUTHORITATIVE),
        "graphs": dict(_AUTHORITATIVE),
        "host_groups": {"createMissing": True},
        "httptests": dict(_AUTHORITATIVE),
        "items": dict(_AUTHORITATIVE),
        "templates": {"createMissing": True, "updateExisting": True},
        "template_groups": {"createMissing": True},
        "templateLinkage": {"createMissing": True},
        "templateScreens": dict(_AUTHORITATIVE),
        "triggers": dict(_AUTHORITATIVE),
        "valueMaps": {"createMissing": True, "updateExisting": True},
    }
    if version <= (3, 2):
        rules["applications"]["updateExisting"] = True
    # templateLinkage.deleteMissing: 4.0.16+ in the 4.0 branch, and 4.4.4+ (not in 4.2 or older 4.0)
    if version[:2] == (4, 0) and version >= (4, 0, 16):
        rules["templateLinkage"]["deleteMissing"] = True
    if version >= (4, 4, 4):
        rules["templateLinkage"]["deleteMissing"] = True
    if version >= (5, 2):  # templateScreens became templateDashboards
        rules["templateDashboards"] = rules.pop("templateScreens")
    if version >= (5, 4):  # applications are gone
        rules.pop("applications", None)
    if version < (6, 2):  # host and template groups were one "groups" parameter
        rules["groups"] = {"createMissing": True}
        rules.pop("host_groups", None)
        rules.pop("template_groups", None)
    return rules


# --------------------------------------------------------------------------------------------- templates

@dataclass
class TemplateResult:
    names: List[str]
    exists: bool
    diff: TemplateDiff
    imported: bool = False

    @property
    def has_changes(self) -> bool:
        return bool(self.diff.has_changes)

    @property
    def removals(self) -> int:
        return int(self.diff.removals)


def template_names(desired: Dict[str, Any]) -> List[str]:
    templates = (desired.get("zabbix_export") or {}).get("templates") or []
    names = [t["template"] for t in templates if isinstance(t, dict) and t.get("template")]
    if not names:
        raise SyncError("desired template JSON has no zabbix_export.templates[].template")
    return names


def fetch_live_template(client: ZabbixClient, names: List[str]) -> Optional[Dict[str, Any]]:
    """Export the live template(s) with the given technical names, or None when none exist."""
    found = client.call("template.get", {"output": ["templateid", "host"], "filter": {"host": names}})
    if not found:
        return None
    raw = client.call("configuration.export", {"options": {"templates": [t["templateid"] for t in found]},
                                               "format": "json"})
    try:
        exported = json.loads(raw)
    except (TypeError, ValueError) as e:
        raise SyncError("configuration.export did not return valid JSON") from e
    if not isinstance(exported, dict):
        raise SyncError("configuration.export returned an unexpected document")
    return exported


def sync_template(desired_template_json: Union[str, Dict[str, Any]], client: ZabbixClient,
                  dry_run: bool) -> TemplateResult:
    """Import the template unless the live export already matches. Never writes when ``dry_run``."""
    if isinstance(desired_template_json, str):
        try:
            desired = json.loads(desired_template_json)
        except ValueError as e:
            raise SyncError(f"desired template is not valid JSON: {e}") from e
        source = desired_template_json
    else:
        desired = desired_template_json
        source = json.dumps(desired)
    names = template_names(desired)
    live = fetch_live_template(client, names)
    diff = diff_template(live, desired)
    result = TemplateResult(names=names, exists=live is not None, diff=diff)
    if not diff.has_changes:  # PM-6: skip no-op imports (same decision as diff.should_import)
        return result
    if not dry_run:
        params = {"format": "json", "rules": build_import_rules(_version_tuple(client.api_version)), "source": source}
        _write(client, dry_run, "configuration.import", params)
        result.imported = True
    return result


# --------------------------------------------------------------------------------------------- hosts

@dataclass
class HostResult:
    host_name: str
    action: str  # create | update | delete | unchanged | failed
    diff_text: str = ""
    removals: int = 0
    applied: bool = False
    error: Optional[str] = None

    @property
    def has_changes(self) -> bool:
        return self.action in ("create", "update", "delete")

    @property
    def failed(self) -> bool:
        return self.action == "failed"


@dataclass
class HostsResult:
    hosts: List[HostResult] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(h.has_changes for h in self.hosts)

    @property
    def failures(self) -> List[HostResult]:
        return [h for h in self.hosts if h.failed]

    @property
    def removals(self) -> int:
        return sum(h.removals for h in self.hosts)


def _get(entry: Dict[str, Any], key: str, default: Any) -> Any:
    return copy.deepcopy(entry[key]) if key in entry else copy.deepcopy(default)


def normalize_macro(macro: Dict[str, Any]) -> Dict[str, str]:
    return {"macro": str(macro["macro"]), "value": str(macro.get("value", "")),
            "description": str(macro.get("description", ""))}


def build_desired_host(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Apply the zbx_host.yml defaults to one ``zabbix.hosts[]`` entry.

    The returned dict is what is handed to ``diff_host`` (live hosts are converted to the same shape):
    host_name, visible_name, description, host_groups, link_templates, status, proxy (name or None),
    macros ([{macro, value, description}]) and interfaces.
    """
    return {
        "host_name": entry["host_name"],
        "visible_name": entry["visible_name"],
        "description": _get(entry, "description", ""),
        "host_groups": _get(entry, "host_groups", DEFAULT_HOST_GROUPS),
        "link_templates": _get(entry, "link_templates", []),
        "status": _get(entry, "status", "enabled"),
        "proxy": _get(entry, "proxy", DEFAULT_PROXY),
        "macros": [normalize_macro(m) for m in _get(entry, "macros", [])],
        "interfaces": [dict(DEFAULT_INTERFACE)],
    }


class _Context:
    """Per-run API helper with lookup caches. All lookups are read-only."""

    def __init__(self, client: ZabbixClient, dry_run: bool) -> None:
        self.client = client
        self.dry_run = dry_run
        self.version = client.version
        self._groups: Dict[str, str] = {}
        self._templates: Dict[str, str] = {}
        self._proxies: Optional[Dict[str, str]] = None

    def write(self, method: str, params: Any) -> Any:
        return _write(self.client, self.dry_run, method, params)

    @property
    def proxy_id_field(self) -> str:
        return "proxyid" if self.version >= (7, 0) else "proxy_hostid"

    @property
    def groups_select(self) -> str:
        return "selectHostGroups" if self.version >= (6, 2) else "selectGroups"

    def proxies(self) -> Dict[str, str]:
        if self._proxies is None:
            name_key = "name" if self.version >= (7, 0) else "host"
            found = self.client.call("proxy.get", {"output": ["proxyid", name_key]})
            self._proxies = {p[name_key]: p["proxyid"] for p in found}
        return self._proxies

    def proxy_id(self, name: str) -> str:
        try:
            return self.proxies()[name]
        except KeyError:
            raise SyncError(f"proxy {name!r} does not exist in Zabbix") from None

    def proxy_name(self, proxy_id: Any) -> Optional[str]:
        if str(proxy_id or "0") == "0":
            return None
        for name, pid in self.proxies().items():
            if pid == str(proxy_id):
                return name
        raise SyncError(f"host is monitored by unknown proxy id {proxy_id}")

    def group_id(self, name: str) -> str:
        if name not in self._groups:
            found = self.client.call("hostgroup.get", {"output": ["groupid", "name"], "filter": {"name": [name]}})
            if not found:
                raise SyncError(f"host group {name!r} does not exist in Zabbix")
            self._groups[name] = found[0]["groupid"]
        return self._groups[name]

    def template_id(self, name: str) -> Optional[str]:
        if name not in self._templates:
            found = self.client.call("template.get", {"output": ["templateid", "host"], "filter": {"host": [name]}})
            if not found:
                return None
            self._templates[name] = found[0]["templateid"]
        return self._templates[name]


def _fetch_live_host(ctx: _Context, host_name: str) -> Optional[Dict[str, Any]]:
    params = {
        "filter": {"host": [host_name]},
        "output": ["hostid", "host", "name", "description", "status", ctx.proxy_id_field],
        "selectParentTemplates": ["templateid", "host"],
        ctx.groups_select: ["groupid", "name"],
        "selectMacros": ["hostmacroid", "macro", "value", "description", "type"],
        "selectInterfaces": ["interfaceid", "type", "main", "useip", "ip", "dns", "port"],
    }
    found = ctx.client.call("host.get", params)
    return found[0] if found else None


def _normalize_live_host(raw: Dict[str, Any], ctx: _Context) -> Dict[str, Any]:
    groups = raw.get("hostgroups", raw.get("groups", []))
    return {
        "host_name": raw["host"],
        "visible_name": raw.get("name") or raw["host"],
        "description": raw.get("description", ""),
        "host_groups": [g["name"] for g in groups],
        "link_templates": [t["host"] for t in raw.get("parentTemplates", [])],
        "status": "enabled" if str(raw.get("status", "0")) == "0" else "disabled",
        "proxy": ctx.proxy_name(raw.get(ctx.proxy_id_field)),
        "macros": [normalize_macro(m) for m in raw.get("macros", [])],
        "interfaces": [
            {"type": int(i["type"]), "main": int(i["main"]), "useip": int(i["useip"]),
             "ip": i["ip"], "dns": i["dns"], "port": str(i["port"])}
            for i in raw.get("interfaces", [])
        ],
    }


def _write_params(ctx: _Context, desired: Dict[str, Any], raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Parameters for host.create (raw is None) or host.update. Templates missing in Zabbix are skipped
    in dry-run only (the template may be about to be created); a real run fails instead."""
    templates = []
    for name in desired["link_templates"]:
        template_id = ctx.template_id(name)
        if template_id is None:
            if ctx.dry_run:
                continue
            raise SyncError(f"template {name!r} does not exist in Zabbix")
        templates.append({"templateid": template_id})
    interfaces = [dict(i) for i in desired["interfaces"]]
    if raw is not None and len(raw.get("interfaces", [])) == 1:
        interfaces[0]["interfaceid"] = raw["interfaces"][0]["interfaceid"]
    params: Dict[str, Any] = {
        "name": desired["visible_name"],
        "description": desired["description"],
        "status": 0 if desired["status"] == "enabled" else 1,
        "groups": [{"groupid": ctx.group_id(g)} for g in desired["host_groups"]],
        "templates": templates,
        "macros": desired["macros"],
        "interfaces": interfaces,
    }
    params.update(_proxy_params(ctx, desired["proxy"]))
    if raw is None:
        params["host"] = desired["host_name"]
    else:
        params["hostid"] = raw["hostid"]
    return params


def _proxy_params(ctx: _Context, proxy: Optional[str]) -> Dict[str, Any]:
    proxy_id = ctx.proxy_id(proxy) if proxy else "0"
    if ctx.version >= (7, 0):
        return {"monitored_by": 1 if proxy else 0, "proxyid": proxy_id}
    return {"proxy_hostid": proxy_id}


def _remove_host(ctx: _Context, host_name: str, raw: Optional[Dict[str, Any]]) -> HostResult:
    if raw is None:
        return HostResult(host_name, "unchanged")
    if not ctx.dry_run:
        ctx.write("host.delete", [raw["hostid"]])
    return HostResult(host_name, "delete", "- host would be deleted (state: absent)", 1, applied=not ctx.dry_run)


def _sync_host(ctx: _Context, entry: Dict[str, Any]) -> HostResult:
    desired = build_desired_host(entry)
    name = desired["host_name"]
    raw = _fetch_live_host(ctx, name)
    if entry.get("state", "present") == "absent":
        return _remove_host(ctx, name, raw)
    live = _normalize_live_host(raw, ctx) if raw is not None else None
    diff: HostDiff = diff_host(live, desired)
    if raw is not None and not diff.has_changes:
        return HostResult(name, "unchanged")
    params = _write_params(ctx, desired, raw)
    action = "create" if raw is None else "update"
    if not ctx.dry_run:
        ctx.write("host.create" if raw is None else "host.update", params)
    return HostResult(name, action, diff.render(), int(diff.removals), applied=not ctx.dry_run)


def sync_pseudo_hosts(config: Dict[str, Any], client: ZabbixClient, dry_run: bool) -> HostsResult:
    """Create/update every ``zabbix.hosts[]`` entry. A failing host is recorded and the batch continues."""
    entries = (config.get("zabbix") or {}).get("hosts") or []
    result = HostsResult()
    if not entries:
        return result
    ctx = _Context(client, dry_run)
    for entry in entries:
        name = str(entry.get("host_name", "<unnamed>")) if isinstance(entry, dict) else "<invalid>"
        try:
            result.hosts.append(_sync_host(ctx, entry))
        except Exception as e:  # noqa: BLE001 - deliberate per-host isolation
            result.hosts.append(HostResult(name, "failed", error=f"{type(e).__name__}: {e}"))
    return result


# --------------------------------------------------------------------------------------------- service

@dataclass
class ServiceResult:
    template: Optional[TemplateResult] = None
    hosts: HostsResult = field(default_factory=HostsResult)
    error: Optional[str] = None

    @property
    def failed(self) -> bool:
        return self.error is not None or bool(self.hosts.failures)

    @property
    def has_changes(self) -> bool:
        return (self.template is not None and self.template.has_changes) or self.hosts.has_changes

    @property
    def removals(self) -> int:
        return (self.template.removals if self.template else 0) + self.hosts.removals


def sync_service(config: Dict[str, Any], desired_template_json: Union[str, Dict[str, Any]],
                 client: ZabbixClient, dry_run: bool) -> ServiceResult:
    """syncTemplate followed by syncPseudoHosts for one service. Hosts are skipped if the template fails."""
    result = ServiceResult()
    try:
        result.template = sync_template(desired_template_json, client, dry_run)
    except Exception as e:  # noqa: BLE001
        result.error = f"template sync failed ({type(e).__name__}: {e}); hosts skipped"
        return result
    try:
        result.hosts = sync_pseudo_hosts(config, client, dry_run)
    except Exception as e:  # noqa: BLE001
        result.error = f"host sync failed ({type(e).__name__}: {e})"
    return result


# --------------------------------------------------------------------------------------------- reporting

def _indent(text: str) -> List[str]:
    return ["    " + line for line in text.splitlines()] if text else []


def _verb(action: str, dry_run: bool) -> str:
    past = {"create": "created", "update": "updated", "delete": "deleted"}
    return f"would {action}" if dry_run else past.get(action, action)


def render_template_result(result: TemplateResult, dry_run: bool) -> str:
    if not result.has_changes:
        status = "unchanged"
    else:
        status = _verb("update" if result.exists else "create", dry_run)
    lines = [f"template {', '.join(result.names)}: {status}"]
    if result.removals:
        lines.append(f"  !! {result.removals} REMOVAL(S): deleteMissing deletes these from Zabbix")
    if result.has_changes:
        lines += _indent(result.diff.render())
    return "\n".join(lines)


def render_host_result(host: HostResult, dry_run: bool) -> str:
    if host.failed:
        return f"host {host.host_name}: FAILED: {host.error}"
    lines = [f"host {host.host_name}: " + ("unchanged" if not host.has_changes else _verb(host.action, dry_run))]
    if host.removals:
        lines.append(f"  !! {host.removals} REMOVAL(S)")
    lines += _indent(host.diff_text)
    return "\n".join(lines)


def render_service_result(result: ServiceResult, dry_run: bool) -> str:
    lines: List[str] = []
    if result.template is not None:
        lines.append(render_template_result(result.template, dry_run))
    lines += [render_host_result(h, dry_run) for h in result.hosts.hosts]
    if result.error:
        lines.append(f"ERROR: {result.error}")
    return "\n".join(lines)
