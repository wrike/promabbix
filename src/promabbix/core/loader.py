#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

"""
Directory input for promabbix: merge ``common/`` directories and a service directory
into a single unified configuration.

Rules (shared by ``generateTemplate <dir>`` and any future command that takes a service dir):

* Every ``*.yaml`` / ``*.yml`` file (non-recursive, hidden files skipped) of each ``--common``
  directory and then of the service directory is loaded in sorted file-name order.
  Common directories are applied first, in the order given, so the service overrides them.
* Files are deep-merged: dicts recursively, lists APPENDED, scalars: later wins
  (same as ``yq eval-all '. as $item ireduce ({}; . *+ $item)'``).
* Wiki-only files (``*wiki_vars.yaml`` / ``*wiki_vars.yml``) found in a ``--common`` directory are
  skipped: they carry keys (``wiki.url``, ``wiki.base_space_path``) for the wiki page generators
  that the unified schema rejects. Service-level ``wiki_vars.yaml`` is a valid ``wiki`` section
  and is merged like any other file.
* ``groups`` is normalised to exactly two canonical entries: ``recording_rules`` (all recording
  rules, concatenated) and ``alerting_rules`` (all alerting rules, concatenated).

Defaults (master item JS, Prometheus API URL, ...) are NOT injected here: the Jinja2 template owns them.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import yaml

from .data_utils import deep_merge_append

try:
    from yaml import CSafeLoader as _SafeLoader
except ImportError:  # pragma: no cover
    from yaml import SafeLoader as _SafeLoader  # type: ignore[assignment]

YAML_SUFFIXES = ('.yaml', '.yml')
WIKI_VARS_STEM_SUFFIX = 'wiki_vars'
RECORDING_RULES = 'recording_rules'
ALERTING_RULES = 'alerting_rules'


class ServiceLoadError(ValueError):
    """Raised when a service directory (or one of its common dirs) cannot be loaded."""


def list_yaml_files(directory: Union[str, Path], skip_wiki_vars: bool = False) -> List[Path]:
    """Return ``*.yaml`` / ``*.yml`` files of a directory (non-recursive) in sorted name order."""
    path = Path(directory)
    if not path.is_dir():
        raise ServiceLoadError(f"Directory not found: {path}")
    files = [
        f for f in path.iterdir()
        if f.is_file() and f.suffix.lower() in YAML_SUFFIXES and not f.name.startswith('.')
    ]
    if skip_wiki_vars:
        files = [f for f in files if not f.stem.lower().endswith(WIKI_VARS_STEM_SUFFIX)]
    return sorted(files, key=lambda f: f.name)


def load_yaml_mapping(path: Path) -> Dict[str, Any]:
    """Load one YAML file that must contain a mapping at top level (empty file -> ``{}``)."""
    try:
        data = yaml.load(path.read_text(encoding='utf-8'), Loader=_SafeLoader)
    except (OSError, yaml.YAMLError) as e:
        raise ServiceLoadError(f"Cannot read {path}: {e}")
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ServiceLoadError(f"{path}: top level must be a mapping, got {type(data).__name__}")
    return data


def normalize_groups(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Collapse ``config['groups']`` into exactly two canonical groups (in place).

    All rules of every ``recording_rules`` group are concatenated into one ``recording_rules``
    group and all rules of every ``alerting_rules`` group into one ``alerting_rules`` group,
    preserving order. Groups with any other name are kept untouched after the canonical two so
    that schema validation can report them.

    Raises:
        ServiceLoadError: if ``groups`` is missing/malformed or holds no rules at all.
    """
    groups = config.get('groups')
    if not isinstance(groups, list) or not groups:
        raise ServiceLoadError(
            "No 'groups' found: the service needs at least one alerts file "
            "(e.g. cpu_alerts.yaml) with 'recording_rules' / 'alerting_rules' groups")

    rules: Dict[str, List[Any]] = {RECORDING_RULES: [], ALERTING_RULES: []}
    others: List[Any] = []
    for group in groups:
        if not isinstance(group, dict):
            raise ServiceLoadError(f"Invalid group entry (expected mapping): {group!r}")
        name = group.get('name')
        if name not in rules:
            others.append(group)
            continue
        group_rules = group.get('rules') or []
        if not isinstance(group_rules, list):
            raise ServiceLoadError(f"Group '{name}': 'rules' must be a list")
        rules[name].extend(group_rules)

    if not rules[RECORDING_RULES] and not rules[ALERTING_RULES] and not others:
        raise ServiceLoadError("No rules found in any group: the service has no alerts to generate")

    config['groups'] = [
        {'name': RECORDING_RULES, 'rules': rules[RECORDING_RULES]},
        {'name': ALERTING_RULES, 'rules': rules[ALERTING_RULES]},
    ] + others
    return config


def load_service(service_dir: Union[str, Path],
                 common_dirs: Optional[Sequence[Union[str, Path]]] = None) -> Dict[str, Any]:
    """
    Load a service directory, merged over zero or more common directories.

    Args:
        service_dir: directory with the service's ``*.yaml`` files (alerts, zabbix_vars, ...)
        common_dirs: directories applied first, in order; the service overrides them

    Returns:
        Unified configuration dict with ``groups`` normalised to two entries.

    Raises:
        ServiceLoadError: missing directory, unparsable/non-mapping file, empty service
            directory, or a service without any rules.
    """
    service_files = list_yaml_files(service_dir)
    if not service_files:
        raise ServiceLoadError(f"No *.yaml / *.yml files found in service directory {service_dir}")

    merged: Dict[str, Any] = {}
    for common_dir in common_dirs or ():
        for path in list_yaml_files(common_dir, skip_wiki_vars=True):
            merged = deep_merge_append(merged, load_yaml_mapping(path))
    for path in service_files:
        merged = deep_merge_append(merged, load_yaml_mapping(path))

    try:
        return normalize_groups(merged)
    except ServiceLoadError as e:
        raise ServiceLoadError(f"{service_dir}: {e}")
