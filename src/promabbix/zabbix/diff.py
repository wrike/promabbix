#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#
"""Pure-Python diff engine for Zabbix templates and hosts (no network access).

Shared by two consumers:

* PM-6 (skip no-op imports): ``should_import(live, desired)``
* ``--dry-run`` of ``syncTemplate`` / ``syncPseudoHosts``: ``diff_template`` /
  ``diff_host`` plus ``.render()``

Design decisions
----------------
Template side (``zabbix_export`` JSON as produced by ``configuration.export``
on Zabbix 6/7, or by promabbix's own generator, which uses the same shape):

* Both sides go through :func:`normalize_template`, so the diff never sees
  ``uuid``, ``version``, ``date``, generated ids, ``vendor`` metadata or the
  top-level group lists (imported with ``createMissing`` only, never updated
  or deleted).  UUID changes are therefore deliberately *not* a difference.
* Trigger placement is normalised: promabbix nests ``trigger_prototypes`` inside
  ``item_prototypes`` (and ``triggers`` inside ``items``) whereas a Zabbix export
  lists them on the discovery rule / at export level.  Nested triggers are
  hoisted to the export layout before comparing, so layout alone is never a
  difference.
* Lists of objects are sorted by a stable identity (items by ``key``, triggers
  by ``name`` + ``expression``, discovery rules by ``key``, prototypes by
  ``key`` / ``name``, macros by ``macro``, tags by ``tag`` + ``value``).
  Ordered lists (``preprocessing`` steps, ``parameters``) are never sorted.
* Defaults omission: Zabbix export omits fields holding their default value.
  Normalisation removes ``None``, ``""``, ``[]``, ``{}`` and every value equal to
  a documented default (``_DEFAULTS``: e.g. ``status: ENABLED``, item
  ``delay: 1m``) from *both* sides, so ``missing == default``.  Fields outside
  that table are compared strictly: a field present on one side only counts
  as a change.  That is conservative on purpose: an unknown difference causes
  an import (safe), never a skipped one.  Numbers are compared as strings.
* ``delay`` of ``DEPENDENT`` items / rules is ignored (it has no meaning there).
* Only templates that exist in ``desired`` are compared; templates present only
  in ``live`` are ignored (import never deletes templates).  Top-level keys of
  the export other than ``templates`` / ``triggers`` / ``graphs`` are ignored.
* Removal semantics follow the import rules (``deleteMissing`` for items,
  triggers, discovery rules, graphs and httptests, which includes LLD
  prototypes).  Those removals are *destructive*: they delete history and are
  counted in ``removals`` and rendered with ``!!! REMOVE``.  Macros and tags
  removals are reported in ``removed`` but are not counted in ``removals``.
  Live-only linked templates, dashboards and value maps are ignored because the
  import never removes them.

Host side (``host.get`` style or promabbix ``zabbix.hosts[]`` style, both are
accepted, see ``_HOST_ALIASES``):

* Mirrors ``host.update`` semantics: only the properties *present* in
  ``desired`` are compared (an omitted property is not sent, so it is
  unchanged).  Groups, linked templates, macros and interfaces are replaced as a
  whole by ``host.update``; dropping one is listed under ``removed`` but is not
  counted in ``removals`` (unlinking keeps history, only the host object itself
  can be deleted).
* The proxy must be given by name (``proxy``).  A bare ``proxyid`` /
  ``proxy_hostid`` cannot be resolved here and is rendered as ``<id N>``,
  which differs from any name, so callers should resolve it first.
* ``state: absent`` in ``desired`` means the host is to be deleted: it is a
  removal (counted) when ``live`` exists and no change otherwise.
* Secret-text macros (``type`` 1) never expose their value through the API, so
  only their presence is compared.
"""

from __future__ import annotations

import copy
import difflib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Optional, Sequence, Set, Tuple, Union

