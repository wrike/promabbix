#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import click

from .cli.generate_template import generate_template


@click.group(invoke_without_command=True)
@click.version_option()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Promabbix - Prometheus to Zabbix integration tool."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# Register subcommands
cli.add_command(generate_template)


def main() -> None:
    """Entry point for the promabbix console script."""
    cli()


if __name__ == '__main__':
    main()
