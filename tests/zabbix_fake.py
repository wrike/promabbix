# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#
"""In-memory fake Zabbix API used as an injectable transport. Records every RPC it receives."""

import copy
import json
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from promabbix.zabbix.client import WRITE_METHODS


class FakeZabbix:
    def __init__(self, version: str = "7.0.5", password: str = "secret",
                 groups: Optional[List[str]] = None, proxies: Optional[List[str]] = None) -> None:
        self.version = version
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
        return json.dumps(self.exports[names[0]])

    def _m_configuration_import(self, params: Any) -> bool:
        self._register_template_doc(json.loads(params["source"]))
        return True

    def _m_hostgroup_get(self, params: Any) -> List[Dict[str, str]]:
        wanted = params["filter"]["name"]
        return [{"groupid": gid, "name": n} for n, gid in self.groups.items() if n in wanted]

    def _m_proxy_get(self, params: Any) -> List[Dict[str, str]]:
        key = "name" if self.version.startswith("7") else "host"
        return [{"proxyid": pid, key: n} for n, pid in self.proxies.items()]

    def _m_host_get(self, params: Any) -> List[Dict[str, Any]]:
        name = params["filter"]["host"][0]
        return [copy.deepcopy(self.hosts[name])] if name in self.hosts else []

    def _host_from_params(self, params: Dict[str, Any], hostid: str, host: str) -> Dict[str, Any]:
        gid_to_name = {v: k for k, v in self.groups.items()}
        tid_to_name = {v: k for k, v in self.templates.items()}
        proxy_field = "proxyid" if self.version.startswith("7") else "proxy_hostid"
        groups = [{"groupid": g["groupid"], "name": gid_to_name[g["groupid"]]} for g in params["groups"]]
        raw: Dict[str, Any] = {
            "hostid": hostid, "host": host, "name": params["name"], "description": params["description"],
            "status": str(params["status"]), proxy_field: params[proxy_field],
            "parentTemplates": [{"templateid": t["templateid"], "host": tid_to_name[t["templateid"]]}
                                for t in params["templates"]],
            "macros": [dict(m, hostmacroid=str(self._new_id()), type="0") for m in params["macros"]],
            "interfaces": [dict(i, interfaceid=i.get("interfaceid", str(self._new_id()))) for i in params["interfaces"]],
        }
        raw["hostgroups" if self.version >= "6.2" else "groups"] = groups
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
                              "template_groups": [{"uuid": "g1", "name": "Templates"}],
                              "templates": [{
                                  "uuid": "u-" + name, "template": name, "name": name,
                                  "groups": [{"name": "Templates"}],
                                  "items": [{"uuid": "i-" + k, "name": k, "key": "k." + k} for k in items],
                                  "triggers": [{"uuid": "t-" + k, "name": "trig " + k, "expression": "last(/x/k." + k + ")=1"}
                                               for k in items],
                              }]}}