__all__ = [
    "FieldChange",
    "ObjectChange",
    "TemplateDiff",
    "HostDiff",
    "normalize_template",
    "normalize_host",
    "diff_template",
    "diff_host",
    "should_import",
]

JsonDict = Dict[str, Any]
Export = Union[JsonDict, str, bytes]

PATH_SEP = " > "
_INLINE_MAX = 100


# ---------------------------------------------------------------------------
# Schema tables
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Child:
    """Describes a list of child objects inside a parent object."""

    kind: str
    keys: Tuple[str, ...]
    fallback: Tuple[str, ...] = ()  # pair leftovers by this key -> "changed"
    label: Tuple[str, ...] = ()  # fields shown to humans (defaults to keys)
    destructive: bool = False  # removal is applied by the import / update
    ignore_live_only: bool = False  # import never removes these
    inline: bool = False  # attribute of its parent: not listed when the parent is added/removed


_TRIGGER = _Child("trigger", ("name", "expression"), ("name",), ("name",), destructive=True)
_TRIGGER_PROTO = _Child("trigger_prototype", ("name", "expression"), ("name",), ("name",), destructive=True)
_TAG = _Child("tag", ("tag", "value"), ("tag",), ("tag", "value"))
_OBJ_TAG = _Child("tag", ("tag", "value"), ("tag",), ("tag", "value"), inline=True)
_MACRO = _Child("macro", ("macro",))
_GROUP = _Child("group", ("name",))

_CHILDREN: Dict[str, Dict[str, _Child]] = {
    "export": {
        "templates": _Child("template", ("template",)),
        "triggers": _TRIGGER,
        "graphs": _Child("graph", ("name",), destructive=True),
    },
    "template": {
        "items": _Child("item", ("key",), destructive=True),
        "discovery_rules": _Child("discovery_rule", ("key",), destructive=True),
        "httptests": _Child("httptest", ("name",), destructive=True),
        "macros": _MACRO,
        "tags": _TAG,
        "groups": _GROUP,
        "templates": _Child("linked_template", ("name",), ignore_live_only=True),
        "dashboards": _Child("dashboard", ("name",), ignore_live_only=True),
        "valuemaps": _Child("valuemap", ("name",), ignore_live_only=True),
    },
    "item": {"tags": _OBJ_TAG},
    "discovery_rule": {
        "item_prototypes": _Child("item_prototype", ("key",), destructive=True),
        "trigger_prototypes": _TRIGGER_PROTO,
        "graph_prototypes": _Child("graph_prototype", ("name",), destructive=True),
        "host_prototypes": _Child("host_prototype", ("host",), destructive=True),
        "tags": _OBJ_TAG,
    },
    "item_prototype": {"tags": _OBJ_TAG},
    "host": {
        "groups": _GROUP,
        "templates": _Child("linked_template", ("name",)),
        "interfaces": _Child("interface", ("type", "main", "ip", "dns", "port"), ("type", "main"),
                             ("type", "ip", "port")),
        "macros": _MACRO,
    },
}

_ITEM_DEFAULTS = {
    "status": "ENABLED", "type": "ZABBIX_PASSIVE", "value_type": "FLOAT", "delay": "1m",
    "history": "90d", "trends": "365d", "request_method": "GET", "timeout": "3s",
    "discover": "DISCOVER", "allow_traps": "NO", "follow_redirects": "YES",
    "retrieve_mode": "BODY", "post_type": "RAW", "output_format": "RAW",
    "authtype": "NONE", "verify_host": "NO", "verify_peer": "NO", "status_codes": "200",
}
_TRIGGER_DEFAULTS = {
    "status": "ENABLED", "priority": "NOT_CLASSIFIED", "manual_close": "NO",
    "recovery_mode": "EXPRESSION", "correlation_mode": "DISABLED",
    "discover": "DISCOVER", "type": "SINGLE",
}
_GRAPH_DEFAULTS = {
    "type": "NORMAL", "width": "900", "height": "200", "show_legend": "YES",
    "show_work_period": "YES", "show_triggers": "YES",
}

