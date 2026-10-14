#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import copy
import json
from typing import Any, Dict


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


def deep_merge_append(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge ``override`` into ``base`` and return a new dict (inputs are not modified).

    Semantics match ``yq eval-all '. as $item ireduce ({}; . *+ $item)'``:

    * dict + dict   -> merged recursively
    * list + list   -> ``override`` items are APPENDED to ``base`` items
    * anything else -> the value from ``override`` wins (including a type change)
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        current = result.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            result[key] = deep_merge_append(current, value)
        elif isinstance(current, list) and isinstance(value, list):
            result[key] = current + copy.deepcopy(value)
        else:
            result[key] = copy.deepcopy(value)
    return result
