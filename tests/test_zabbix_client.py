# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#
"""Tests for the JSON-RPC client: auth flow, error mapping, write-method registry, HTTP failures."""

import io
import json
import socket
import urllib.error
from unittest import mock

import pytest

from promabbix.zabbix import client as client_mod
from promabbix.zabbix.client import (WRITE_METHODS, ZabbixAPIError, ZabbixAuthError, ZabbixClient,
                                     ZabbixConnectionError, ZabbixWriteBlockedError, parse_version)
from tests.zabbix_fake import FakeZabbix


def make(fake, **kw):
    return ZabbixClient("https://zbx.example.com/", "svc", "secret", transport=fake, **kw)


class TestAuthFlow:
    def test_endpoint_is_normalised(self):
        assert make(FakeZabbix()).endpoint == "https://zbx.example.com/api_jsonrpc.php"

    def test_v7_uses_username_param_and_bearer_header(self):
        fake = FakeZabbix(version="7.0.5")
        c = make(fake)
        c.call("template.get", {"filter": {"host": ["x"]}})
        login = fake.calls_of("user.login")[0]
        assert login["params"] == {"username": "svc", "password": "secret"}
        assert "authorization" not in login["headers"] and login["auth"] is None
        call = fake.calls_of("template.get")[0]
        assert call["headers"]["authorization"] == "Bearer tok-123"
        assert call["auth"] is None

    def test_v64_uses_username_param_and_legacy_auth_field(self):
        fake = FakeZabbix(version="6.4.1")
        make(fake).call("template.get", {"filter": {"host": ["x"]}})
        assert fake.calls_of("user.login")[0]["params"] == {"username": "svc", "password": "secret"}
        call = fake.calls_of("template.get")[0]
        assert call["auth"] == "tok-123"
        assert "authorization" not in call["headers"]

    def test_pre_64_uses_user_param(self):
        fake = FakeZabbix(version="6.0.20")
        make(fake).call("template.get", {"filter": {"host": ["x"]}})
        assert fake.calls_of("user.login")[0]["params"] == {"user": "svc", "password": "secret"}

    def test_login_is_lazy_and_happens_once(self):
        fake = FakeZabbix()
        c = make(fake)
        assert fake.calls == []
        c.call("template.get", {"filter": {"host": []}})
        c.call("template.get", {"filter": {"host": []}})
        assert fake.methods.count("user.login") == 1
        assert fake.methods.count("apiinfo.version") == 1

    def test_logout_on_close_and_context_manager(self):
        fake = FakeZabbix()
        with make(fake) as c:
            c.call("template.get", {"filter": {"host": []}})
        assert fake.methods[-1] == "user.logout"
        assert fake.calls[-1]["headers"]["authorization"] == "Bearer tok-123"
        c.close()  # idempotent
        assert fake.methods.count("user.logout") == 1

    def test_close_without_login_makes_no_calls(self):
        fake = FakeZabbix()
        make(fake).close()
        assert fake.calls == []

    def test_logout_failure_is_swallowed(self):
        fake = FakeZabbix()
        c = make(fake)
        c.call("template.get", {"filter": {"host": []}})
        fake.errors["user.logout"] = (-32500, "Application error.", "session expired")
        c.close()  # no raise

    def test_bad_password_raises_auth_error_with_details(self):
        fake = FakeZabbix(password="right")
        with pytest.raises(ZabbixAuthError) as ei:
            make(fake).call("template.get", {"filter": {"host": []}})
        assert ei.value.code == -32602
        assert "Login name or password is incorrect" in ei.value.data
        assert "svc" in str(ei.value)
        assert "secret" not in str(ei.value)
        assert fake.methods == ["apiinfo.version", "user.login"]

    def test_login_without_token_is_an_error(self):
        fake = FakeZabbix()
        fake.errors["user.login"] = None
        fake._m_user_login = lambda params: ""  # type: ignore[method-assign]
        with pytest.raises(ZabbixAuthError, match="no session token"):
            make(fake).call("template.get", {})

    def test_timeout_is_passed_to_transport(self):
        fake = FakeZabbix()
        make(fake, timeout=7.5).call("template.get", {"filter": {"host": []}})
        assert {c["timeout"] for c in fake.calls} == {7.5}

    def test_repr_hides_password(self):
        assert "secret" not in repr(make(FakeZabbix()))