# Defaults keyed by object kind (child objects) or by field name (plain nested values).
_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "item": _ITEM_DEFAULTS,
    "item_prototype": _ITEM_DEFAULTS,
    "discovery_rule": {**_ITEM_DEFAULTS, "lifetime": "30d"},
    "trigger": _TRIGGER_DEFAULTS,
    "trigger_prototype": _TRIGGER_DEFAULTS,
    "graph": _GRAPH_DEFAULTS,
    "graph_prototype": _GRAPH_DEFAULTS,
    "httptest": {"status": "ENABLED", "delay": "1m", "attempts": "1", "agent": "Zabbix"},
    "macro": {"type": "TEXT"},
    "host_macro": {"type": "0"},
    "preprocessing": {"error_handler": "ORIGINAL_ERROR"},
    "conditions": {"operator": "MATCHES_REGEX"},
    "filter": {"evaltype": "AND_OR"},
}

_DEPENDENT_KINDS = frozenset({"item", "item_prototype", "discovery_rule"})

# Plain lists of dicts where order carries no meaning.
_PLAIN_SORT: Dict[str, Tuple[str, ...]] = {"conditions": ("formulaid", "macro", "value")}

# Keys removed at any depth (generated ids).
_VOLATILE_KEYS = frozenset({
    "uuid", "templateid", "itemid", "triggerid", "graphid", "hostid", "interfaceid",
    "hostmacroid", "httptestid", "ruleid", "valuemapid", "dashboardid", "groupid",
})
# Keys removed on the export root / template.
_EXPORT_DROP = frozenset({"version", "date", "groups", "template_groups", "host_groups"})
_TEMPLATE_DROP = frozenset({"vendor"})


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldChange:
    """A single scalar/plain field difference.  ``None`` means "unset"."""

    field: str
    old: Any
    new: Any


@dataclass(frozen=True)
class ObjectChange:
    """One added / removed / changed object.

    ``path`` is the human readable hierarchical identity, e.g.
    ``template "t" > discovery_rule "k" > item_prototype "p"``.
    ``destructive`` is only meaningful for removed objects: the removal is
    applied by the import/update and destroys data (history).
    """

    kind: str
    path: str
    fields: Tuple[FieldChange, ...] = ()
    destructive: bool = False


@dataclass
class _DiffBase:
    title: str
    is_new: bool = False
    added: List[ObjectChange] = field(default_factory=list)
    removed: List[ObjectChange] = field(default_factory=list)
    changed: List[ObjectChange] = field(default_factory=list)

    label: ClassVar[str] = "Object"
    root_kind: ClassVar[str] = ""

    @property
    def has_changes(self) -> bool:
        return bool(self.is_new or self.added or self.removed or self.changed)

    @property
    def removals(self) -> int:
        """Number of objects that would be DELETED (data/history loss)."""
        return sum(1 for r in self.removed if r.destructive)

    def render(self) -> str:
        """Human readable, unified-style text.  Removals come first."""
        head = f"{self.label} {self.title}"
        if not self.has_changes:
            return f"{head}: no changes"
        if self.is_new:
            return "\n".join([f"{head}: NEW, would be created", self._new_summary()])
        strip = f'{self.root_kind} "{self.title}"{PATH_SEP}'
        lines = [f"{head}: CHANGES"]
        lines += [self._removed_line(r, strip) for r in self.removed if r.destructive]
        lines += [self._removed_line(r, strip) for r in self.removed if not r.destructive]
        for c in self.changed:
            lines.append(f"~ {_short(c.path, strip)}")
            for fc in c.fields:
                lines += _render_field(fc)
        lines += [f"+ {_short(a.path, strip)}" for a in self.added]
        lines.append(self._summary())
        if self.removals:
            lines.append(f"!!! {self.removals} object(s) would be DELETED, history and data will be lost")
        return "\n".join(lines)

    def _summary(self) -> str:
        return f"Summary: {len(self.added)} added, {len(self.removed)} removed, {len(self.changed)} changed"

    def _new_summary(self) -> str:
        counts: Dict[str, int] = defaultdict(int)
        for a in self.added:
            counts[a.kind] += 1
        body = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
        return f"+ {len(self.added)} object(s): {body}" if body else "+ 0 object(s)"

    @staticmethod
    def _removed_line(r: ObjectChange, strip: str) -> str:
        prefix = "!!! REMOVE" if r.destructive else "-"
        return f"{prefix} {_short(r.path, strip)}"


