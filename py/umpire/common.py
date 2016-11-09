# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common Umpire classes.

This module provides constants and common Umpire classes.
"""

import os
import re

import factory_common  # pylint: disable=W0611
from cros.factory.utils import type_utils


# Base serving path for ShopFloorHander.
HANDLER_BASE = '/shop_floor'

# "version" in Ping method return value to indicate server is Umpire server.
UMPIRE_VERSION = 3

# Resource types which can use "umpire update" to update.
UPDATEABLE_RESOURCES = ['factory_toolkit', 'firmware', 'fsi', 'hwid']

# Supported resource types.
ResourceType = type_utils.Enum([
    'FACTORY_TOOLKIT', 'FIRMWARE', 'HWID', 'NETBOOT_FIRMWARE',
    'NETBOOT_VMLINUX', 'ROOTFS_RELEASE', 'ROOTFS_TEST'])

# Valid keys in DUT info.
DUT_INFO_KEYS = set(['sn', 'mlb_sn', 'board', 'firmware', 'ec', 'pd', 'stage'])

# Required fields in resource map.
REQUIRED_RESOURCE_MAP_FIELDS = set(['__token__', 'shop_floor_handler'])

# List of valid key prefix in DUT info. For example, a DUT may have several
# MACs, like mac.eth0, mac.wlan0. It accepts those keys with prefix 'mac'.
DUT_INFO_KEY_PREFIX = ['mac']

# Valid matchers for ruleset.
SCALAR_MATCHERS = set(['sn', 'mlb_sn', 'stage'])
RANGE_MATCHERS = set(['sn_range', 'mlb_sn_range'])
# A set of scalar matchers. It checks DUT value which's key's prefix matches.
SCALAR_PREFIX_MATCHERS = set(['mac'])

# Length of a resource file's hash, which is the leftmost N digit of
# the file's MD5SUM in hex format.
RESOURCE_HASH_DIGITS = 8

# Resource filename format:
#     <original_filename>#<optional_version>#<n_hex_digit_hash>
RESOURCE_FILE_PATTERN = re.compile(
    r'(.+)#(.*)#([0-9a-f]{%d})$' % RESOURCE_HASH_DIGITS)

# Default Umpire base directory relative to root dir.
DEFAULT_BASE_DIR = os.path.join('var', 'db', 'factory', 'umpire')
DEFAULT_SERVER_DIR = os.path.join('usr', 'local', 'factory')

EMPTY_FILE_HASH = 'd41d8cd9'
DUMMY_RESOURCE = 'none##' + EMPTY_FILE_HASH


class UmpireError(Exception):

  """General umpire exception class."""
  pass
