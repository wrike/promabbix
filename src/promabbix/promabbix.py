#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import argparse
import os

from core.fs_utils import DataLoader, DataSaver
from core.template import Render
from rich_argparse import RichHelpFormatter
from pathlib import Path


class PromabbixApp:
    def __init__(self, loader=DataLoader(), saver=DataSaver(), parser=None):
        self.loader = loader
        self.saver = saver
        self.parser = parser if parser else self.app_args()

    def main(self):
        pargs = vars(self.app_args().parse_args())

        # Handle input: if alertrules is "-", read from STDIN
        if pargs['alertrules'] == '-':
            template_data = self.loader.load_from_stdin()
        else:
            template_data = self.loader.load_from_file(str(pargs['alertrules']))

        render = Render(searchpath=str(pargs['templates']))
        _zbx_template_data = render.do_template(template_data, str(pargs['template_name']))

        # Handle output: if output is "-", write to STDOUT
        if _zbx_template_data != '':
            if pargs['output'] == '-':
                self.saver.save_to_stdout(_zbx_template_data)
            else:
                output_path = Path(str(pargs['output'])).expanduser().resolve()
                self.saver.save(_zbx_template_data, output_path)
        # FIXME: return code here?

    def app_args(self):
        parser = argparse.ArgumentParser(description='Promabbix', formatter_class=RichHelpFormatter)

        parser.add_argument(
            'alertrules',
            action="store",
            default=None,
            type=str,
            help=('Path to prometheus aggregated alert rules (use "-" to read from STDIN)')
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


if __name__ == '__main__':
    PromabbixApp().main()
