#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#
"""syncTemplate / syncPseudoHosts commands: push a service's template (and pseudo-hosts) to Zabbix."""

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple, cast

import click
import yaml
from rich.console import Console

from ..core.fs_utils import DataLoader
from ..core.loader import load_service
from ..core.template import Render
from ..core.validation import ConfigValidator, ValidationError
from ..zabbix.client import ZabbixAPIError, ZabbixClient
from ..zabbix.sync import (ServiceResult, SyncError, render_service_result, render_template_result,
                           sync_service, sync_template)

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_CHANGES = 2  # --exit-code and changes exist

AUTH_FILE_NAMES = (".zbx_auth.yml", ".zbx_auth.yaml", ".zbx_auth.json")
DEFAULT_TEMPLATE_NAME = "prometheus_alert_rules_to_zbx_template.j2"


class CredentialsError(Exception):
    """Zabbix credentials could not be resolved."""


def _load_config(path: str, common_dirs: Iterable[str]) -> Dict[str, Any]:
    """Load a service directory (merged over ``common_dirs``) or a unified single file."""
    commons = list(common_dirs)
    if os.path.isdir(path):
        return load_service(path, commons)
    if commons:
        raise ValueError("--common can only be used when the input is a service directory")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Configuration file not found: {path}")
    return cast(Dict[str, Any], DataLoader().load_from_file(path))


def _read_auth_file(home: Optional[Path] = None) -> Dict[str, Any]:
    base = home or Path(os.path.expanduser("~"))
    for name in AUTH_FILE_NAMES:
        candidate = base / name
        if candidate.is_file():
            try:
                data = yaml.safe_load(candidate.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError) as e:
                raise CredentialsError(f"cannot read {candidate}: {e}") from e
            if not isinstance(data, dict):
                raise CredentialsError(f"{candidate} must contain a mapping with zbx_url/zbx_username/zbx_password")
            return data
    return {}


def resolve_credentials(url: Optional[str], user: Optional[str], password: Optional[str],
                        env: Optional[Mapping[str, str]] = None) -> Tuple[str, str, str]:
    """Per field: CLI flag, then ZABBIX_URL/ZABBIX_USER/ZABBIX_PASSWORD, then ~/.zbx_auth.yml."""
    environ = os.environ if env is None else env
    file_data: Optional[Dict[str, Any]] = None
    resolved: Dict[str, Optional[str]] = {}
    spec = (("url", url, "ZABBIX_URL", "zbx_url"), ("user", user, "ZABBIX_USER", "zbx_username"),
            ("password", password, "ZABBIX_PASSWORD", "zbx_password"))
    for field_name, cli_value, env_key, file_key in spec:
        value = cli_value or environ.get(env_key)
        if not value:
            if file_data is None:
                file_data = _read_auth_file()
            file_value = file_data.get(file_key)
            value = str(file_value) if file_value not in (None, "") else None
        resolved[field_name] = value
    missing = [k for k, v in resolved.items() if not v]
    if missing:
        raise CredentialsError(
            f"missing Zabbix {', '.join(missing)}: use --zabbix-url/--zabbix-user/--zabbix-password, "
            "ZABBIX_URL/ZABBIX_USER/ZABBIX_PASSWORD or ~/.zbx_auth.yml (zbx_url, zbx_username, zbx_password)")
    return cast(str, resolved["url"]), cast(str, resolved["user"]), cast(str, resolved["password"])


def generate_template_json(config: Dict[str, Any]) -> str:
    """Validate the config and render the Zabbix template JSON in memory."""
    ConfigValidator().validate_config(config)
    templates_dir = f"{os.path.abspath(os.path.dirname(__file__))}/../templates/"
    rendered = Render().render_file(template_path=templates_dir, template_name=DEFAULT_TEMPLATE_NAME, data=config)
    try:
        json.loads(rendered)
    except ValueError as e:
        raise SyncError(f"generated template is not valid JSON: {e}") from e
    return str(rendered)


ClientFactory = Callable[[str, str, str, float, bool], ZabbixClient]


def _default_client_factory(url: str, user: str, password: str, timeout: float, read_only: bool) -> ZabbixClient:
    return ZabbixClient(url, user, password, timeout=timeout, read_only=read_only)


