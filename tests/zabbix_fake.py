# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#
"""In-memory fake Zabbix API used as an injectable transport. Records every RPC it receives."""

import copy
import json
import urllib.request
import re
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

from promabbix.zabbix.client import WRITE_METHODS

_CM = frozenset({"createMissing"})
_CU = frozenset({"createMissing", "updateExisting"})
_CUD = frozenset({"createMissing", "updateExisting", "deleteMissing"})

#: ``configuration.import`` rules accepted by Zabbix 6.0, key -> allowed flags.  Copied from
#: ui/include/classes/api/services/CConfiguration.php:205-270 (release/6.0): ``groups`` has no deleteMissing,
#: ``templateLinkage`` has no updateExisting, there is no host_groups / template_groups / applications.
RULES_60: Dict[str, FrozenSet[str]] = {
    "discoveryRules": _CUD, "graphs": _CUD, "groups": _CU, "hosts": _CU, "httptests": _CUD, "images": _CU,
    "items": _CUD, "maps": _CU, "mediaTypes": _CU, "templateLinkage": frozenset({"createMissing", "deleteMissing"}),
    "templates": _CU, "templateDashboards": _CUD, "triggers": _CUD, "valueMaps": _CUD,
}
#: 6.2+ split ``groups`` into host_groups and template_groups (not audited against sources, flags as for groups).
RULES_62 = {**{k: v for k, v in RULES_60.items() if k != "groups"}, "host_groups": _CU, "template_groups": _CU}


def version_tuple(version: str) -> Tuple[int, int]:
    """``"6.0.25"`` -> ``(6, 0)``.  Never compare version strings: ``"10.0" < "6.2"``."""
    match = re.match(r"(\d+)\.(\d+)", version)
    assert match, f"bad fake version {version!r}"
    return int(match.group(1)), int(match.group(2))


