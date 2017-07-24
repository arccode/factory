# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import logging
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
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
    ConfigType('umpire_config', 'umpire', 'yaml'),
    ConfigType('payload_config', 'payload', 'json')])

PayloadType = collections.namedtuple('PayloadType',
                                     ['type_name', 'import_pattern'])

PayloadTypes, PayloadTypeNames = _InitializeTypes([
    PayloadType('complete', 'complete/*'),
    PayloadType('firmware', 'firmware/*'),
    PayloadType('hwid', 'hwid/*'),
    PayloadType('netboot_cmdline', 'netboot/tftp/chrome-bot/*/cmdline'),
    PayloadType('netboot_firmware', 'netboot/image.net.bin'),
    PayloadType('netboot_kernel', 'netboot/tftp/chrome-bot/*/vmlinu*'),
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


def UnpackFactoryToolkit(env, toolkit_path, toolkit_hash):
  """Unpacks factory toolkit to toolkits/<toolkit_hash> directory.

  Note that if the destination directory already exists, it doesn't unpack.

  Args:
    env: UmpireEnv object.
    toolkit_path: Path to factory toolkit resources.
  """
  unpack_dir = os.path.join(env.device_toolkits_dir, toolkit_hash)
  if os.path.isdir(unpack_dir):
    logging.info('UnpackFactoryToolkit destination dir already exists: %s',
                 unpack_dir)
    return

  # Extract to temp directory first then move the directory to prevent
  # keeping a broken toolkit.
  with file_utils.TempDirectory(dir=env.temp_dir) as temp_dir:
    process_utils.Spawn(['sh', toolkit_path, '--noexec', '--target', temp_dir],
                        check_call=True, log=True)
    file_utils.TryMakeDirs(os.path.dirname(unpack_dir))
    os.rename(temp_dir, unpack_dir)
    logging.debug('Factory toolkit extracted to %s', unpack_dir)

  # TODO(b/36083439): Remove this part.
  # Inject MD5SUM in extracted toolkit as umpire read only.
  md5sum_path = os.path.join(unpack_dir, 'usr', 'local', 'factory', 'MD5SUM')
  file_utils.WriteFile(md5sum_path, '%s\n' % toolkit_hash)
  logging.debug('%r generated', md5sum_path)


def GetFilePayloadHash(payload):
  """Extracts hash from a dictionary of a file payload component.

  TODO(youcheng): Remove this function after b:38512373.

  Args:
    payload: A dictionary of a file payload component.

  Returns:
    Resource hash.
  """
  return payload['file'].split('.')[-2]