class SyncCommand:
    """Shared implementation for both commands. ``client_factory`` is injectable for tests."""

    def __init__(self, client_factory: Optional[ClientFactory] = None,
                 config_loader: Optional[Callable[[str, Iterable[str]], Dict[str, Any]]] = None,
                 out: Optional[Callable[[str], None]] = None) -> None:
        self.client_factory = client_factory or _default_client_factory
        self.config_loader = config_loader or _load_config
        self.out = out or click.echo
        self.console = Console(stderr=True)

    def execute(self, path: str, common_dirs: Iterable[str], dry_run: bool, exit_code: bool,
                with_hosts: bool, url: Optional[str] = None, user: Optional[str] = None,
                password: Optional[str] = None, timeout: float = 60.0) -> int:
        try:
            config = self.config_loader(path, list(common_dirs))
            template_json = generate_template_json(config)
            zbx_url, zbx_user, zbx_password = resolve_credentials(url, user, password)
        except ValidationError as e:
            self.console.print(f"[red]Configuration validation failed:[/red] {e}")
            return EXIT_FAILURE
        except (CredentialsError, SyncError, OSError, ValueError) as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return EXIT_FAILURE

        # A dry-run client is read-only: write methods are refused at the transport boundary too.
        client = self.client_factory(zbx_url, zbx_user, zbx_password, timeout, dry_run)
        try:
            return self._run(client, config, template_json, dry_run, exit_code, with_hosts)
        except ZabbixAPIError as e:
            self.console.print(f"[red]Zabbix API error: {e}[/red]")
            return EXIT_FAILURE
        finally:
            client.close()

    def _run(self, client: ZabbixClient, config: Dict[str, Any], template_json: str, dry_run: bool,
             exit_code: bool, with_hosts: bool) -> int:
        if with_hosts:
            service = sync_service(config, template_json, client, dry_run)
            self.out(render_service_result(service, dry_run))
            failed, changes = service.failed, service.has_changes
            removals = service.removals
        else:
            try:
                template = sync_template(template_json, client, dry_run)
            except (SyncError, ZabbixAPIError) as e:
                self.console.print(f"[red]template sync failed: {e}[/red]")
                return EXIT_FAILURE
            self.out(render_template_result(template, dry_run))
            failed, changes, removals = False, template.has_changes, template.removals
        if failed:
            self._print_failures(service if with_hosts else None)
            return EXIT_FAILURE
        if removals and dry_run:
            self.console.print(f"[yellow]{removals} removal(s) would be applied by a real run[/yellow]")
        if dry_run and exit_code and changes:
            return EXIT_CHANGES
        return EXIT_OK

    def _print_failures(self, service: Optional[ServiceResult]) -> None:
        if service is None:
            return
        if service.error:
            self.console.print(f"[red]{service.error}[/red]")
        for host in service.hosts.failures:
            self.console.print(f"[red]host {host.host_name} failed: {host.error}[/red]")


def _common_options(func: Callable[..., None]) -> Callable[..., None]:
    options: List[Callable[[Callable[..., None]], Callable[..., None]]] = [
        click.argument('config_path', type=str),
        click.option('--common', 'common', multiple=True, type=click.Path(),
                     help='Common config directory merged under the service (repeatable)'),
        click.option('--dry-run', is_flag=True, help='Read-only: print the diff against live Zabbix, write nothing'),
        click.option('--exit-code', 'exit_code', is_flag=True,
                     help='With --dry-run, exit with status 2 when changes exist'),
        click.option('--zabbix-url', default=None, help='Zabbix URL (env ZABBIX_URL, ~/.zbx_auth.yml zbx_url)'),
        click.option('--zabbix-user', default=None, help='Zabbix user (env ZABBIX_USER, ~/.zbx_auth.yml zbx_username)'),
        click.option('--zabbix-password', default=None,
                     help='Zabbix password (env ZABBIX_PASSWORD, ~/.zbx_auth.yml zbx_password)'),
        click.option('--timeout', type=float, default=60.0, show_default=True, help='HTTP timeout in seconds'),
    ]
    for option in reversed(options):
        func = option(func)
    return func


def _run_command(with_hosts: bool, config_path: str, common: Tuple[str, ...], dry_run: bool, exit_code: bool,
                 zabbix_url: Optional[str], zabbix_user: Optional[str], zabbix_password: Optional[str],
                 timeout: float) -> None:
    code = SyncCommand().execute(config_path, common, dry_run, exit_code, with_hosts,
                                 zabbix_url, zabbix_user, zabbix_password, timeout)
    if code != EXIT_OK:
        sys.exit(code)


@click.command(name='syncTemplate')
@_common_options
def sync_template_cmd(config_path: str, common: Tuple[str, ...], dry_run: bool, exit_code: bool,
                      zabbix_url: Optional[str], zabbix_user: Optional[str], zabbix_password: Optional[str],
                      timeout: float) -> None:
    """Generate the template for CONFIG_PATH and import it into Zabbix (skipped when unchanged)."""
    _run_command(False, config_path, common, dry_run, exit_code, zabbix_url, zabbix_user, zabbix_password, timeout)


@click.command(name='syncPseudoHosts')
@_common_options
def sync_pseudo_hosts_cmd(config_path: str, common: Tuple[str, ...], dry_run: bool, exit_code: bool,
                          zabbix_url: Optional[str], zabbix_user: Optional[str],
                          zabbix_password: Optional[str], timeout: float) -> None:
    """syncTemplate, then create/update the zabbix.hosts[] pseudo-hosts of CONFIG_PATH."""
    _run_command(True, config_path, common, dry_run, exit_code, zabbix_url, zabbix_user, zabbix_password, timeout)
