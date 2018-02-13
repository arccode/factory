# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common Umpire classes.

This module provides constants and common Umpire classes.
"""

# "version" in Ping method return value to indicate server is Umpire server.
UMPIRE_DUT_RPC_VERSION = 3

# Valid keys in DUT info.
DUT_INFO_KEYS = set(['sn', 'mlb_sn', 'firmware', 'ec', 'pd', 'stage'])

# Deprecated keys in DUT info.
LEGACY_DUT_INFO_KEYS = set(['board'])

# List of valid key prefix in DUT info. For example, a DUT may have several
# MACs, like mac.eth0, mac.wlan0. It accepts those keys with prefix 'mac'.
DUT_INFO_KEY_PREFIX = ['mac']

# Valid matchers for ruleset.
SCALAR_MATCHERS = set(['sn', 'mlb_sn', 'stage'])
RANGE_MATCHERS = set(['sn_range', 'mlb_sn_range'])
# A set of scalar matchers. It checks DUT value which's key's prefix matches.
SCALAR_PREFIX_MATCHERS = set(['mac'])

# IP should be decided by host IP inside Docker.
DEFAULT_SHOPFLOOR_SERVICE_PORT = 8090

UMPIRE_DEFAULT_PORT = 8080


class UmpireError(Exception):
  """General umpire exception class."""
  pass