@dataclass
class TemplateDiff(_DiffBase):
    label: ClassVar[str] = "Template"
    root_kind: ClassVar[str] = "template"


@dataclass
class HostDiff(_DiffBase):
    label: ClassVar[str] = "Host"
    root_kind: ClassVar[str] = "host"


def _short(path: str, strip: str) -> str:
    return path[len(strip):] if strip and path.startswith(strip) else path


def _fmt(value: Any) -> str:
    return "<unset>" if value is None else json.dumps(value, ensure_ascii=False, sort_keys=True)


def _pretty(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _render_field(fc: FieldChange) -> List[str]:
    old, new = _fmt(fc.old), _fmt(fc.new)
    if max(len(old), len(new)) <= _INLINE_MAX and "\\n" not in old + new:
        return [f"    - {fc.field}: {old}", f"    + {fc.field}: {new}"]
    udiff = difflib.unified_diff(_pretty(fc.old).splitlines(), _pretty(fc.new).splitlines(), lineterm="", n=1)
    return [f"    ~ {fc.field}:"] + [f"      {line}" for line in list(udiff)[2:]]


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, (str, list, dict)) and len(value) == 0)


def _clean(value: Any, ctx: str) -> Any:
    """Recursively normalise a plain value found under field ``ctx``."""
    if isinstance(value, dict):
        defaults = _DEFAULTS.get(ctx, {})
        out = {}
        for k, v in value.items():
            if k in _VOLATILE_KEYS:
                continue
            cleaned = _clean(v, k)
            if not _is_empty(cleaned) and cleaned != defaults.get(k):
                out[k] = cleaned
        return out
    if isinstance(value, list):
        items = [_clean(v, ctx) for v in value]
        sort_keys = _PLAIN_SORT.get(ctx)
        if sort_keys and all(isinstance(i, dict) for i in items):
            items.sort(key=lambda i: _sort_key(i, sort_keys))
        return items
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return value


def _sort_key(obj: JsonDict, keys: Sequence[str]) -> Tuple[Tuple[str, ...], str]:
    return (tuple(str(obj.get(k, "")) for k in keys), json.dumps(obj, sort_keys=True, ensure_ascii=False))


def _dicts(values: Any) -> List[JsonDict]:
    return [v for v in values or [] if isinstance(v, dict)]


def _hoist_triggers(export: JsonDict) -> JsonDict:
    """Move nested triggers to the layout used by Zabbix exports (on a copy)."""
    export = copy.deepcopy(export)
    top = export.setdefault("triggers", [])
    for tpl in _dicts(export.get("templates")):
        for item in _dicts(tpl.get("items")):
            top.extend(item.pop("triggers", None) or [])
        for rule in _dicts(tpl.get("discovery_rules")):
            protos = rule.setdefault("trigger_prototypes", [])
            for proto in _dicts(rule.get("item_prototypes")):
                protos.extend(proto.pop("trigger_prototypes", None) or [])
    return export


