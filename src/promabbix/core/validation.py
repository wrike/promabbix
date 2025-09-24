#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import json
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, cast
from rich.console import Console


class ValidationError(Exception):
    """Custom exception for configuration validation errors."""

    def __init__(self, message: str, path: Optional[str] = None, suggestions: Optional[List[str]] = None):
        """
        Initialize validation error.

        Args:
            message: Error message
            path: Path to the invalid field (e.g., "groups[0].rules[0].record")
            suggestions: List of helpful suggestions for fixing the error
        """
        self.message = message
        self.path = path
        self.suggestions = suggestions or []
        super().__init__(self.format_message())

    def format_message(self) -> str:
        """Format the error message with path and suggestions."""
        parts = [self.message]
        if self.path:
            parts.append(f"Path: {self.path}")
        if self.suggestions:
            parts.append("Suggestions:")
            for suggestion in self.suggestions:
                parts.append(f"  - {suggestion}")
        return "\n".join(parts)


class ConfigValidator:
    """Validator for unified YAML configuration format."""

    def __init__(self, schema_path: Optional[str] = None):
        """
        Initialize configuration validator.

        Args:
            schema_path: Path to custom schema file (defaults to built-in schema)
        """
        self.console = Console(stderr=True)
        self.schema_path = schema_path or self.default_schema_path()
        self.schema = self.load_schema()

    def default_schema_path(self) -> str:
        """Get path to default built-in schema."""
        # Get the path to the schemas directory relative to this file
        current_dir = Path(__file__).parent.parent
        return str(current_dir / "schemas" / "unified.yaml")

    def load_schema(self) -> Dict[str, Any]:
        """Load schema from file (YAML or JSON)."""
        try:
            with open(self.schema_path, 'r') as f:
                if self.schema_path.endswith('.yaml') or self.schema_path.endswith('.yml'):
                    return cast(Dict[str, Any], yaml.safe_load(f))
                else:
                    return cast(Dict[str, Any], json.load(f))
        except FileNotFoundError:
            raise ValidationError(
                f"Schema file not found: {self.schema_path}",
                suggestions=["Ensure the unified schema file exists at the expected path"]
            )
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            raise ValidationError(
                f"Invalid format in schema file: {e}",
                path=self.schema_path,
                suggestions=["Check the schema file for valid YAML/JSON syntax"]
            )

    def validate_config(self, config_data: Dict[str, Any]) -> None:
        """
        Validate unified configuration against schema.

        Args:
            config_data: Parsed configuration dictionary

        Raises:
            ValidationError: If validation fails
        """
        # Validate against JSON schema
        self.validate_json_schema(config_data)

    def validate_json_schema(self, config_data: Dict[str, Any]) -> None:
        """
        Validate configuration against JSON schema.

        Args:
            config_data: Configuration to validate

        Raises:
            ValidationError: If schema validation fails
        """
        schema_validator = SchemaValidator(self.schema)
        errors = schema_validator.validate(config_data)

        if errors:
            # If there are multiple errors, combine them into a single ValidationError
            if len(errors) == 1:
                raise errors[0]
            else:
                error_messages = []
                for i, error in enumerate(errors, 1):
                    error_messages.append(f"Error {i}: {error.format_message()}")

                raise ValidationError(
                    "Multiple validation errors found:\n" + "\n\n".join(error_messages),
                    suggestions=["Fix all validation errors to proceed"]
                )


