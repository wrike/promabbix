#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import json
from typing import Any


def isjson(data: Any) -> bool:
    """ Check if the data is a json
    """
    try:
        if isinstance(data, str):
            _ = json.loads(data)
        elif isinstance(data, (dict, list)):
            return True
        else:
            return False
    except Exception:
        return False
    return True
