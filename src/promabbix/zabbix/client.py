#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#
"""Minimal Zabbix JSON-RPC client built on ``urllib.request`` (no third-party dependencies)."""

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, FrozenSet, Optional, Tuple

#: API methods that mutate Zabbix configuration. Dry-run code paths must never reach these;
#: a client created with ``read_only=True`` refuses to send them at all.
WRITE_METHODS: FrozenSet[str] = frozenset({
    "configuration.import",
    "host.create", "host.update", "host.delete", "host.massadd", "host.massupdate", "host.massremove",
    "template.create", "template.update", "template.delete",
    "hostgroup.create", "hostgroup.update", "hostgroup.delete",
    "templategroup.create", "templategroup.update", "templategroup.delete",
    "item.create", "item.update", "item.delete",
    "trigger.create", "trigger.update", "trigger.delete",
    "discoveryrule.create", "discoveryrule.update", "discoveryrule.delete",
    "usermacro.create", "usermacro.update", "usermacro.delete",
    "usermacro.createglobal", "usermacro.updateglobal", "usermacro.deleteglobal",
    "proxy.create", "proxy.update", "proxy.delete",
})

#: Methods that must be called without any authentication.
_UNAUTHENTICATED_METHODS: FrozenSet[str] = frozenset({"apiinfo.version", "user.login"})

JSONRPC_PATH = "api_jsonrpc.php"

#: ``transport(request, timeout) -> raw response body``. Injectable for tests.
Transport = Callable[[urllib.request.Request, float], bytes]


class ZabbixAPIError(Exception):
    """Zabbix returned a JSON-RPC error, or the response could not be understood."""

    def __init__(self, message: str, code: Optional[int] = None, data: Optional[str] = None,
                 method: Optional[str] = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        self.method = method
        super().__init__(self._format())

    def _format(self) -> str:
        parts = [self.message]
        if self.data:
            parts.append(str(self.data))
        text = " ".join(parts)
        prefix = f"{self.method}: " if self.method else ""
        suffix = f" (code {self.code})" if self.code is not None else ""
        return f"{prefix}{text}{suffix}"


class ZabbixConnectionError(ZabbixAPIError):
    """HTTP/transport-level failure: connection refused, timeout, non-200 status."""


class ZabbixAuthError(ZabbixAPIError):
    """Login failed."""


class ZabbixWriteBlockedError(ZabbixAPIError):
    """A write method was attempted on a read-only client."""


def _default_transport(request: urllib.request.Request, timeout: float) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is operator supplied
            return bytes(response.read())
    except urllib.error.HTTPError as e:
        raise ZabbixConnectionError(f"HTTP {e.code} {e.reason} from {request.full_url}", code=e.code) from e
    except urllib.error.URLError as e:
        raise ZabbixConnectionError(f"cannot reach {request.full_url}: {e.reason}") from e
    except (socket.timeout, TimeoutError) as e:
        raise ZabbixConnectionError(f"timeout after {timeout}s talking to {request.full_url}") from e


def parse_version(version: str) -> Tuple[int, int]:
    """Return (major, minor) of a Zabbix version string such as ``7.0.3`` or ``6.4.0rc1``."""
    parts = version.split(".")
    try:
        return int(parts[0]), int("".join(ch for ch in parts[1] if ch.isdigit()) or 0)
    except (ValueError, IndexError) as e:
        raise ZabbixAPIError(f"unparseable Zabbix API version {version!r}") from e


class ZabbixClient:
    """JSON-RPC client for ``<url>/api_jsonrpc.php``.

    Login is lazy (first authenticated call). ``close()`` logs out. Zabbix 7.0+ authenticates with an
    ``Authorization: Bearer`` header; older servers get the legacy ``auth`` body field. ``username``
    is used for the login parameter on 6.4+, ``user`` before that.
    """

    def __init__(self, url: str, user: str, password: str, timeout: float = 60.0,
                 read_only: bool = False, transport: Optional[Transport] = None) -> None:
        self.endpoint = url.rstrip("/") + "/" + JSONRPC_PATH
        self._user = user
        self._password = password
        self.timeout = timeout
        self.read_only = read_only
        self._transport: Transport = transport or _default_transport
        self._token: Optional[str] = None
        self._version: Optional[str] = None
        self._request_id = 0

    def __repr__(self) -> str:
        return f"ZabbixClient(endpoint={self.endpoint!r}, user={self._user!r}, read_only={self.read_only})"

    def __enter__(self) -> "ZabbixClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @staticmethod
    def is_write_method(method: str) -> bool:
        return method in WRITE_METHODS

    @property
    def api_version(self) -> str:
        if self._version is None:
            self._version = str(self._rpc("apiinfo.version", {}, auth=False))
        return self._version

    @property
    def version(self) -> Tuple[int, int]:
        return parse_version(self.api_version)

    def login(self) -> None:
        user_param = "username" if self.version >= (6, 4) else "user"
        try:
            token = self._rpc("user.login", {user_param: self._user, "password": self._password}, auth=False)
        except ZabbixConnectionError:
            raise
        except ZabbixAPIError as e:
            raise ZabbixAuthError(f"login failed for user {self._user!r}: {e.message}",
                                  code=e.code, data=e.data, method="user.login") from e
        if not isinstance(token, str) or not token:
            raise ZabbixAuthError("login returned no session token", method="user.login")
        self._token = token

    def close(self) -> None:
        """Log out (best effort). Safe to call repeatedly."""
        if self._token is None:
            return
        try:
            self._rpc("user.logout", [], auth=True)
        except ZabbixAPIError:
            pass
        finally:
            self._token = None

    def call(self, method: str, params: Any = None) -> Any:
        """Call an authenticated API method, logging in first if necessary."""
        if method in WRITE_METHODS and self.read_only:
            raise ZabbixWriteBlockedError("write method refused by read-only client", method=method)
        if method in _UNAUTHENTICATED_METHODS:
            return self._rpc(method, params if params is not None else {}, auth=False)
        if self._token is None:
            self.login()
        return self._rpc(method, params if params is not None else {}, auth=True)

    def _rpc(self, method: str, params: Any, auth: bool) -> Any:
        self._request_id += 1
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params, "id": self._request_id}
        headers = {"Content-Type": "application/json-rpc"}
        if auth and self._token is not None:
            if self.version >= (7, 0):
                headers["Authorization"] = f"Bearer {self._token}"
            else:
                payload["auth"] = self._token
        request = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode("utf-8"),
                                         headers=headers, method="POST")
        raw = self._transport(request, self.timeout)
        return self._unwrap(method, raw)

    @staticmethod
    def _unwrap(method: str, raw: bytes) -> Any:
        try:
            body = json.loads(raw)
        except (ValueError, TypeError) as e:
            raise ZabbixAPIError("response is not valid JSON", method=method) from e
        if not isinstance(body, dict):
            raise ZabbixAPIError("unexpected response shape", method=method)
        error = body.get("error")
        if error:
            raise ZabbixAPIError(str(error.get("message", "unknown error")), code=error.get("code"),
                                 data=error.get("data"), method=method)
        if "result" not in body:
            raise ZabbixAPIError("response has neither result nor error", method=method)
        return body["result"]
