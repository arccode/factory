# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common Umpire classes.

This module provides constants and common Umpire classes.
"""

# "version" in Ping method return value to indicate server is Umpire server.
UMPIRE_DUT_RPC_VERSION = 3

# version for the umpire image. (This is the version that Dome sees, and
# should be uprev when ANY incompatible change for umpire image is done that
# needs Dome to restart umpire instance, for example, incompatible docker
# command line arguments change.)
# Remember to uprev the MOCK_UMPIRE_VERSION in py/dome/backend/tests.py too.
UMPIRE_VERSION = 5

# Valid keys in DUT info.
# TODO(pihsun): Most of these fields are probably not necessary after the match
# rules are removed.
DUT_INFO_KEYS = set(['sn', 'mlb_sn', 'firmware', 'ec', 'pd', 'stage',
                     'uuid', 'drop_slot'])

# Deprecated keys in DUT info.
LEGACY_DUT_INFO_KEYS = set(['board'])

# List of valid key prefix in DUT info. For example, a DUT may have several
# MACs, like mac.eth0, mac.wlan0. It accepts those keys with prefix 'mac'.
DUT_INFO_KEY_PREFIX = ['mac']

# IP should be decided by host IP inside Docker.
DEFAULT_SHOPFLOOR_SERVICE_PORT = 8090

UMPIRE_DEFAULT_PORT = 8080


class UmpireError(Exception):
  """General umpire exception class."""