def _normalize_object(obj: JsonDict, kind: str) -> JsonDict:
    children = _CHILDREN.get(kind, {})
    defaults = _DEFAULTS.get(kind, {})
    drop = _VOLATILE_KEYS
    if kind == "export":
        drop = drop | _EXPORT_DROP
    elif kind == "template":
        drop = drop | _TEMPLATE_DROP
    out: JsonDict = {}
    for name, raw in obj.items():
        if name in drop:
            continue
        spec = children.get(name)
        if spec is not None and isinstance(raw, list):
            items = [_normalize_object(o, spec.kind) for o in raw if isinstance(o, dict)]
            items.sort(key=lambda i: _sort_key(i, spec.keys))
            value: Any = items
        else:
            value = _clean(raw, name)
        if not _is_empty(value) and value != defaults.get(name):
            out[name] = value
    if kind in _DEPENDENT_KINDS and out.get("type") == "DEPENDENT":
        out.pop("delay", None)  # meaningless for dependent items, exports are inconsistent
    return out


def _load_export(export: Export) -> JsonDict:
    if isinstance(export, (str, bytes)):
        export = json.loads(export)
    if not isinstance(export, dict):
        raise TypeError(f"Zabbix export must be a dict or JSON string, got {type(export).__name__}")
    inner = export.get("zabbix_export", export)
    if not isinstance(inner, dict):
        raise TypeError("'zabbix_export' must be an object")
    return inner


def normalize_template(export: Export) -> JsonDict:
    """Return a canonical, comparable form of a Zabbix export / generated template.

    Accepts ``{"zabbix_export": {...}}`` (or the bare inner object, or its JSON
    text) and returns ``{"zabbix_export": {...}}`` without volatile fields,
    with lists sorted by stable keys and defaults omission normalised (see the
    module docstring).  Never mutates its input.
    """
    return {"zabbix_export": _normalize_object(_hoist_triggers(_load_export(export)), "export")}


# ---------------------------------------------------------------------------
# Generic object tree diff
# ---------------------------------------------------------------------------


def _key(obj: JsonDict, keys: Sequence[str]) -> Tuple[str, ...]:
    return tuple(str(obj.get(k, "")) for k in keys)


def _label(spec: _Child, obj: JsonDict) -> str:
    return f'{spec.kind} "' + "/".join(str(obj.get(k, "")) for k in (spec.label or spec.keys)) + '"'


def _join(parent: str, label: str) -> str:
    return f"{parent}{PATH_SEP}{label}" if parent else label


def _pair_by_fallback(live: List[JsonDict], desired: List[JsonDict], keys: Sequence[str]
                      ) -> Tuple[List[Tuple[JsonDict, JsonDict]], List[JsonDict], List[JsonDict]]:
    """Pair leftovers whose fallback key is unique on both sides."""
    by_live: Dict[Tuple[str, ...], List[JsonDict]] = defaultdict(list)
    by_desired: Dict[Tuple[str, ...], List[JsonDict]] = defaultdict(list)
    for obj in live:
        by_live[_key(obj, keys)].append(obj)
    for obj in desired:
        by_desired[_key(obj, keys)].append(obj)
    pairs = [(by_live[k][0], by_desired[k][0])
             for k in by_live if len(by_live[k]) == 1 and len(by_desired.get(k, [])) == 1]
    used_live = {id(p[0]) for p in pairs}
    used_desired = {id(p[1]) for p in pairs}
    return (pairs,
            [o for o in live if id(o) not in used_live],
            [o for o in desired if id(o) not in used_desired])


def _match(live: List[JsonDict], desired: List[JsonDict], spec: _Child
           ) -> Tuple[List[Tuple[JsonDict, JsonDict]], List[JsonDict], List[JsonDict]]:
    """Return (matched pairs, live only, desired only)."""
    pool: Dict[Tuple[str, ...], List[JsonDict]] = defaultdict(list)
    for obj in live:
        pool[_key(obj, spec.keys)].append(obj)
    pairs: List[Tuple[JsonDict, JsonDict]] = []
    rest_desired: List[JsonDict] = []
    for obj in desired:
        bucket = pool.get(_key(obj, spec.keys))
        if bucket:
            pairs.append((bucket.pop(0), obj))
        else:
            rest_desired.append(obj)
    used = {id(p[0]) for p in pairs}
    rest_live = [o for o in live if id(o) not in used]
    if spec.fallback and rest_live and rest_desired:
        extra, rest_live, rest_desired = _pair_by_fallback(rest_live, rest_desired, spec.fallback)
        pairs.extend(extra)
    return pairs, rest_live, rest_desired


