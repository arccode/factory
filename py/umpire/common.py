# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Common Umpire classes.

This module provides constants and common Umpire classes.
"""

import logging
import os
import re
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.utils.file_utils import CheckPath, Md5sumInHex, Glob
from cros.factory.test.utils import Enum


UMPIRE_CLI = 'umpire'
UMPIRE_DAEMON = 'umpired'

# Base serving path for ShopFloorHander.
HANDLER_BASE = '/shop_floor'

# "version" in Ping method return value to indicate server is Umpire server.
UMPIRE_VERSION = 3

# Resource types which can use "umpire update" to update.
UPDATEABLE_RESOURCES = ['factory_toolkit', 'firmware', 'fsi', 'hwid']

# Supported resource types.
ResourceType = Enum([
    'FACTORY_TOOLKIT', 'FIRMWARE', 'HWID', 'NETBOOT_VMLINUX', 'ROOTFS_RELEASE',
    'ROOTFS_TEST'])

# Valid keys in DUT info.
DUT_INFO_KEYS = set(['sn', 'mlb_sn', 'board', 'firmware', 'ec', 'stage'])

# Required fields in resource map.
REQUIRED_RESOURCE_MAP_FIELDS = set(['__token__', 'shop_floor_handler'])

# List of valid key prefix in DUT info. For example, a DUT may have several
# MACs, like mac.eth0, mac.wlan0. It accepts those keys with prefix 'mac'.
DUT_INFO_KEY_PREFIX = ['mac']

# Valid matchers for ruleset.
SCALAR_MATCHERS = set(['sn', 'mlb_sn'])
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

# Relative path of factory toolkit in a factory bundle.
BUNDLE_FACTORY_TOOLKIT_PATH = os.path.join('factory_toolkit',
                                           'install_factory_toolkit.run')
BUNDLE_MANIFEST = 'MANIFEST.yaml'


class UmpireError(Exception):

  """General umpire exception class."""
  pass


def VerifyResource(res_file):
  """Verifies a resource file.

  It verifies a file by calculating its md5sum and its leading N-digit
  should be the same as the filename's hash section.

  Args:
    res_file: path to a resource file

  Returns:
    True if the file's checksum is verified.
  """
  if not os.path.isfile(res_file):
    logging.error('VerifyResource: file missing: ' + res_file)
    return False
  hashsum = GetHashFromResourceName(res_file)
  if not hashsum:
    logging.error('Ill-formed resource filename: ' + res_file)
    return False
  calculated_hashsum = Md5sumInHex(res_file)
  return calculated_hashsum.startswith(hashsum)


def ParseResourceName(res_file):
  """Parses resource file name.

  Args:
    res_file: path to a resource file

  Returns:
    (base_name, version, hash).
    None if res_file is ill-formed.
  """
  match = RESOURCE_FILE_PATTERN.match(res_file)
  return match.groups() if match else None


def GetHashFromResourceName(res_file):
  """Gets hash from resource file name.

  Args:
    res_file: path to a resource file

  Returns:
    hash value in resource file name's tail.
    None if res_file is ill-formed.
  """
  match = RESOURCE_FILE_PATTERN.match(res_file)
  return match.group(3) if match else None


def GetVersionFromResourceName(res_file):
  """Gets version from resource file name.

  Args:
    res_file: path to a resource file

  Returns:
    Version in resource file name's second latest segment (# delimited).
    None if res_file is ill-formed.
  """
  match = RESOURCE_FILE_PATTERN.match(res_file)
  return match.group(2) if match else None


# pylint: disable=R0901
class BundleManifestIgnoreGlobLoader(yaml.Loader):

  """A YAML loader that loads factory bundle manifest with !glob ignored."""

  def __init__(self, *args, **kwargs):
    def FakeGlobConstruct(unused_loader, unused_node):
      return None

    yaml.Loader.__init__(self, *args, **kwargs)
    self.add_constructor('!glob', FakeGlobConstruct)


# pylint: disable=R0901
class BundleManifestLoader(yaml.Loader):

  """A YAML loader that loads factory bundle manifest with !glob ignored."""

  def __init__(self, *args, **kwargs):
    yaml.Loader.__init__(self, *args, **kwargs)
    # TODO(deanliao): refactor out Glob from py/tools/finalize_bundle.py
    #     to py/utils/bundle_manifest.py and move the LoadBundleManifest
    #     related methods to that module.
    self.add_constructor('!glob', Glob.Construct)


def LoadBundleManifest(path, ignore_glob=False):
  """Loads factory bundle's MANIFEST.yaml (with !glob ignored).

  Args:
    path: path to factory bundle's MANIFEST.yaml
    ignore_glob: True to ignore glob.

  Returns:
    A Python object the manifest file represents.

  Raises:
    IOError if file not found.
    UmpireError if the manifest fail to load and parse.
  """
  CheckPath(path, description='factory bundle manifest')
  try:
    loader = (BundleManifestIgnoreGlobLoader if ignore_glob else
              BundleManifestLoader)
    with open(path) as f:
      return yaml.load(f, Loader=loader)
  except Exception as e:
    raise UmpireError('Failed to load MANIFEST.yaml: ' + str(e))
