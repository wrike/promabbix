#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from rich.console import Console


class MigrationError(Exception):
    """Exception raised during migration operations."""
    
    def __init__(self, message: str, source_path: Optional[str] = None):
        """
        Initialize migration error.
        
        Args:
            message: Error message
            source_path: Path to source file/directory causing the error
        """
        self.message = message
        self.source_path = source_path
        super().__init__(self.format_message())
    
    def format_message(self) -> str:
        """Format the error message with source path."""
        raise NotImplementedError


class LegacyServiceMigrator:
    """Migrator for converting legacy three-file format to unified format."""
    
    def __init__(self):
        """Initialize legacy service migrator."""
        self.console = Console(stderr=True)
    
    def migrate_service(self, service_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Migrate a service from legacy three-file format to unified format.
        
        Args:
            service_path: Path to service directory containing three files
            
        Returns:
            Unified configuration dictionary
            
        Raises:
            MigrationError: If migration fails
        """
        raise NotImplementedError
    
    def load_legacy_files(self, service_path: Path) -> Dict[str, Dict[str, Any]]:
        """
        Load the three legacy files from service directory.
        
        Args:
            service_path: Path to service directory
            
        Returns:
            Dictionary with 'alerts', 'zabbix', 'wiki' keys
            
        Raises:
            MigrationError: If files cannot be loaded
        """
        raise NotImplementedError
    
    def find_alerts_file(self, service_path: Path) -> Path:
        """
        Find the alerts YAML file in service directory.
        
        Args:
            service_path: Path to service directory
            
        Returns:
            Path to alerts file
            
        Raises:
            MigrationError: If alerts file not found
        """
        raise NotImplementedError
    
    def find_zabbix_vars_file(self, service_path: Path) -> Path:
        """
        Find the zabbix_vars.yaml file in service directory.
        
        Args:
            service_path: Path to service directory
            
        Returns:
            Path to zabbix_vars.yaml file
            
        Raises:
            MigrationError: If zabbix_vars.yaml not found
        """
        raise NotImplementedError
    
    def find_wiki_vars_file(self, service_path: Path) -> Path:
        """
        Find the wiki_vars.yaml file in service directory.
        
        Args:
            service_path: Path to service directory
            
        Returns:
            Path to wiki_vars.yaml file
            
        Raises:
            MigrationError: If wiki_vars.yaml not found
        """
        raise NotImplementedError
    
    def merge_configurations(self, legacy_files: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge legacy file contents into unified format.
        
        Args:
            legacy_files: Dictionary with loaded legacy file contents
            
        Returns:
            Unified configuration dictionary
        """
        raise NotImplementedError
    
    def add_default_sections(self, unified_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add default prometheus and promabbix sections to unified config.
        
        Args:
            unified_config: Unified configuration
            
        Returns:
            Unified configuration with default sections added
        """
        raise NotImplementedError
    
    def generate_default_prometheus_config(self) -> Dict[str, Any]:
        """
        Generate default prometheus configuration section.
        
        Returns:
            Default prometheus configuration
        """
        raise NotImplementedError
    
    def generate_default_promabbix_config(self) -> Dict[str, Any]:
        """
        Generate default promabbix configuration section.
        
        Returns:
            Default promabbix configuration
        """
        raise NotImplementedError
    
    def validate_legacy_structure(self, service_path: Path) -> bool:
        """
        Validate that service directory has legacy three-file structure.
        
        Args:
            service_path: Path to service directory
            
        Returns:
            True if valid legacy structure
        """
        raise NotImplementedError


class FormatDetector:
    """Detector for configuration format types."""
    
    @staticmethod
    def detect_config_format(path: Union[str, Path]) -> str:
        """
        Detect configuration format type.
        
        Args:
            path: Path to configuration file or directory
            
        Returns:
            Format type: 'unified', 'legacy_three_file', or 'unknown'
        """
        raise NotImplementedError
    
    @staticmethod
    def is_unified_format(path: Path) -> bool:
        """
        Check if path points to unified format configuration.
        
        Args:
            path: Path to check
            
        Returns:
            True if unified format
        """
        raise NotImplementedError
    
    @staticmethod
    def is_legacy_three_file_format(path: Path) -> bool:
        """
        Check if path points to legacy three-file format.
        
        Args:
            path: Path to check
            
        Returns:
            True if legacy three-file format
        """
        raise NotImplementedError
    
    @staticmethod
    def has_unified_structure(config: Dict[str, Any]) -> bool:
        """
        Check if configuration dictionary has unified structure.
        
        Args:
            config: Configuration to check
            
        Returns:
            True if has unified structure
        """
        raise NotImplementedError


class BatchMigrator:
    """Batch migrator for converting multiple services."""
    
    def __init__(self, migrator: Optional[LegacyServiceMigrator] = None):
        """
        Initialize batch migrator.
        
        Args:
            migrator: Service migrator instance
        """
        self.migrator = migrator or LegacyServiceMigrator()
        self.console = Console(stderr=True)
    
    def migrate_repository(self, repo_path: Union[str, Path], output_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Migrate entire repository from legacy to unified format.
        
        Args:
            repo_path: Path to repository root
            output_path: Path to output migrated files
            
        Returns:
            Migration summary report
            
        Raises:
            MigrationError: If repository migration fails
        """
        raise NotImplementedError
    
    def find_legacy_services(self, repo_path: Path) -> List[Path]:
        """
        Find all legacy service directories in repository.
        
        Args:
            repo_path: Path to repository root
            
        Returns:
            List of paths to legacy service directories
        """
        raise NotImplementedError
    
    def migrate_service_batch(self, service_paths: List[Path], output_path: Path) -> Dict[str, Any]:
        """
        Migrate multiple services in batch.
        
        Args:
            service_paths: List of service directory paths
            output_path: Output directory path
            
        Returns:
            Batch migration report
        """
        raise NotImplementedError
    
    def generate_migration_report(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate migration summary report.
        
        Args:
            results: List of individual migration results
            
        Returns:
            Summary report
        """
        raise NotImplementedError
    
    def validate_migration_results(self, results: List[Dict[str, Any]]) -> bool:
        """
        Validate that all migrations completed successfully.
        
        Args:
            results: List of migration results
            
        Returns:
            True if all migrations successful
        """
        raise NotImplementedError


class ConfigConverter:
    """Converter for transforming configuration structures."""
    
    @staticmethod
    def convert_legacy_alerts_to_unified(alerts_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert legacy alerts configuration to unified groups format.
        
        Args:
            alerts_config: Legacy alerts configuration
            
        Returns:
            Unified groups configuration
        """
        raise NotImplementedError
    
    @staticmethod
    def convert_legacy_zabbix_to_unified(zabbix_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert legacy zabbix_vars configuration to unified zabbix format.
        
        Args:
            zabbix_config: Legacy zabbix configuration
            
        Returns:
            Unified zabbix configuration
        """
        raise NotImplementedError
    
    @staticmethod
    def convert_legacy_wiki_to_unified(wiki_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert legacy wiki_vars configuration to unified wiki format.
        
        Args:
            wiki_config: Legacy wiki configuration
            
        Returns:
            Unified wiki configuration
        """
        raise NotImplementedError
    
    @staticmethod
    def normalize_template_name(template_name: str) -> str:
        """
        Normalize template name to unified format conventions.
        
        Args:
            template_name: Original template name
            
        Returns:
            Normalized template name
        """
        raise NotImplementedError
    
    @staticmethod
    def normalize_host_name(host_name: str) -> str:
        """
        Normalize host name to unified format conventions.
        
        Args:
            host_name: Original host name
            
        Returns:
            Normalized host name
        """
        raise NotImplementedError