def _subtree(obj: JsonDict, spec: _Child, parent: str) -> List[ObjectChange]:
    """The object itself and all its descendants as flat entries."""
    path = _join(parent, _label(spec, obj))
    out = [ObjectChange(spec.kind, path, destructive=spec.destructive)]
    for name, child in _CHILDREN.get(spec.kind, {}).items():
        if child.inline:
            continue
        for sub in obj.get(name, []):
            out.extend(_subtree(sub, child, path))
    return out


def _field_changes(live: JsonDict, desired: JsonDict, kind: str) -> List[FieldChange]:
    skip = _CHILDREN.get(kind, {})
    names = sorted((set(live) | set(desired)) - set(skip))
    return [FieldChange(n, live.get(n), desired.get(n)) for n in names if live.get(n) != desired.get(n)]


def _diff_children(spec: _Child, parent: str, live: List[JsonDict], desired: List[JsonDict],
                   out: _DiffBase) -> None:
    pairs, only_live, only_desired = _match(live, desired, spec)
    for old, new in pairs:
        _diff_object(spec.kind, _join(parent, _label(spec, new)), old, new, out)
    for obj in only_desired:
        out.added.extend(_subtree(obj, spec, parent))
    if not spec.ignore_live_only:
        for obj in only_live:
            out.removed.extend(_subtree(obj, spec, parent))


def _diff_object(kind: str, path: str, live: JsonDict, desired: JsonDict, out: _DiffBase) -> None:
    fields = _field_changes(live, desired, kind)
    if fields:
        out.changed.append(ObjectChange(kind, path, tuple(fields)))
    for name, spec in _CHILDREN.get(kind, {}).items():
        _diff_children(spec, path, live.get(name, []), desired.get(name, []), out)


# ---------------------------------------------------------------------------
# Template diff
# ---------------------------------------------------------------------------


def diff_template(live: Optional[Export], desired: Export) -> TemplateDiff:
    """Diff the live export of a template against the desired template.

    ``live=None`` means the template does not exist yet: everything in
    ``desired`` is reported as added and ``removals`` is 0.
    """
    d_exp = normalize_template(desired)["zabbix_export"]
    templates = d_exp.get("templates", [])
    title = ", ".join(str(t.get("template", "?")) for t in templates) or "(none)"
    diff = TemplateDiff(title=title, is_new=live is None)
    if live is None:
        for name, spec in _CHILDREN["export"].items():
            for obj in d_exp.get(name, []):
                diff.added.extend(_subtree(obj, spec, ""))
        return diff
    l_exp = normalize_template(live)["zabbix_export"]
    wanted = {t.get("template") for t in templates}
    l_exp["templates"] = [t for t in l_exp.get("templates", []) if t.get("template") in wanted]
    for name, spec in _CHILDREN["export"].items():
        _diff_children(spec, "", l_exp.get(name, []), d_exp.get(name, []), diff)
    return diff


def should_import(live: Optional[Export], desired: Export) -> bool:
    """PM-6: True when ``configuration.import`` would change anything."""
    if live is None:
        return True
    return diff_template(live, desired).has_changes


# ---------------------------------------------------------------------------
# Host diff
# ---------------------------------------------------------------------------

# canonical field -> accepted aliases in host.get output / promabbix host config
_HOST_ALIASES: Dict[str, Tuple[str, ...]] = {
    "name": ("visible_name", "name"),
    "groups": ("groups", "hostgroups", "host_groups"),
    "templates": ("parentTemplates", "templates", "link_templates"),
    "interfaces": ("interfaces",),
    "macros": ("macros",),
    "proxy": ("proxy", "proxyid", "proxy_hostid"),
    "status": ("status",),
    "description": ("description",),
}
_INTERFACE_FIELDS = ("type", "main", "useip", "ip", "dns", "port", "details")
_MACRO_FIELDS = ("macro", "value", "description", "type")
_SECRET_MACRO = "1"


