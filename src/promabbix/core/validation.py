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
        raise NotImplementedError


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
        raise NotImplementedError
    
    def load_schema(self) -> Dict[str, Any]:
        """Load JSON schema from file."""
        raise NotImplementedError
    
    def validate_config(self, config_data: Dict[str, Any]) -> None:
        """
        Validate unified configuration against schema and cross-references.
        
        Args:
            config_data: Parsed configuration dictionary
            
        Raises:
            ValidationError: If validation fails
        """
        raise NotImplementedError
    
    def validate_json_schema(self, config_data: Dict[str, Any]) -> None:
        """
        Validate configuration against JSON schema.
        
        Args:
            config_data: Configuration to validate
            
        Raises:
            ValidationError: If schema validation fails
        """
        raise NotImplementedError
    
    def validate_cross_references(self, config_data: Dict[str, Any]) -> None:
        """
        Validate cross-references between different sections of config.
        
        Args:
            config_data: Configuration to validate
            
        Raises:
            ValidationError: If cross-reference validation fails
        """
        raise NotImplementedError
    
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
        raise NotImplementedError
    
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
        raise NotImplementedError
    
    def convert_jsonschema_error(self, error: Any) -> ValidationError:
        """
        Convert jsonschema ValidationError to our ValidationError format.
        
        Args:
            error: jsonschema ValidationError
            
        Returns:
            Our ValidationError with path and suggestions
        """
        raise NotImplementedError
    
    def generate_suggestions(self, error: Any) -> List[str]:
        """
        Generate helpful suggestions based on validation error.
        
        Args:
            error: jsonschema ValidationError
            
        Returns:
            List of suggestions for fixing the error
        """
        raise NotImplementedError


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
        raise NotImplementedError
    
    def validate_template_references(self, config: Dict[str, Any]) -> List[ValidationError]:
        """
        Validate template name consistency between zabbix template and host links.
        
        Args:
            config: Configuration to validate
            
        Returns:
            List of validation errors for template reference issues
        """
        raise NotImplementedError
    
    def validate_macro_consistency(self, config: Dict[str, Any]) -> List[ValidationError]:
        """
        Validate that referenced macros are defined.
        
        Args:
            config: Configuration to validate
            
        Returns:
            List of validation errors for undefined macros
        """
        raise NotImplementedError
    
    def should_validate_wiki_consistency(self, config: Dict[str, Any]) -> bool:
        """
        Check if wiki consistency validation should be performed.
        
        Args:
            config: Configuration to check
            
        Returns:
            True if both alerts and wiki knowledgebase exist
        """
        raise NotImplementedError


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
        raise NotImplementedError
    
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
        raise NotImplementedError
    
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
        raise NotImplementedError
    
    @staticmethod
    def has_alerting_rules(config: Dict[str, Any]) -> bool:
        """
        Check if configuration has alerting rules.
        
        Args:
            config: Configuration to check
            
        Returns:
            True if alerting_rules group exists with rules
        """
        raise NotImplementedError