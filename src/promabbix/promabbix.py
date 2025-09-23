#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import argparse
import os
import sys
from typing import Any, Dict, Optional, cast

from .core.fs_utils import DataLoader, DataSaver
from .core.template import Render
from .core.validation import ConfigValidator, ValidationError
from rich_argparse import RichHelpFormatter
from rich.console import Console


class PromabbixApp:
    def __init__(self, loader: Optional[DataLoader] = None, saver: Optional[DataSaver] = None,
                 parser: Optional[argparse.ArgumentParser] = None, validator: Optional[ConfigValidator] = None) -> None:
        self.loader = loader or DataLoader()
        self.saver = saver or DataSaver()
        self.parser = parser if parser else self.app_args()
        self.validator = validator or ConfigValidator()
        self.console = Console(stderr=True)

    def main(self) -> int:
        """
        Main application entry point.

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            # Parse command line arguments
            args = self.parser.parse_args()

            # Load configuration
            config_data = self.load_configuration(args.alertrules)

            if args.validate_only:
                # Validation-only mode
                return self.handle_validation_only_mode(config_data)
            else:
                # Normal mode (validation + template generation)
                return self.handle_normal_mode(config_data, vars(args))

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    def validate_configuration(self, config_data: dict) -> bool:
        """
        Validate configuration data.

        Args:
            config_data: Configuration to validate

        Returns:
            True if validation passes

        Raises:
            ValidationError: If validation fails
        """
        self.validator.validate_config(config_data)
        return True

    def generate_template(self, config_data: dict, template_path: str, template_name: str) -> str:
        """
        Generate Zabbix template from configuration data.

        Args:
            config_data: Validated configuration data
            template_path: Path to template directory
            template_name: Template file name

        Returns:
            Generated template content
        """
        renderer = Render()
        return renderer.render_file(
            template_path=template_path,
            template_name=template_name,
            data=config_data
        )

    def handle_validation_only_mode(self, config_data: dict) -> int:
        """
        Handle validation-only mode execution.

        Args:
            config_data: Configuration to validate

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            self.validator.validate_config(config_data)
            self.print_validation_success()
            return 0
        except ValidationError as e:
            self.print_validation_error(e)
            return 1

    def handle_normal_mode(self, config_data: dict, pargs: dict) -> int:
        """
        Handle normal mode execution (validation + template generation).

        Args:
            config_data: Configuration data
            pargs: Parsed command line arguments

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            # First validate the configuration
            self.validator.validate_config(config_data)

            # Then generate template (existing functionality)
            template_content = self.generate_template(
                config_data,
                pargs['templates'],
                pargs['template_name']
            )

            # Save the generated template
            self.save_template(template_content, pargs['output'])

            return 0
        except ValidationError as e:
            self.print_validation_error(e)
            return 1

    def load_configuration(self, alertrules_path: str) -> Dict[str, Any]:
        """
        Load configuration from file or STDIN.

        Args:
            alertrules_path: Path to configuration file or "-" for STDIN

        Returns:
            Loaded configuration dictionary
        """
        if alertrules_path == "-":
            return cast(Dict[str, Any], self.loader.load_from_stdin())
        else:
            return cast(Dict[str, Any], self.loader.load_from_file(alertrules_path))

    def save_template(self, template_data: str, output_path: str) -> None:
        """
        Save generated template to file or STDOUT.

        Args:
            template_data: Generated template content
            output_path: Output path or "-" for STDOUT
        """
        if output_path == "-":
            self.saver.save_to_stdout(template_data)
        else:
            self.saver.save_to_file(template_data, output_path)

    def print_validation_success(self) -> None:
        """Print validation success message."""
        self.console.print("[green]✓ Configuration validation passed[/green]")

    def print_validation_error(self, error: ValidationError) -> None:
        """
        Print validation error message.

        Args:
            error: Validation error to display
        """
        self.console.print("[red]✗ Configuration validation failed:[/red]")
        self.console.print(f"[red]{error}[/red]")

    def app_args(self) -> argparse.ArgumentParser:
        """Configure command line argument parser."""
        parser = argparse.ArgumentParser(description='Promabbix', formatter_class=RichHelpFormatter)

        parser.add_argument(
            'alertrules',
            action="store",
            default=None,
            type=str,
            help=('Path to unified alert configuration file (use "-" to read from STDIN)')
        )

        parser.add_argument(
            '--validate-only',
            action="store_true",
            help=('Only validate the configuration without generating templates')
        )

        parser.add_argument(
            '-t',
            '--templates',
            action="store",
            default=f'{os.path.abspath(os.path.dirname(__file__))}/templates/',
            type=str,
            help=('Path to dir with jinja2 templates')
        )

        parser.add_argument(
            '-o',
            '--output',
            action="store",
            default='/tmp/zbx_template.json',
            type=str,
            help=('Path to save of generated Zabbix template (use "-" to write to STDOUT)')
        )

        parser.add_argument(
            '-tn',
            '--template-name',
            action="store",
            default='prometheus_alert_rules_to_zbx_template.j2',
            type=str,
            help=('Template name')
        )
        return parser


def main() -> None:
    """Entry point for the promabbix console script."""
    app = PromabbixApp()
    exit_code = app.main()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