def _alias(raw: JsonDict, field_name: str) -> Any:
    for alias in _HOST_ALIASES[field_name]:
        if alias in raw:
            return raw[alias]
    return None


def _names(values: Any, name_keys: Sequence[str]) -> List[JsonDict]:
    out = []
    for v in values or []:
        if isinstance(v, dict):
            v = next((v[k] for k in name_keys if v.get(k)), "")
        out.append({"name": str(v)})
    out.sort(key=lambda i: i["name"])
    return out


def _host_proxy(raw: JsonDict) -> str:
    value = _alias(raw, "proxy")
    if isinstance(value, dict):
        value = value.get("name") or value.get("host")
    if "proxy" not in raw and value not in (None, "", 0, "0"):
        return f"<id {value}>"
    return str(value) if value not in (None, 0, "0") else ""


def _host_macro(raw: JsonDict) -> JsonDict:
    macro: JsonDict = _clean({k: raw[k] for k in _MACRO_FIELDS if k in raw}, "host_macro")
    if macro.get("type") == _SECRET_MACRO:
        macro.pop("value", None)
    return macro


def _host_status(raw: JsonDict) -> str:
    value = _alias(raw, "status")
    text = "enabled" if value is None else str(value).strip().lower()
    return {"0": "enabled", "1": "disabled"}.get(text, text)


def _managed_fields(raw: JsonDict) -> Set[str]:
    return {name for name, aliases in _HOST_ALIASES.items() if any(a in raw for a in aliases)}


def normalize_host(host: JsonDict) -> JsonDict:
    """Canonical, fully-defaulted form of a host (API or promabbix config shape)."""
    tech = host.get("host") or host.get("host_name")
    if not tech:
        raise ValueError("host has neither 'host' nor 'host_name'")
    visible = _alias(host, "name")
    interfaces = [_clean({k: i[k] for k in _INTERFACE_FIELDS if k in i}, "interface")
                  for i in (_alias(host, "interfaces") or [])]
    interfaces.sort(key=lambda i: _sort_key(i, ("type", "main", "ip", "dns", "port")))
    macros = [_host_macro(m) for m in (_alias(host, "macros") or [])]
    macros.sort(key=lambda m: _sort_key(m, ("macro",)))
    return {
        "host": str(tech),
        "name": str(visible) if visible not in (None, "") else str(tech),
        "groups": _names(_alias(host, "groups"), ("name",)),
        "templates": _names(_alias(host, "templates"), ("host", "template", "name")),
        "interfaces": interfaces,
        "macros": macros,
        "proxy": _host_proxy(host),
        "status": _host_status(host),
        "description": str(_alias(host, "description") or ""),
    }


def diff_host(live: Optional[JsonDict], desired: JsonDict) -> HostDiff:
    """Diff a live host (``host.get`` shape) against the desired host definition.

    Only properties present in ``desired`` are compared (``host.update``
    semantics).  ``live=None`` means "would create".
    """
    want = normalize_host(desired)
    path = f'host "{want["host"]}"'
    diff = HostDiff(title=want["host"])
    if str(desired.get("state", "present")).lower() == "absent":
        if live is not None:
            diff.removed.append(ObjectChange("host", path, destructive=True))
        return diff
    if live is None:
        diff.is_new = True
        root = _Child("host", ("host",))
        diff.added.extend(_subtree(want, root, ""))
        return diff
    managed = _managed_fields(desired)
    have = normalize_host(live)
    _diff_object("host", path, {k: v for k, v in have.items() if k in managed},
                 {k: v for k, v in want.items() if k in managed}, diff)
    return diff
