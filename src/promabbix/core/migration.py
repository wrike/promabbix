#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

"""
Migration utilities for converting legacy three-file format to unified format.

This module provides functionality to:
- Detect legacy vs unified format configurations
- Migrate legacy three-file structures to unified format
- Support builder script integration for format detection
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Union, Optional, cast


def detect_config_format(config_path: Union[str, Path]) -> str:
    """
    Detect whether a configuration is in legacy three-file format or unified format.

    Args:
        config_path: Path to configuration file or directory

    Returns:
        "legacy_three_file" for legacy format, "unified" for unified format

    Raises:
        ValueError: If format cannot be determined
    """
    path = Path(config_path)

    if path.is_file():
        # If it's a single file, it's likely unified format
        try:
            with open(path, 'r') as f:
                config = yaml.safe_load(f)

            # Check if it has the unified format structure
            if isinstance(config, dict) and 'groups' in config and 'zabbix' in config:
                return "unified"
            else:
                raise ValueError(f"Single file {path} doesn't match unified format")
        except Exception as e:
            raise ValueError(f"Could not parse {path}: {e}")

    elif path.is_dir():
        # If it's a directory, check for legacy three-file structure
        # Look for alert files (could be various names ending with _alerts.yaml)
        alert_files = list(path.glob('*_alerts.yaml'))

        # Check if we have the typical legacy structure
        has_zabbix = (path / 'zabbix_vars.yaml').exists()
        has_alerts = len(alert_files) > 0

        if has_zabbix and has_alerts:
            return "legacy_three_file"
        else:
            raise ValueError(f"Directory {path} doesn't match legacy three-file format")

    else:
        raise ValueError(f"Path {config_path} is neither a file nor a directory")


def migrate_legacy_service(service_dir: Union[str, Path]) -> Dict[str, Any]:
    """
    Migrate a legacy three-file service configuration to unified format.

    Args:
        service_dir: Path to service directory containing legacy files

    Returns:
        Dictionary containing unified configuration

    Raises:
        FileNotFoundError: If required legacy files are missing
        ValueError: If legacy files cannot be parsed
    """
    service_path = Path(service_dir)

    if not service_path.is_dir():
        raise ValueError(f"Service path {service_path} is not a directory")

    # Find required files
    alerts_file = _find_alerts_file(service_path)
    zabbix_file = service_path / 'zabbix_vars.yaml'
    wiki_file = service_path / 'wiki_vars.yaml'

    # Build unified configuration
    unified_config = {}
    unified_config['groups'] = _load_alerts_section(alerts_file)
    unified_config['zabbix'] = _load_zabbix_section(zabbix_file)

    # Load optional wiki section
    wiki_data = _load_wiki_section(wiki_file)
    if wiki_data:
        unified_config['wiki'] = wiki_data

    # Add default sections
    _add_default_sections(unified_config)

    return unified_config


def _find_alerts_file(service_path: Path) -> Path:
    """Find the alerts file in the service directory."""
    alert_files = list(service_path.glob('*_alerts.yaml'))
    if not alert_files:
        raise FileNotFoundError(f"No *_alerts.yaml file found in {service_path}")
    return alert_files[0]


def _load_alerts_section(alerts_file: Path) -> Dict[str, Any]:
    """Load and validate alerts section."""
    if not alerts_file.exists():
        raise FileNotFoundError(f"Alerts file {alerts_file} not found")

    with open(alerts_file, 'r') as f:
        alerts_data = yaml.safe_load(f)
        if not (alerts_data and 'groups' in alerts_data):
            raise ValueError(f"Invalid alerts file format in {alerts_file}")
        return cast(Dict[str, Any], alerts_data['groups'])


def _load_zabbix_section(zabbix_file: Path) -> Dict[str, Any]:
    """Load and validate zabbix section."""
    if not zabbix_file.exists():
        raise FileNotFoundError(f"Zabbix configuration file {zabbix_file} not found")

    with open(zabbix_file, 'r') as f:
        zabbix_data = yaml.safe_load(f)
        if not (zabbix_data and 'zabbix' in zabbix_data):
            raise ValueError(f"Invalid zabbix file format in {zabbix_file}")
        return cast(Dict[str, Any], zabbix_data['zabbix'])


def _load_wiki_section(wiki_file: Path) -> Optional[Dict[str, Any]]:
    """Load optional wiki section."""
    if not wiki_file.exists():
        return None

    try:
        with open(wiki_file, 'r') as f:
            wiki_data = yaml.safe_load(f)
            if wiki_data and 'wiki' in wiki_data:
                return cast(Dict[str, Any], wiki_data['wiki'])
    except Exception:
        # Wiki is optional, so we can ignore parsing errors
        pass
    return None


def _add_default_sections(unified_config: Dict[str, Any]) -> None:
    """Add default prometheus and promabbix sections if missing."""
    if 'prometheus' not in unified_config:
        unified_config['prometheus'] = {
            'api': {
                'url': 'http://victoria-metrics.monitoring.svc:8481/api/v1/query'
            }
        }

    if 'promabbix' not in unified_config:
        unified_config['promabbix'] = {
            'zabbix_depend_item_preprocessing': '$.metrics["{#ZBX.ITEM.SUBKEY}"]',
            'zabbix_master_item_preprocessing': '''var ingest_json = JSON.parse(value),
    metrics = ingest_json.data.result || [],
    result = { "lld": [], "metrics": {} };
for (var i = 0; i < metrics.length; i++) {
    var metric = metrics[i];
    var labels = metric.metric || {};
    var key = Object.keys(labels).map(k => labels[k]).join('_') || 'default';
    result.lld.push(labels);
    result.metrics[key] = metric.value[1];
}
return JSON.stringify(result);'''
        }


def detect_builder_script_format(config_path: Union[str, Path]) -> Optional[str]:
    """
    Detect configuration format for builder script integration.

    This function is designed to be called from bash builder scripts
    and returns format strings that can be easily processed by shell scripts.

    Args:
        config_path: Path to configuration file or directory

    Returns:
        "legacy" or "unified" or None if detection fails
    """
    try:
        format_type = detect_config_format(config_path)
        if format_type == "legacy_three_file":
            return "legacy"
        elif format_type == "unified":
            return "unified"
        else:
            return None
    except Exception:
        return None


def save_unified_config(config: Dict[str, Any], output_path: Union[str, Path]) -> None:
    """
    Save unified configuration to a file.

    Args:
        config: Unified configuration dictionary
        output_path: Path where to save the unified configuration
    """
    output_file = Path(output_path)

    # Ensure parent directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, indent=2)
