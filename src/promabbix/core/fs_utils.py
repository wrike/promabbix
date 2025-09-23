#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

from pathlib import Path
from rich.console import Console
from typing import Any
import json
import sys
import yaml

try:
    from yaml import CLoader as YamlLoader
except ImportError:
    from yaml import Loader as YamlLoader  # type: ignore[assignment]

# Create an alias for the loader to be used in yaml.load() calls
Loader = YamlLoader


class DataLoader:
    """
    Class DataLoader to serialize JSON/YAML file.
    """

    def __init__(self) -> None:
        self.console = Console(stderr=True)

    def _parse_data(self, data: str) -> Any:
        """
        Parse data as YAML or JSON.

        :param data: Raw data string to parse
        :return: Parsed data object
        """
        try:
            result = yaml.load(data, Loader=Loader)
            if result is not None:
                return result
            else:
                last_yaml_error = "Parser returned None"
        except yaml.YAMLError as e:
            last_yaml_error = str(e)
        except Exception as e:
            last_yaml_error = str(e)

        try:
            return json.loads(data)
        except Exception as e:
            last_json_error = str(e)

        self.console.print(f"ERROR: Failed to parse as YAML ({last_yaml_error}) or JSON ({last_json_error})", style="bold red")
        raise ValueError(f"Failed to parse as YAML ({last_yaml_error}) or JSON ({last_json_error})")

    def load_from_file(self, filename: str) -> Any:
        """
        Loads data from a file, which can be YAML or JSON.

        :param filename: Path to file.
        :return: Deserialized object.
        """
        file_path = Path(filename).expanduser().resolve()
        try:
            data = file_path.read_text(encoding='utf-8')
        except Exception as e:
            self.console.print(f"Error reading file: {e}", style="bold red")
            raise

        return self._parse_data(data)

    def load_from_stdin(self) -> Any:
        """
        Loads data from STDIN, which can be YAML or JSON.

        :return: Deserialized object.
        """
        try:
            data = sys.stdin.read()
        except Exception as e:
            self.console.print(f"Error reading from STDIN: {e}", style="bold red")
            raise

        if not data.strip():
            self.console.print("Warning: No data received from STDIN", style="bold yellow")
            return {}

        return self._parse_data(data)


class DataSaver:
    """
    Class to serialize to JSON or YAML file.

    :param filename: Path to file.
    """
    def __init__(self) -> None:
        self.console = Console(stderr=True)

    def save_to_file(self, data: Any, filename: str) -> None:
        """
        Save data to file with format determined by filename suffix.
        Supports .json, .yaml, .yml extensions.
        """
        file_path = Path(filename).expanduser().resolve()
        ext = file_path.suffix.lower()

        try:
            data_to_write = self._format_data_for_extension(data, ext)
            file_path.write_text(data_to_write, encoding='utf-8')
            self.console.print(f"Data saved to {file_path}.", style="green")
        except Exception as e:
            self.console.print(f"[bold red]Error saving file:[/bold red] {e}")

    def _format_data_for_extension(self, data: Any, ext: str) -> str:
        """Format data according to file extension."""
        if ext == '.json':
            return self._format_as_json(data)
        elif ext in {'.yaml', '.yml'}:
            return self._format_as_yaml(data)
        else:
            return self._format_as_default(data)

    def _format_as_json(self, data: Any) -> str:
        """Format data as JSON."""
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                return json.dumps(parsed, indent=2, ensure_ascii=False)
            except Exception:
                self._print_format_warning()
                return data
        else:
            return json.dumps(data, indent=2, ensure_ascii=False)

    def _format_as_yaml(self, data: Any) -> str:
        """Format data as YAML."""
        if isinstance(data, str):
            try:
                parsed_data = yaml.load(data, Loader=Loader)
                if parsed_data is None:
                    return data
                else:
                    return yaml.dump(parsed_data, allow_unicode=True, sort_keys=False)
            except Exception:
                self._print_format_warning()
                return data
        else:
            return yaml.dump(data, allow_unicode=True, sort_keys=False)

    def _format_as_default(self, data: Any) -> str:
        """Format data for unknown extensions."""
        if isinstance(data, str):
            return data
        elif isinstance(data, (dict, list)):
            return json.dumps(data, indent=2, ensure_ascii=False)
        else:
            return str(data)

    def _print_format_warning(self) -> None:
        """Print warning for invalid data format."""
        self.console.print("Warning: String is not valid data format, saving as plain text.",
                           style="bold yellow")

    def save_text_to_file(self, data: str, filename: str) -> None:
        file_path = Path(filename).expanduser().resolve()
        try:
            file_path.write_text(data, encoding='utf-8')
            self.console.print(f"Text data saved to {file_path}.", style="green")
        except Exception as e:
            self.console.print(f"[bold red]Error saving text file:[/bold red] {e}")

    def save(self, data: Any, filename: str) -> None:
        ext = Path(filename).suffix.lower()
        if ext in {'.json'}:
            self.save_to_file(data, filename)
        elif ext in {'.yaml', '.yml'}:
            self.save_to_file(data, filename)
        elif isinstance(data, (dict, list)):
            # Default to JSON if data is dict/list
            self.save_to_file(data, filename)
        elif isinstance(data, str):
            self.save_text_to_file(data, filename)
        else:
            self.console.print("Unknown data type, attempting to save as string.", style="bold yellow")
            self.save_text_to_file(str(data), filename)

    def save_to_stdout(self, data: Any) -> None:
        """
        Saves data to STDOUT.

        :param data: Data to be saved (string, dict, list, etc.)
        """
        try:
            if isinstance(data, str):
                # For strings, try to determine if it's JSON/YAML and format it nicely
                try:
                    # Try parsing as JSON first for pretty printing
                    parsed = json.loads(data)
                    output = json.dumps(parsed, indent=2, ensure_ascii=False)
                except Exception:
                    # Not JSON, output as-is
                    output = data
            elif isinstance(data, (dict, list)):
                # For dicts/lists, default to JSON format
                output = json.dumps(data, indent=2, ensure_ascii=False)
            else:
                # For other types, convert to string
                output = str(data)

            # Write to stdout
            sys.stdout.write(output)
            if not output.endswith('\n'):
                sys.stdout.write('\n')
            sys.stdout.flush()

        except Exception as e:
            self.console.print(f"[bold red]Error writing to STDOUT:[/bold red] {e}")
            raise