class FakeZabbix:
    def __init__(self, version: str = "7.0.5", password: str = "secret",
                 groups: Optional[List[str]] = None, proxies: Optional[List[str]] = None) -> None:
        self.version = version
        self.vt = version_tuple(version)
        self.password = password
        self.calls: List[Dict[str, Any]] = []
        self.groups = {name: str(i + 1) for i, name in enumerate(
            groups if groups is not None else ["New host maitenance", "Kubernetes", "Production hosts"])}
        self.proxies = {name: str(100 + i) for i, name in enumerate(
            proxies if proxies is not None else ["gce-infra-zabbix-proxy-pgsql-2", "other-proxy"])}
        self.templates: Dict[str, str] = {}      # name -> templateid
        self.exports: Dict[str, Dict[str, Any]] = {}  # name -> export document
        self.hosts: Dict[str, Dict[str, Any]] = {}    # host name -> raw host (host.get shape)
        self.errors: Dict[str, Any] = {}  # method -> (code, message, data) | callable(params) -> Optional[tuple]
        self.http_status: Optional[int] = None
        self.raw_body: Optional[bytes] = None
        self._next_id = 1000

    # --- test helpers -------------------------------------------------------------------------------
    @property
    def methods(self) -> List[str]:
        return [c["method"] for c in self.calls]

    @property
    def write_calls(self) -> List[Dict[str, Any]]:
        return [c for c in self.calls if c["method"] in WRITE_METHODS]

    def calls_of(self, method: str) -> List[Dict[str, Any]]:
        return [c for c in self.calls if c["method"] == method]

    def add_live_template(self, doc: Dict[str, Any]) -> None:
        self._register_template_doc(doc)

    def _register_template_doc(self, doc: Dict[str, Any]) -> None:
        for tpl in doc["zabbix_export"]["templates"]:
            name = tpl["template"]
            self.templates.setdefault(name, str(self._new_id()))
            self.exports[name] = copy.deepcopy(doc)

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    # --- transport ----------------------------------------------------------------------------------
    def __call__(self, request: urllib.request.Request, timeout: float) -> bytes:
        payload = json.loads(request.data or b"{}")
        headers = {k.lower(): v for k, v in request.header_items()}
        call = {"method": payload["method"], "params": payload["params"], "auth": payload.get("auth"),
                "headers": headers, "timeout": timeout, "url": request.full_url}
        self.calls.append(call)
        if self.http_status is not None:
            from promabbix.zabbix.client import ZabbixConnectionError
            raise ZabbixConnectionError(f"HTTP {self.http_status}", code=self.http_status)
        if self.raw_body is not None:
            return self.raw_body
        auth_error = self._check_auth(payload, headers)
        if auth_error:
            return self._reply(payload, error=auth_error)
        injected = self.errors.get(payload["method"])
        if callable(injected):
            injected = injected(payload["params"])
        if injected:
            code, message, data = injected
            return self._reply(payload, error={"code": code, "message": message, "data": data})
        handler: Callable[[Any], Any] = getattr(self, "_m_" + payload["method"].replace(".", "_"), self._unknown)
        try:
            return self._reply(payload, result=handler(payload["params"]))
        except KeyError as e:
            return self._reply(payload, error={"code": -32602, "message": "Invalid params.", "data": str(e)})

    def _check_auth(self, payload: Dict[str, Any], headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """CLocalApiClient.php:87-95 and 205-216 (release/6.0): apiinfo.version and user.login must not carry
        ``auth``; every other method needs a session: the body ``auth`` or, from 7.0, the ``Authorization: Bearer``
        header (a 6.x server ignores the header)."""
        method = payload["method"]
        body_auth = payload.get("auth")
        if method in ("apiinfo.version", "user.login"):
            if body_auth is not None:
                return {"code": -32602, "message": "Invalid params.",
                        "data": f'The "{method}" method must be called without the "auth" parameter.'}
            if "authorization" in headers and self.vt >= (7, 0):
                return {"code": -32602, "message": "Invalid params.",
                        "data": f'The "{method}" method must be called without authentication.'}
            return None
        bearer = headers.get("authorization", "")
        token = body_auth
        if token is None and self.vt >= (7, 0) and bearer.startswith("Bearer "):
            token = bearer[len("Bearer "):]  # before 7.0 the header is ignored, only the body ``auth`` counts
        if token != "tok-123":
            return {"code": -32602, "message": "Not authorized.", "data": "Session terminated, re-login, "
                    "session is expired or no permissions to perform the operation."}
        return None

    @staticmethod
    def _reply(payload: Dict[str, Any], result: Any = None, error: Optional[Dict[str, Any]] = None) -> bytes:
        body: Dict[str, Any] = {"jsonrpc": "2.0", "id": payload["id"]}
        if error is not None:
            body["error"] = error
        else:
            body["result"] = result
        return json.dumps(body).encode()

    def _unknown(self, params: Any) -> Any:
        raise KeyError("method not implemented in fake")

    # --- API methods --------------------------------------------------------------------------------
    def _m_apiinfo_version(self, params: Any) -> str:
        return self.version

    def _m_user_login(self, params: Any) -> str:
        if params.get("password") != self.password:
            raise _Err(-32602, "Incorrect user name or password or account is temporarily blocked.", "Login name or password is incorrect.")
        return "tok-123"

    def _m_user_logout(self, params: Any) -> bool:
        return True

    def _m_template_get(self, params: Any) -> List[Dict[str, str]]:
        wanted = params["filter"]["host"]
        return [{"templateid": tid, "host": n} for n, tid in self.templates.items() if n in wanted]

    def _m_configuration_export(self, params: Any) -> str:
        ids = params["options"]["templates"]
        names = [n for n, tid in self.templates.items() if tid in ids]
        return json.dumps(self._export_shape(self.exports[names[0]]))

    def _export_shape(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """The export carries the server's own version, and the group list is ``groups`` before 6.2
        (``template_groups`` / ``host_groups`` from 6.2)."""
        doc = copy.deepcopy(doc)
        export = doc["zabbix_export"]
        export["version"] = f"{self.vt[0]}.{self.vt[1]}"
        if self.vt < (6, 2):
            if "template_groups" in export:
                export["groups"] = export.pop("template_groups")
        elif "groups" in export:
            export["template_groups"] = export.pop("groups")
        return doc

    def _check_import_rules(self, rules: Dict[str, Any]) -> None:
        allowed = RULES_60 if self.vt < (6, 2) else RULES_62
        for key, flags in rules.items():
            if key not in allowed:
                raise _Err(-32602, "Invalid params.", f'Invalid parameter "/rules": unexpected parameter "{key}".')
            for flag in flags:
                if flag not in allowed[key]:
                    raise _Err(-32602, "Invalid params.",
                               f'Invalid parameter "/rules/{key}": unexpected parameter "{flag}".')

    def _m_configuration_import(self, params: Any) -> bool:
        self._check_import_rules(params["rules"])
        self._register_template_doc(json.loads(params["source"]))
        return True

    def _m_hostgroup_get(self, params: Any) -> List[Dict[str, str]]:
        wanted = params["filter"]["name"]
        return [{"groupid": gid, "name": n} for n, gid in self.groups.items() if n in wanted]

    def _m_proxy_get(self, params: Any) -> List[Dict[str, str]]:
        key = "name" if self.vt >= (7, 0) else "host"
        if any(field not in ("proxyid", key) for field in params.get("output", [])):
            raise _Err(-32602, "Invalid params.", f'Invalid parameter "/output": unexpected value in {params["output"]}.')
        return [{"proxyid": pid, key: n} for n, pid in self.proxies.items()]

    def _m_host_get(self, params: Any) -> List[Dict[str, Any]]:
        if "selectHostGroups" in params and self.vt < (6, 2):
            raise _Err(-32602, "Invalid params.", 'Invalid parameter "/": unexpected parameter "selectHostGroups".')
        wrong_proxy = "proxy_hostid" if self.vt >= (7, 0) else "proxyid"
        if wrong_proxy in params.get("output", []):
            raise _Err(-32602, "Invalid params.", f'Invalid parameter "/output/{wrong_proxy}": unexpected value.')
        name = params["filter"]["host"][0]
        return [copy.deepcopy(self.hosts[name])] if name in self.hosts else []

    def _host_from_params(self, params: Dict[str, Any], hostid: str, host: str) -> Dict[str, Any]:
        gid_to_name = {v: k for k, v in self.groups.items()}
        tid_to_name = {v: k for k, v in self.templates.items()}
        proxy_field = "proxyid" if self.vt >= (7, 0) else "proxy_hostid"
        for wrong in ({"proxy_hostid"} if self.vt >= (7, 0) else {"proxyid", "monitored_by"}) & set(params):
            raise _Err(-32602, "Invalid params.", f'Invalid parameter "/": unexpected parameter "{wrong}".')
        groups = [{"groupid": g["groupid"], "name": gid_to_name[g["groupid"]]} for g in params["groups"]]
        raw: Dict[str, Any] = {
            "hostid": hostid, "host": host, "name": params["name"], "description": params["description"],
            "status": str(params["status"]), proxy_field: params[proxy_field],
            "parentTemplates": [{"templateid": t["templateid"], "host": tid_to_name[t["templateid"]]}
                                for t in params["templates"]],
            "macros": [dict(m, hostmacroid=str(self._new_id()), type="0") for m in params["macros"]],
            "interfaces": [dict(i, interfaceid=i.get("interfaceid", str(self._new_id()))) for i in params["interfaces"]],
        }
        raw["hostgroups" if self.vt >= (6, 2) else "groups"] = groups
        return raw

    def _m_host_create(self, params: Any) -> Dict[str, List[str]]:
        hostid = str(self._new_id())
        self.hosts[params["host"]] = self._host_from_params(params, hostid, params["host"])
        return {"hostids": [hostid]}

    def _m_host_update(self, params: Any) -> Dict[str, List[str]]:
        name = next(n for n, h in self.hosts.items() if h["hostid"] == params["hostid"])
        self.hosts[name] = self._host_from_params(params, params["hostid"], name)
        return {"hostids": [params["hostid"]]}

    def _m_host_delete(self, params: Any) -> Dict[str, List[str]]:
        for name in [n for n, h in self.hosts.items() if h["hostid"] in params]:
            del self.hosts[name]
        return {"hostids": params}


class _Err(Exception):
    pass





_orig_call = FakeZabbix.__call__


def _call_with_errors(self: FakeZabbix, request: urllib.request.Request, timeout: float) -> bytes:
    try:
        return _orig_call(self, request, timeout)
    except _Err as e:
        code, message, data = e.args
        payload = json.loads(request.data or b"{}")
        return self._reply(payload, error={"code": code, "message": message, "data": data})


FakeZabbix.__call__ = _call_with_errors  # type: ignore[method-assign]


def fake_template_doc(name: str = "templ_module_promt_svc", items: Tuple[str, ...] = ("a", "b")) -> Dict[str, Any]:
    """A small, real-shaped template export."""
    return {"zabbix_export": {"version": "6.0", "date": "2025-01-01T00:00:00Z",
                              "groups": [{"uuid": "g1", "name": "Templates"}],
                              "templates": [{
                                  "uuid": "u-" + name, "template": name, "name": name,
                                  "groups": [{"name": "Templates"}],
                                  "items": [{"uuid": "i-" + k, "name": k, "key": "k." + k} for k in items],
                                  "triggers": [{"uuid": "t-" + k, "name": "trig " + k, "expression": "last(/x/k." + k + ")=1"}
                                               for k in items],
                              }]}}
