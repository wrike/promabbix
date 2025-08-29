#!/usr/bin/env python3
# -*- coding: utf-8 -*- #
#
# Copyright 2025 Wrike Inc.
#

import json


def isjson(data):
    """ Check if the data is a json
    """
    try:
        if isinstance(data, str):
            _ = json.loads(data)
        elif isinstance(data, (dict, list)):
            return True
        else:
            return False
    except Exception as e:
        return False
    return True
