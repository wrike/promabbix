# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#
"""Emulation of what a Zabbix 6.0 ``configuration.export`` returns for a promabbix-style template.

Written from the 6.0 sources (release/6.0, ``ui/``), independently of ``promabbix.zabbix.diff``:

* defaults are omitted: CConfigurationExportBuilder.php:74-90 with the schema defaults of
  include/classes/import/validators/C60XmlValidator.php (``value_type`` UNSIGNED, not FLOAT:
  C60XmlValidator.php:476, 622, 1152, 1299);
* LLD filter conditions are sorted and ``formulaid`` renumbered A, B, C... for evaltype AND_OR / AND / OR:
  ``sortLldRuleFilterConditions``, include/items.inc.php:2345-2373, called from
  CConfigurationExportBuilder.php:691-695;
* the top-level group list is ``groups`` and the version is ``6.0`` (template_groups exists from 6.2);
* trigger prototypes sit on the discovery rule, triggers on the export root.
"""

import copy
import re
from functools import cmp_to_key
from typing import Any, Dict, List

# (field -> value) pairs the 6.0 exporter leaves out, per object kind.
_COMMON = {"status": "ENABLED", "type": "ZABBIX_PASSIVE", "delay": "1m", "authtype": "NONE", "timeout": "3s",
           "request_method": "GET", "retrieve_mode": "BODY", "post_type": "RAW", "allow_traps": "NO",
           "follow_redirects": "YES", "verify_peer": "NO", "verify_host": "NO", "status_codes": "200"}
_ITEM = {**_COMMON, "value_type": "UNSIGNED", "history": "90d", "trends": "365d", "inventory_link": "NONE",
         "output_format": "RAW"}
_OMIT = {
    "items": _ITEM,
    "item_prototypes": {**_ITEM, "discover": "DISCOVER"},
    "discovery_rules": {**_COMMON, "lifetime": "30d"},
    "triggers": {"status": "ENABLED", "priority": "NOT_CLASSIFIED", "manual_close": "NO", "type": "SINGLE",
                 "recovery_mode": "EXPRESSION", "correlation_mode": "DISABLED"},
    "trigger_prototypes": {"status": "ENABLED", "priority": "NOT_CLASSIFIED", "manual_close": "NO",
                           "type": "SINGLE", "recovery_mode": "EXPRESSION", "correlation_mode": "DISABLED",
                           "discover": "DISCOVER"},
    "macros": {"type": "TEXT"},
    "conditions": {"operator": "MATCHES_REGEX"},
    "preprocessing": {"error_handler": "ORIGINAL_ERROR"},
}
_EXISTS_OPERATORS = ("EXISTS", "NOT_EXISTS")


def _natcasecmp(a: str, b: str) -> int:
    """Approximation of PHP strnatcasecmp: digit runs compare as numbers, the rest case-insensitively."""
    def chunks(s: str) -> List[Any]:
        return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", s.lower()) if p]
    ka, kb = chunks(a), chunks(b)
    for x, y in zip(ka, kb):
        if type(x) is not type(y):
            x, y = str(x), str(y)
        if x != y:
            return -1 if x < y else 1
    return (len(ka) > len(kb)) - (len(ka) < len(kb))


def _compare_conditions(a: Dict[str, Any], b: Dict[str, Any]) -> int:
    """items.inc.php:2350-2367: macro, then (not-)exists operators first, then value."""
    result = _natcasecmp(a["macro"], b["macro"])
    if result:
        return result
    a_exists = a.get("operator", "MATCHES_REGEX") in _EXISTS_OPERATORS
    b_exists = b.get("operator", "MATCHES_REGEX") in _EXISTS_OPERATORS
    if a_exists != b_exists:
        return int(b_exists) - int(a_exists)
    return _natcasecmp(a.get("value", ""), b.get("value", ""))


def num2letter(number: int) -> str:
    """include/func.inc.php:1585: 0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    level = 0
    while True:
        if level:
            number -= 1
        level += 1
        number, remainder = divmod(number, 26)
        letters = chr(ord("A") + remainder) + letters
        if number <= 0:
            return letters


def sort_and_renumber(conditions: List[Dict[str, Any]], evaltype: str) -> List[Dict[str, Any]]:
    """sortLldRuleFilterConditions() for AND_OR / AND / OR; FORMULA keeps its ids, ordered by formulaid."""
    conditions = copy.deepcopy(conditions)
    if evaltype == "FORMULA":
        return sorted(conditions, key=lambda c: c["formulaid"])
    conditions.sort(key=cmp_to_key(_compare_conditions))
    for index, condition in enumerate(conditions):
        condition["formulaid"] = num2letter(index)
    return conditions


def _strip(obj: Dict[str, Any], kind: str) -> Dict[str, Any]:
    omit = _OMIT.get(kind, {})
    return {k: v for k, v in obj.items() if omit.get(k) != v and v not in ("", [], {}, None)}


def _export_filter(rule: Dict[str, Any]) -> None:
    flt = rule.get("filter")
    if not flt or not flt.get("conditions"):
        rule.pop("filter", None)  # CConfigurationExportBuilder.php:643-645
        return
    evaltype = flt.get("evaltype", "AND_OR")
    flt["conditions"] = [_strip(c, "conditions") for c in sort_and_renumber(flt["conditions"], evaltype)]
    if evaltype == "AND_OR":
        flt.pop("evaltype")
    if evaltype != "FORMULA":
        flt.pop("formula", None)


def export_60(rendered: Dict[str, Any], uuid: str = "f" * 32) -> Dict[str, Any]:
    """The 6.0 export of ``rendered`` (a promabbix-generated or hand-written template document)."""
    export = copy.deepcopy(rendered["zabbix_export"])
    export["version"] = "6.0"
    export["date"] = "2025-06-01T00:00:00Z"
    if "template_groups" in export:
        export["groups"] = export.pop("template_groups")
    for tpl in export["templates"]:
        tpl["uuid"] = uuid
        tpl["items"] = [_strip(i, "items") for i in tpl.get("items", [])]
        rules = []
        for rule in tpl.get("discovery_rules", []):
            protos, triggers = [], rule.pop("trigger_prototypes", [])
            for proto in rule.pop("item_prototypes", []):
                triggers += proto.pop("trigger_prototypes", [])
                protos.append(_strip(proto, "item_prototypes"))
            _export_filter(rule)
            rule = _strip(rule, "discovery_rules")
            rule["item_prototypes"] = protos
            rule["trigger_prototypes"] = [_strip(t, "trigger_prototypes") for t in triggers]
            rules.append(rule)
        tpl["discovery_rules"] = rules
        tpl["macros"] = [_strip(m, "macros") for m in tpl.get("macros", [])]
    return {"zabbix_export": export}
