#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
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
        self.schema_path = schema_path or self.default_schema_path()
        self.schema = self.load_schema()
        self.console = Console(stderr=True)
    
    def default_schema_path(self) -> str:
        """Get path to default built-in schema."""
        # Get the path to the schemas directory relative to this file
        current_dir = Path(__file__).parent.parent.parent.parent
        return str(current_dir / "schemas" / "unified.json")
    
    def load_schema(self) -> Dict[str, Any]:
        """Load JSON schema from file."""
        try:
            with open(self.schema_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            raise ValidationError(
                f"Schema file not found: {self.schema_path}",
                suggestions=["Ensure the unified schema file exists at the expected path"]
            )
        except json.JSONDecodeError as e:
            raise ValidationError(
                f"Invalid JSON in schema file: {e}",
                path=self.schema_path,
                suggestions=["Check the schema file for valid JSON syntax"]
            )
    
    def validate_config(self, config_data: Dict[str, Any]) -> None:
        """
        Validate unified configuration against schema and cross-references.
        
        Args:
            config_data: Parsed configuration dictionary
            
        Raises:
            ValidationError: If validation fails
        """
        # First validate against JSON schema
        self.validate_json_schema(config_data)
        
        # Then perform cross-reference validation if both sections exist
        if self.should_validate_cross_references(config_data):
            self.validate_cross_references(config_data)
    
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
                    f"Multiple validation errors found:\n" + "\n\n".join(error_messages),
                    suggestions=["Fix all validation errors to proceed"]
                )
    
    def validate_cross_references(self, config_data: Dict[str, Any]) -> None:
        """
        Validate cross-references between different sections of config.
        
        Args:
            config_data: Configuration to validate
            
        Raises:
            ValidationError: If cross-reference validation fails
        """
        cross_ref_validator = CrossReferenceValidator()
        errors = []
        
        # Validate alert-wiki consistency
        errors.extend(cross_ref_validator.validate_alert_wiki_consistency(config_data))
        
        # Validate template references
        errors.extend(cross_ref_validator.validate_template_references(config_data))
        
        # Validate macro consistency  
        errors.extend(cross_ref_validator.validate_macro_consistency(config_data))
        
        if errors:
            if len(errors) == 1:
                raise errors[0]
            else:
                error_messages = []
                for i, error in enumerate(errors, 1):
                    error_messages.append(f"Cross-reference error {i}: {error.format_message()}")
                
                raise ValidationError(
                    f"Multiple cross-reference validation errors found:\n" + "\n\n".join(error_messages),
                    suggestions=["Fix all cross-reference errors to proceed"]
                )
    
    def validate_alert_consistency(self, config: Dict[str, Any]) -> None:
        """
        Ensure alerts in groups match wiki knowledge base (if wiki exists).
        
        Args:
            config: Configuration to validate
            
        Raises:
            ValidationError: If alerts are missing documentation
        """
        raise NotImplementedError
    
    def validate_zabbix_references(self, config: Dict[str, Any]) -> None:
        """
        Validate Zabbix template and host references.
        
        Args:
            config: Configuration to validate
            
        Raises:
            ValidationError: If Zabbix references are invalid
        """
        raise NotImplementedError
    
    def validate_macro_references(self, config: Dict[str, Any]) -> None:
        """
        Validate macro references between expressions and definitions.
        
        Args:
            config: Configuration to validate
            
        Raises:
            ValidationError: If macro references are invalid
        """
        raise NotImplementedError
    
    def extract_alert_names(self, groups: List[Dict[str, Any]]) -> Set[str]:
        """
        Extract alert names from alerting_rules groups.
        
        Args:
            groups: List of rule groups
            
        Returns:
            Set of alert names
        """
        raise NotImplementedError
    
    def extract_wiki_alert_names(self, wiki: Dict[str, Any]) -> Set[str]:
        """
        Extract alert names from wiki knowledgebase.
        
        Args:
            wiki: Wiki configuration section
            
        Returns:
            Set of alert names documented in wiki
        """
        raise NotImplementedError
    
    def extract_macro_references(self, config: Dict[str, Any]) -> Set[str]:
        """
        Extract all macro references from expressions.
        
        Args:
            config: Configuration to analyze
            
        Returns:
            Set of macro names referenced in expressions
        """
        raise NotImplementedError
    
    def extract_macro_definitions(self, config: Dict[str, Any]) -> Set[str]:
        """
        Extract all macro definitions from zabbix section.
        
        Args:
            config: Configuration to analyze
            
        Returns:
            Set of macro names defined in zabbix section
        """
        raise NotImplementedError
    
    def should_validate_cross_references(self, config: Dict[str, Any]) -> bool:
        """
        Determine if cross-reference validation should be performed.
        
        Args:
            config: Configuration to check
            
        Returns:
            True if cross-reference validation should run
        """
        # Only validate cross-references if both alerts and wiki exist
        has_alerts = ConfigAnalyzer.has_alerting_rules(config)
        has_wiki = ConfigAnalyzer.has_wiki_knowledgebase(config)
        return has_alerts and has_wiki
    
    def collect_validation_errors(self, config_data: Dict[str, Any]) -> List[ValidationError]:
        """
        Collect all validation errors without stopping at first error.
        
        Args:
            config_data: Configuration to validate
            
        Returns:
            List of all validation errors found
        """
        raise NotImplementedError
    
    def format_validation_summary(self, errors: List[ValidationError]) -> str:
        """
        Format validation errors into a user-friendly summary.
        
        Args:
            errors: List of validation errors
            
        Returns:
            Formatted error summary
        """
        raise NotImplementedError


