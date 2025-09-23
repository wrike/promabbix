# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#
"""Promabbix - Tool for connecting Prometheus to Zabbix monitoring."""

__author__ = "Andrey Menzhinsky (menai34)"
__license__ = "MIT"
__maintainer__ = "Wrike Inc."
__status__ = "Production/Stable"

# Dynamic version from setuptools-scm
try:
    from ._version import version as __version__
except ImportError:
    # Fallback for development without setuptools-scm
    __version__ = "dev"

__all__ = ["__version__"]
