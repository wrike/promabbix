#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2025 Wrike Inc.
#

import click
import os
import sys
from typing import Any, Dict, Optional, cast

from ..core.fs_utils import DataLoader, DataSaver
from ..core.template import Render
from ..core.validation import ConfigValidator, ValidationError
from rich.console import Console


@click.command(name='generateTemplate')
@click.argument('config_file', type=click.Path(exists=True))
@click.option('-o', '--output', 
              default='/tmp/zbx_template.json',
              help='Path to save generated Zabbix template (use "-" for STDOUT)')
@click.option('-t', '--templates',
              default=None,
              help='Path to directory with jinja2 templates')
@click.option('-tn', '--template-name',
              default='prometheus_alert_rules_to_zbx_template.j2',
              help='Template file name')
@click.option('--validate-only',
              is_flag=True,
              help='Only validate the configuration without generating templates')
def generate_template(config_file: str, output: str, templates: Optional[str], 
                     template_name: str, validate_only: bool) -> None:
    """Generate Zabbix template from alert configuration file."""
    
    command = GenerateTemplateCommand()
    exit_code = command.execute(config_file, output, templates, template_name, validate_only)
    if exit_code != 0:
        sys.exit(exit_code)


class GenerateTemplateCommand:
    """Command handler for generateTemplate functionality."""
    
    def __init__(self, loader: Optional[DataLoader] = None, 
                 saver: Optional[DataSaver] = None,
                 validator: Optional[ConfigValidator] = None) -> None:
        """Initialize command with dependencies."""
        self.loader = loader or DataLoader()
        self.saver = saver or DataSaver()
        self.validator = validator or ConfigValidator()
        self.console = Console(stderr=True)
    
    def execute(self, config_file: str, output: str, templates: Optional[str],
                template_name: str, validate_only: bool) -> int:
        """
        Execute the generateTemplate command.
        
        Args:
            config_file: Path to configuration file
            output: Output path for generated template
            templates: Path to template directory
            template_name: Template file name
            validate_only: If True, only validate without generating
            
        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            # Load configuration
            config_data = self.load_configuration(config_file)
            
            # Validate configuration
            self.validate_configuration(config_data)
            
            if validate_only:
                # Validation-only mode
                self.print_validation_success()
                return 0
            else:
                # Normal mode (validation + template generation)
                template_content = self.generate_template_content(
                    config_data, templates, template_name
                )
                self.save_template(template_content, output)
                return 0
                
        except ValidationError as e:
            self.print_validation_error(e)
            return 1
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return 1
    
    def load_configuration(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from file or STDIN."""
        if config_file == "-":
            return cast(Dict[str, Any], self.loader.load_from_stdin())
        else:
            return cast(Dict[str, Any], self.loader.load_from_file(config_file))
    
    def validate_configuration(self, config_data: Dict[str, Any]) -> None:
        """Validate configuration data."""
        self.validator.validate_config(config_data)
    
    def generate_template_content(self, config_data: Dict[str, Any], 
                                templates: Optional[str], template_name: str) -> str:
        """Generate template content from configuration."""
        # Handle default template path
        if templates is None:
            templates = f'{os.path.abspath(os.path.dirname(__file__))}/../templates/'
        
        renderer = Render()
        return renderer.render_file(
            template_path=templates,
            template_name=template_name,
            data=config_data
        )
    
    def save_template(self, template_data: str, output_path: str) -> None:
        """Save generated template to file or STDOUT."""
        if output_path == "-":
            self.saver.save_to_stdout(template_data)
        else:
            self.saver.save_to_file(template_data, output_path)
    
    def print_validation_success(self) -> None:
        """Print validation success message."""
        self.console.print("[green]✓ Configuration validation passed[/green]")
    
    def print_validation_error(self, error: ValidationError) -> None:
        """Print validation error message."""
        self.console.print("[red]✗ Configuration validation failed:[/red]")
        self.console.print(f"[red]{error}[/red]")