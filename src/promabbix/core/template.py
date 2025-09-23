#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

from pathlib import Path
from typing import Any, Dict, Union
from rich.console import Console
import jinja2
from jinja2 import Environment, FileSystemLoader
from jinja2.exceptions import (TemplateSyntaxError, UndefinedError, TemplateRuntimeError,
                               TemplateAssertionError)

from datetime import datetime
import json
import os
import time
import uuid
import hashlib


def date_time(format: str) -> str:
    epoch_ts = time.time()
    now = datetime.fromtimestamp(epoch_ts)
    try:
        return now.strftime(format)
    except Exception:
        return 'unknown'


def to_uuid4(val: str) -> str:
    hex_string = hashlib.md5(val.encode("UTF-8")).hexdigest()
    uuid4 = uuid.UUID(hex=hex_string, version=4)
    return str(uuid4)


def get_jinja2_globals() -> Dict[str, Any]:
    return {
        'date_time': date_time,
    }


def get_jinja2_filters() -> Dict[str, Any]:
    from .data_utils import isjson
    from ansible.plugins.filter.core import (
        combine, regex_findall, regex_replace, regex_search, to_json, to_uuid,
        dict_to_list_of_dict_key_value_elements, list_of_dict_key_value_elements_to_dict
    )
    return {
        'basename': os.path.basename,
        'combine': combine,
        'dict2items': dict_to_list_of_dict_key_value_elements,
        'dirname': os.path.dirname,
        'isjson': isjson,
        'items2dict': list_of_dict_key_value_elements_to_dict,
        'json_loads': json.loads,
        'regex_findall': regex_findall,
        'regex_replace': regex_replace,
        'regex_search': regex_search,
        'to_json': to_json,
        'to_uuid': to_uuid,
        'to_uuid4': to_uuid4,
    }


def get_jinja2_tests() -> Dict[str, Any]:
    from ansible.plugins.test.core import match
    from ansible.plugins.filter.core import (
        regex_replace, regex_search, regex_findall
    )
    return {
        'match': match,
        'regex_replace': regex_replace,
        'regex_search': regex_search,
        'regex_findall': regex_findall,
    }


class Render:
    def __init__(self, searchpath: Union[str, Path, None] = None) -> None:
        self.console = Console(stderr=True)
        self.searchpath = Path(searchpath).expanduser().resolve() if searchpath else None

        # Jinja2 Environment
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.searchpath)) if self.searchpath else None,
            trim_blocks=True,
            lstrip_blocks=True,
            comment_start_string="{##",
            comment_end_string='##}'
        )

        for k, v in get_jinja2_filters().items():
            self.jinja_env.filters[k] = v
        for k, v in get_jinja2_tests().items():
            self.jinja_env.tests[k] = v
        for k, v in get_jinja2_globals().items():
            self.jinja_env.globals[k] = v
        # Add self do_template method as global
        self.jinja_env.globals['lookup_template'] = self.do_template

    def render(self, template: str, data: Dict[str, Any]) -> str:
        """
        Render a template from file (if 'template' is a file in searchpath) or from string.
        Returns rendered result or empty string on error.
        """
        try:
            template_file = None
            if self.searchpath:
                candidate = Path(self.searchpath) / template
                if candidate.exists() and candidate.is_file():
                    template_file = template

            if template_file is not None:
                tpl = self.jinja_env.get_template(template_file)
            else:
                if self.is_template(template):
                    tpl = self.jinja_env.from_string(template)
                else:
                    tpl = self.jinja_env.from_string('')
            return tpl.render(**data)
        except (TemplateSyntaxError, UndefinedError, TemplateRuntimeError, TemplateAssertionError) as e:
            if template_file and hasattr(e, 'lineno'):
                self.console.print(f"[bold red]Jinja2 render error, line {e.lineno}:[/bold red] {e}")
            else:
                self.console.print(f"[bold red]Jinja2 error:[/bold red] {e}")
        except Exception as e:
            self.console.print(f"[bold red]Jinja2 error:[/bold red] {e}")
        return ""

    def do_template(self, data: dict, template: str) -> str:
        """
        Public method for use in template lookups or direct.
        """
        return self.render(template, data)

    def is_template(self, template_str: str) -> bool:
        """Returns True if this is valid jinja2 template syntax."""
        try:
            self.jinja_env.parse(template_str)
            return True
        except TemplateSyntaxError as e:
            lines = template_str.split('\n')
            self.console.print(f"[bold red]Template syntax error, line {e.lineno}:[/bold red] {str(e)}")
            if 0 < e.lineno <= len(lines):
                self.console.print(lines[e.lineno-1])
            return False

    def render_file(self, template_path: Union[str, Path], template_name: str, data: Dict[str, Any]) -> str:
        """
        Render a template file with the given data.

        Args:
            template_path: Path to template directory
            template_name: Name of template file
            data: Data to render template with

        Returns:
            Rendered template content
        """
        # Set the search path and render the template
        original_searchpath = self.searchpath
        try:
            self.searchpath = Path(template_path) if template_path else None
            # Update the Jinja environment with new searchpath
            if self.searchpath:
                self.jinja_env = jinja2.Environment(
                    loader=jinja2.FileSystemLoader(self.searchpath),
                    undefined=jinja2.StrictUndefined
                )
                # Re-add filters, globals, and tests
                for k, v in get_jinja2_filters().items():
                    self.jinja_env.filters[k] = v
                for k, v in get_jinja2_globals().items():
                    self.jinja_env.globals[k] = v
                for k, v in get_jinja2_tests().items():
                    self.jinja_env.tests[k] = v
                self.jinja_env.globals['lookup_template'] = self.do_template

            return self.render(template_name, data)
        finally:
            self.searchpath = original_searchpath