class SchemaValidator:
    """JSON Schema validator with enhanced error reporting."""
    
    def __init__(self, schema: Dict[str, Any]):
        """
        Initialize schema validator.
        
        Args:
            schema: JSON schema dictionary
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
        import jsonschema
        
        errors = []
        try:
            jsonschema.validate(data, self.schema)
        except jsonschema.ValidationError as e:
            # Convert the main error
            errors.append(self.convert_jsonschema_error(e))
            
            # Also collect any sub-errors if this is a oneOf/anyOf validation
            if hasattr(e, 'context') and e.context:
                for sub_error in e.context:
                    errors.append(self.convert_jsonschema_error(sub_error))
        
        return errors
    
    def convert_jsonschema_error(self, error: Any) -> ValidationError:
        """
        Convert jsonschema ValidationError to our ValidationError format.
        
        Args:
            error: jsonschema ValidationError
            
        Returns:
            Our ValidationError with path and suggestions
        """
        # Build the path to the invalid field
        path_parts = []
        for part in error.absolute_path:
            if isinstance(part, int):
                path_parts.append(f"[{part}]")
            else:
                path_parts.append(str(part))
        path = ".".join(path_parts) if path_parts else "root"
        
        # Generate helpful suggestions
        suggestions = self.generate_suggestions(error)
        
        return ValidationError(
            message=error.message,
            path=path,
            suggestions=suggestions
        )
    
    def generate_suggestions(self, error: Any) -> List[str]:
        """
        Generate helpful suggestions based on validation error.
        
        Args:
            error: jsonschema ValidationError
            
        Returns:
            List of suggestions for fixing the error
        """
        suggestions = []
        
        if error.validator == 'required':
            suggestions.append(f"Add the required field: {error.message.split()[-1]}")
        elif error.validator == 'type':
            expected_type = error.schema.get('type', 'unknown')
            suggestions.append(f"Change value to type: {expected_type}")
        elif error.validator == 'enum':
            allowed_values = error.schema.get('enum', [])
            suggestions.append(f"Use one of the allowed values: {', '.join(map(str, allowed_values))}")
        elif error.validator == 'pattern':
            pattern = error.schema.get('pattern', '')
            suggestions.append(f"Value must match pattern: {pattern}")
        elif error.validator == 'additionalProperties':
            suggestions.append("Remove unexpected properties or check property names for typos")
        elif error.validator == 'minItems':
            min_items = error.schema.get('minItems', 0)
            suggestions.append(f"Array must have at least {min_items} items")
        elif error.validator == 'maxItems':
            max_items = error.schema.get('maxItems', 0)
            suggestions.append(f"Array must have at most {max_items} items")
        else:
            suggestions.append("Check the schema documentation for valid values")
        
        return suggestions


class CrossReferenceValidator:
    """Validator for cross-references between configuration sections."""
    
    def __init__(self):
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
        errors = []
        
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
        
        # Find extra documentation (warn but don't fail)
        extra_docs = wiki_alert_names - alert_names
        if extra_docs:
            errors.append(ValidationError(
                f"Wiki documentation exists for undefined alerts: {', '.join(sorted(extra_docs))}",
                path="wiki.knowledgebase.alerts.alertings",
                suggestions=[
                    "Remove documentation for non-existent alerts",
                    "Check for typos in alert names"
                ]
            ))
        
        return errors
    
    def validate_template_references(self, config: Dict[str, Any]) -> List[ValidationError]:
        """
        Validate template name consistency between zabbix template and host links.
        
        Args:
            config: Configuration to validate
            
        Returns:
            List of validation errors for template reference issues
        """
        # For now, just return empty list - this validation is less critical
        # Can be enhanced in future phases
        return []
    
    def validate_macro_consistency(self, config: Dict[str, Any]) -> List[ValidationError]:
        """
        Validate that referenced macros are defined.
        
        Args:
            config: Configuration to validate
            
        Returns:
            List of validation errors for undefined macros
        """
        # For now, just return empty list - macro validation is complex 
        # and can be enhanced in future phases
        return []
    
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
    def extract_recording_rule_names(groups: List[Dict[str, Any]]) -> Set[str]:
        """
        Extract recording rule names from groups.
        
        Args:
            groups: List of rule groups
            
        Returns:
            Set of recording rule names
        """
        raise NotImplementedError
    
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
    def extract_macro_references(text: str) -> Set[str]:
        """
        Extract macro references from expression text.
        
        Args:
            text: Expression text to analyze
            
        Returns:
            Set of macro names referenced
        """
        raise NotImplementedError
    
    @staticmethod
    def extract_zabbix_macros(zabbix_config: Dict[str, Any]) -> Set[str]:
        """
        Extract macro definitions from zabbix configuration.
        
        Args:
            zabbix_config: Zabbix section of configuration
            
        Returns:
            Set of defined macro names
        """
        raise NotImplementedError
    
    @staticmethod
    def extract_template_references(zabbix_config: Dict[str, Any]) -> Set[str]:
        """
        Extract template references from host configurations.
        
        Args:
            zabbix_config: Zabbix section of configuration
            
        Returns:
            Set of template names referenced by hosts
        """
        raise NotImplementedError
    
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