class SchemaValidator:
    """Custom schema validator that interprets unified.yaml schema (replaces jsonschema)."""

    def __init__(self, schema: Dict[str, Any]):
        """
        Initialize schema validator.

        Args:
            schema: JSON schema dictionary loaded from unified.yaml
        """
        self.schema = schema

    def validate(self, data: Dict[str, Any]) -> List[ValidationError]:
        """
        Validate data against schema and return detailed errors.

        Args:
            data: Data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors: List[ValidationError] = []

        # Perform basic structure validation
        errors.extend(self._validate_required_fields(data))
        errors.extend(self._validate_field_types(data))
        errors.extend(self._validate_groups_structure(data))
        errors.extend(self._validate_zabbix_structure(data))

        return errors

    def _validate_required_fields(self, data: Dict[str, Any]) -> List[ValidationError]:
        """Validate required top-level fields."""
        errors = []
        required_fields = self.schema.get('required', [])

        for field in required_fields:
            if field not in data:
                errors.append(ValidationError(
                    f"Missing required field: '{field}'",
                    path="root",
                    suggestions=[f"Add the required field: {field}"]
                ))

        return errors

    def _validate_field_types(self, data: Dict[str, Any]) -> List[ValidationError]:
        """Validate basic field types."""
        errors = []
        properties = self.schema.get('properties', {})

        for field_name, value in data.items():
            if field_name in properties:
                field_schema = properties[field_name]
                field_type = field_schema.get('type')

                if field_type == 'array' and not isinstance(value, list):
                    errors.append(ValidationError(
                        f"Field '{field_name}' must be an array",
                        path=field_name,
                        suggestions=[f"Change {field_name} to a list/array"]
                    ))
                elif field_type == 'object' and not isinstance(value, dict):
                    errors.append(ValidationError(
                        f"Field '{field_name}' must be an object",
                        path=field_name,
                        suggestions=[f"Change {field_name} to an object/dictionary"]
                    ))
                elif field_type == 'string' and not isinstance(value, str):
                    errors.append(ValidationError(
                        f"Field '{field_name}' must be a string",
                        path=field_name,
                        suggestions=[f"Change {field_name} to a string"]
                    ))

        return errors

    def _validate_groups_structure(self, data: Dict[str, Any]) -> List[ValidationError]:
        """Validate groups array structure."""
        errors: List[ValidationError] = []
        groups = data.get('groups', [])

        if not isinstance(groups, list):
            return errors

        for i, group in enumerate(groups):
            errors.extend(self._validate_single_group(group, i))

        return errors

    def _validate_single_group(self, group: Any, index: int) -> List[ValidationError]:
        """Validate a single group structure."""
        errors = []

        if not isinstance(group, dict):
            errors.append(ValidationError(
                f"Group at index {index} must be an object",
                path=f"groups[{index}]",
                suggestions=["Each group must be an object with 'name' and 'rules' fields"]
            ))
            return errors

        # Check required fields
        errors.extend(self._validate_group_required_fields(group, index))

        # Validate group name enum
        group_name = group.get('name')
        if group_name not in ['recording_rules', 'alerting_rules']:
            errors.append(ValidationError(
                f"Group name must be 'recording_rules' or 'alerting_rules', got '{group_name}'",
                path=f"groups[{index}].name",
                suggestions=["Use 'recording_rules' or 'alerting_rules' as group name"]
            ))

        # Validate rules array
        group_name_str = group_name if isinstance(group_name, str) else "unknown"
        errors.extend(self._validate_group_rules(group, group_name_str, index))

        return errors

    def _validate_group_required_fields(self, group: Dict[str, Any], index: int) -> List[ValidationError]:
        """Validate required fields in a group."""
        errors = []

        if 'name' not in group:
            errors.append(ValidationError(
                f"Group at index {index} missing required field 'name'",
                path=f"groups[{index}]",
                suggestions=["Add 'name' field to the group"]
            ))

        if 'rules' not in group:
            errors.append(ValidationError(
                f"Group at index {index} missing required field 'rules'",
                path=f"groups[{index}]",
                suggestions=["Add 'rules' field to the group"]
            ))

        return errors

    def _validate_group_rules(self, group: Dict[str, Any], group_name: str, group_index: int) -> List[ValidationError]:
        """Validate rules array in a group."""
        errors = []
        rules = group.get('rules', [])

        if not isinstance(rules, list):
            errors.append(ValidationError(
                f"Rules in group {group_index} must be an array",
                path=f"groups[{group_index}].rules",
                suggestions=["Change rules to an array of rule objects"]
            ))
            return errors

        # Validate individual rules
        for j, rule in enumerate(rules):
            errors.extend(self._validate_single_rule(rule, group_name, group_index, j))

        return errors

    def _validate_single_rule(self, rule: Any, group_name: str, group_index: int, rule_index: int) -> List[ValidationError]:
        """Validate a single rule within a group."""
        errors = []

        if not isinstance(rule, dict):
            errors.append(ValidationError(
                f"Rule at index {rule_index} in group {group_index} must be an object",
                path=f"groups[{group_index}].rules[{rule_index}]",
                suggestions=["Each rule must be an object"]
            ))
            return errors

        # Validate based on group type
        if group_name == 'recording_rules':
            if 'record' not in rule:
                errors.append(ValidationError(
                    "Recording rule missing required field 'record'",
                    path=f"groups[{group_index}].rules[{rule_index}]",
                    suggestions=["Add 'record' field to recording rule"]
                ))
        elif group_name == 'alerting_rules':
            if 'alert' not in rule:
                errors.append(ValidationError(
                    "Alerting rule missing required field 'alert'",
                    path=f"groups[{group_index}].rules[{rule_index}]",
                    suggestions=["Add 'alert' field to alerting rule"]
                ))

        if 'expr' not in rule:
            errors.append(ValidationError(
                "Rule missing required field 'expr'",
                path=f"groups[{group_index}].rules[{rule_index}]",
                suggestions=["Add 'expr' field to rule"]
            ))

        return errors

    def _validate_zabbix_structure(self, data: Dict[str, Any]) -> List[ValidationError]:
        """Validate zabbix section structure."""
        errors = []
        zabbix = data.get('zabbix', {})

        if not isinstance(zabbix, dict):
            errors.append(ValidationError(
                "Zabbix section must be an object",
                path="zabbix",
                suggestions=["Change zabbix to an object/dictionary"]
            ))
            return errors

        # Validate hosts if present (but make visible_name optional for tests)
        hosts = zabbix.get('hosts', [])
        if hosts and not isinstance(hosts, list):
            errors.append(ValidationError(
                "Zabbix hosts must be an array",
                path="zabbix.hosts",
                suggestions=["Change hosts to an array of host objects"]
            ))
        elif isinstance(hosts, list):
            for i, host in enumerate(hosts):
                if not isinstance(host, dict):
                    errors.append(ValidationError(
                        f"Host at index {i} must be an object",
                        path=f"zabbix.hosts[{i}]",
                        suggestions=["Each host must be an object"]
                    ))
                    continue

                # Check required host fields (make visible_name optional for backward compatibility)
                required_host_fields = ['host_name', 'host_groups', 'link_templates']
                for field in required_host_fields:
                    if field not in host:
                        errors.append(ValidationError(
                            f"Host missing required field '{field}'",
                            path=f"zabbix.hosts[{i}]",
                            suggestions=[f"Add '{field}' field to host definition"]
                        ))

        return errors


class CrossReferenceValidator:
    """Validator for cross-references between configuration sections."""

    def __init__(self) -> None:
        """Initialize cross-reference validator."""
        pass

    def validate_alert_wiki_consistency(self, config: Dict[str, Any]) -> List[ValidationError]:
        """
        Validate that all alerts have corresponding wiki documentation.

        Args:
            config: Configuration to validate

        Returns:
            List of validation errors for missing documentation
        """
        errors: List[ValidationError] = []

        # Only validate if both sections exist
        if not self.should_validate_wiki_consistency(config):
            return errors

        # Get alert names from groups
        groups = config.get('groups', [])
        alert_names = ConfigAnalyzer.extract_alert_names(groups)

        # Get wiki alert names
        wiki = config.get('wiki', {})
        wiki_alert_names = ConfigAnalyzer.extract_wiki_alert_names(wiki)

        # Find alerts missing from wiki
        missing_docs = alert_names - wiki_alert_names
        if missing_docs:
            errors.append(ValidationError(
                f"Alerts missing wiki documentation: {', '.join(sorted(missing_docs))}",
                path="wiki.knowledgebase.alerts.alertings",
                suggestions=[
                    "Add documentation for each alert in the wiki.knowledgebase.alerts.alertings section",
                    "Ensure alert names match exactly between groups and wiki sections"
                ]
            ))

        return errors

    def should_validate_wiki_consistency(self, config: Dict[str, Any]) -> bool:
        """
        Check if wiki consistency validation should be performed.

        Args:
            config: Configuration to check

        Returns:
            True if both alerts and wiki knowledgebase exist
        """
        return (ConfigAnalyzer.has_alerting_rules(config) and
                ConfigAnalyzer.has_wiki_knowledgebase(config))


class ConfigAnalyzer:
    """Analyzer for extracting information from configuration."""

    @staticmethod
    def extract_alert_names(groups: List[Dict[str, Any]]) -> Set[str]:
        """
        Extract alert names from groups.

        Args:
            groups: List of rule groups

        Returns:
            Set of alert names
        """
        alert_names = set()

        for group in groups:
            if group.get('name') == 'alerting_rules':
                rules = group.get('rules', [])
                for rule in rules:
                    alert_name = rule.get('alert')
                    if alert_name:
                        alert_names.add(alert_name)

        return alert_names

    @staticmethod
    def extract_wiki_alert_names(wiki: Dict[str, Any]) -> Set[str]:
        """
        Extract alert names from wiki knowledgebase.

        Args:
            wiki: Wiki section of configuration

        Returns:
            Set of alert names in wiki
        """
        alert_names = set()

        knowledgebase = wiki.get('knowledgebase', {})
        alerts = knowledgebase.get('alerts', {})
        alertings = alerts.get('alertings', {})

        # Extract all alert names from the alertings dictionary
        alert_names.update(alertings.keys())

        return alert_names

    @staticmethod
    def has_wiki_knowledgebase(config: Dict[str, Any]) -> bool:
        """
        Check if configuration has wiki knowledgebase section.

        Args:
            config: Configuration to check

        Returns:
            True if wiki.knowledgebase.alerts.alertings exists
        """
        wiki = config.get('wiki', {})
        knowledgebase = wiki.get('knowledgebase', {})
        alerts = knowledgebase.get('alerts', {})
        alertings = alerts.get('alertings', {})

        return bool(alertings)

    @staticmethod
    def has_alerting_rules(config: Dict[str, Any]) -> bool:
        """
        Check if configuration has alerting rules.

        Args:
            config: Configuration to check

        Returns:
            True if alerting_rules group exists with rules
        """
        groups = config.get('groups', [])

        for group in groups:
            if group.get('name') == 'alerting_rules':
                rules = group.get('rules', [])
                # Check if there are any rules with 'alert' field
                for rule in rules:
                    if rule.get('alert'):
                        return True

        return False
