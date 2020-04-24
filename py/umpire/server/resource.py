# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections

from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


def _InitializeTypes(type_list):
  types = {}
  type_names = []
  for t in type_list:
    types[t.type_name] = t
    type_names.append(t.type_name)
  return type_utils.Obj(**types), type_utils.Enum(type_names)


ConfigType = collections.namedtuple('ConfigType',
                                    ['type_name', 'fn_prefix', 'fn_suffix'])

ConfigTypes, ConfigTypeNames = _InitializeTypes([
    ConfigType('umpire_config', 'umpire', 'json'),
    ConfigType('payload_config', 'payload', 'json'),
    ConfigType('multicast_config', 'multicast', 'json')])

PayloadType = collections.namedtuple('PayloadType',
                                     ['type_name', 'import_pattern'])

PayloadTypes, PayloadTypeNames = _InitializeTypes([
    PayloadType('complete', 'complete/*'),
    PayloadType('firmware', 'firmware/*'),
    PayloadType('hwid', 'hwid/*'),
    PayloadType('netboot_cmdline', 'netboot/tftp/chrome-bot/*/cmdline'),
    PayloadType('netboot_firmware', 'netboot/image.net.bin'),
    PayloadType('netboot_kernel', 'netboot/tftp/chrome-bot/*/vmlinu*'),
    PayloadType('project_config', 'project_config/*'),
    PayloadType('release_image', 'release_image/*'),
    PayloadType('test_image', 'test_image/*'),
    PayloadType('toolkit', 'toolkit/*')
])


def GetConfigType(type_name):
  """Gets the ConfigType object of a type_name.

  Args:
    type_name: An element of ConfigTypeNames.

  Returns:
    Corresponding ConfigType.
  """
  return getattr(ConfigTypes, type_name)


def GetPayloadType(type_name):
  """Gets the PayloadType object of a type_name.

  Args:
    type_name: An element of PayloadTypeNames.

  Returns:
    Corresponding PayloadType.
  """
  return getattr(PayloadTypes, type_name)


def GetResourceHashFromFile(file_path):
  """Calculates hash of a resource file.

  Args:
    file_path: path to the file.

  Returns:
    Hash of the file in hexadecimal.
  """
  return file_utils.MD5InHex(file_path)


def BuildConfigFileName(type_name, file_path):
  """Builds resource name for a config file.

  Args:
    type_name: An element of ConfigTypeNames.
    file_path: path to the config file.

  Returns:
    Resource name.
  """
  cfg_type = GetConfigType(type_name)
  return '.'.join([cfg_type.fn_prefix,
                   GetResourceHashFromFile(file_path),
                   cfg_type.fn_suffix])


def IsConfigFileName(basename):
  """Check if basename is a config file."""
  s = basename.split('.')
  if len(s) == 3:
    for type_name in ConfigTypeNames:
      type_info = getattr(ConfigTypes, type_name)
      if s[0] == type_info.fn_prefix and s[2] == type_info.fn_suffix:
        return True
  return False