class TestErrors:
    def test_api_error_carries_code_message_data_method(self):
        fake = FakeZabbix()
        fake.errors["template.get"] = (-32602, "Invalid params.", "Invalid parameter \"/\": unexpected.")
        with pytest.raises(ZabbixAPIError) as ei:
            make(fake).call("template.get", {})
        e = ei.value
        assert (e.code, e.message, e.data, e.method) == (-32602, "Invalid params.", "Invalid parameter \"/\": unexpected.", "template.get")
        assert "template.get" in str(e) and "-32602" in str(e) and "unexpected" in str(e)

    def test_non_json_response(self):
        fake = FakeZabbix()
        c = make(fake)
        c.call("template.get", {"filter": {"host": []}})
        fake.raw_body = b"<html>502 Bad Gateway</html>"
        with pytest.raises(ZabbixAPIError, match="not valid JSON"):
            c.call("template.get", {})

    @pytest.mark.parametrize("body,msg", [(b"[1]", "unexpected response shape"),
                                          (b'{"jsonrpc":"2.0","id":1}', "neither result nor error")])
    def test_odd_bodies(self, body, msg):
        fake = FakeZabbix()
        c = make(fake)
        c.call("template.get", {"filter": {"host": []}})
        fake.raw_body = body
        with pytest.raises(ZabbixAPIError, match=msg):
            c.call("template.get", {})

    def test_transport_error_propagates_as_connection_error(self):
        fake = FakeZabbix()
        fake.http_status = 503
        with pytest.raises(ZabbixConnectionError) as ei:
            make(fake).call("template.get", {})
        assert ei.value.code == 503

    def test_connection_error_during_login_is_not_reported_as_bad_credentials(self):
        fake = FakeZabbix()
        c = make(fake)
        c.api_version  # populate version first
        fake.http_status = 500
        with pytest.raises(ZabbixConnectionError) as ei:
            c.login()
        assert not isinstance(ei.value, ZabbixAuthError)

    @pytest.mark.parametrize("v,expected", [("7.0.5", (7, 0)), ("6.4.0rc1", (6, 4)), ("6.0.20", (6, 0)),
                                            ("7.2.0alpha1", (7, 2))])
    def test_parse_version(self, v, expected):
        assert parse_version(v) == expected

    @pytest.mark.parametrize("v", ["", "garbage", "7"])
    def test_parse_version_rejects(self, v):
        with pytest.raises(ZabbixAPIError):
            parse_version(v)


class TestWriteMethods:
    @pytest.mark.parametrize("m", ["configuration.import", "host.create", "host.update", "host.delete",
                                   "template.update", "usermacro.create", "item.delete"])
    def test_registered(self, m):
        assert m in WRITE_METHODS and ZabbixClient.is_write_method(m)

    @pytest.mark.parametrize("m", ["host.get", "template.get", "configuration.export", "user.login",
                                   "apiinfo.version", "proxy.get", "hostgroup.get"])
    def test_reads_are_not_writes(self, m):
        assert m not in WRITE_METHODS

    @pytest.mark.parametrize("m", sorted(WRITE_METHODS))
    def test_read_only_client_refuses_every_write_without_any_request(self, m):
        fake = FakeZabbix()
        with pytest.raises(ZabbixWriteBlockedError):
            make(fake, read_only=True).call(m, {})
        assert fake.calls == []

    def test_read_only_client_still_reads(self):
        fake = FakeZabbix()
        assert make(fake, read_only=True).call("template.get", {"filter": {"host": []}}) == []


class TestDefaultTransport:
    @staticmethod
    def request():
        import urllib.request
        return urllib.request.Request("https://zbx.example.com/api_jsonrpc.php", data=b"{}")

    def test_success_returns_body_and_passes_timeout(self):
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = b'{"ok":1}'
        with mock.patch.object(client_mod.urllib.request, "urlopen", return_value=resp) as urlopen:
            assert client_mod._default_transport(self.request(), 12.0) == b'{"ok":1}'
        assert urlopen.call_args.kwargs["timeout"] == 12.0

    def test_http_error(self):
        err = urllib.error.HTTPError("u", 502, "Bad Gateway", {}, io.BytesIO(b""))  # type: ignore[arg-type]
        with mock.patch.object(client_mod.urllib.request, "urlopen", side_effect=err):
            with pytest.raises(ZabbixConnectionError, match="HTTP 502") as ei:
                client_mod._default_transport(self.request(), 1)
        assert ei.value.code == 502

    def test_url_error(self):
        with mock.patch.object(client_mod.urllib.request, "urlopen",
                               side_effect=urllib.error.URLError("connection refused")):
            with pytest.raises(ZabbixConnectionError, match="connection refused"):
                client_mod._default_transport(self.request(), 1)

    def test_socket_timeout(self):
        with mock.patch.object(client_mod.urllib.request, "urlopen", side_effect=socket.timeout()):
            with pytest.raises(ZabbixConnectionError, match="timeout after 3"):
                client_mod._default_transport(self.request(), 3)

    def test_default_transport_end_to_end_through_client(self):
        bodies = iter([b'{"jsonrpc":"2.0","id":1,"result":"7.0.1"}'])
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.side_effect = lambda: next(bodies)
        with mock.patch.object(client_mod.urllib.request, "urlopen", return_value=resp):
            c = ZabbixClient("https://zbx.example.com", "u", "p")
            assert c.api_version == "7.0.1"
