# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re

import factory_common  # pylint: disable=unused-import
from cros.factory.gooftool import common as gooftool_common
from cros.factory.utils import type_utils


# Path to the relied `gsctool` command line utility.
GSCTOOL_PATH = '/usr/sbin/gsctool'


class FirmwareVersion(type_utils.Obj):
  def __init__(self, ro_version, rw_version):
    super(FirmwareVersion, self).__init__(ro_version=ro_version,
                                          rw_version=rw_version)

class ImageInfo(type_utils.Obj):
  def __init__(self, ro_fw_version, rw_fw_version, board_id_flags):
    super(ImageInfo, self).__init__(ro_fw_version=ro_fw_version,
                                    rw_fw_version=rw_fw_version,
                                    board_id_flags=board_id_flags)


UpdateResult = type_utils.Enum(['NOOP', 'ALL_UPDATED', 'RW_UPDATED'])


class GSCToolError(Exception):
  pass


class GSCTool(object):
  """Helper class to operate on Cr50 firmware by the `gsctool` cmdline utility.
  """

  def __init__(self, shell=None):
    self._shell = shell or gooftool_common.Shell

  def GetCr50FirmwareVersion(self):
    """Get the version of the current Cr50 firmware.

    Returns:
      Instance of `FirmwareVersion`.

    Raises:
      `GSCToolError` if fails.
    """
    cmd = [GSCTOOL_PATH, '-M', '-a', '-f']
    return self._GetAttrs(cmd, FirmwareVersion, {'RO_FW_VER': 'ro_version',
                                                 'RW_FW_VER': 'rw_version'},
                          'firmware versions.')

  def UpdateCr50Firmware(self, image_file):
    """Update the Cr50 firmware.

    Args:
      image_file: Path to the image file that contains the cr50 firmware image.

    Returns:
      Enum element of `UpdateResult` if succeeds.

    Raises:
      `GSCToolError` if update fails.
    """
    cmd = [GSCTOOL_PATH, '-a', '-u', image_file]
    # 0: noop. 1: all_updated, 2: rw_updated, 3: update_error
    # See platform/ec/extra/usb_updater/gsctool.h for more detail.
    cmd_result_checker = lambda result: 0 <= result.status <= 2
    cmd_result = self._InvokeCommand(cmd, 'Failed to update the Cr50 firmware',
                                     cmd_result_checker=cmd_result_checker)
    return {0: UpdateResult.NOOP,
            1: UpdateResult.ALL_UPDATED,
            2: UpdateResult.RW_UPDATED}[cmd_result.status]

  def GetImageInfo(self, image_file):
    """Get the version and the board id of the specified Cr50 firmware image.

    Args:
      image_file: Path to the Cr50 firmware image file.

    Returns:
      Instance of `ImageVersion`.

    Raises:
      `GSCToolError` if fails.
    """
    cmd = [GSCTOOL_PATH, '-M', '-b', image_file]
    info = self._GetAttrs(cmd, ImageInfo, {'IMAGE_RO_FW_VER': 'ro_fw_version',
                                           'IMAGE_RW_FW_VER': 'rw_fw_version',
                                           'IMAGE_BID_FLAGS': 'board_id_flags'},
                          'image versions.')
    # pylint: disable=attribute-defined-outside-init
    info.board_id_flags = int(info.board_id_flags, 16)
    return info

  def _GetAttrs(self, cmd, AttrClass, fields, target_name):
    cmd_result = self._InvokeCommand(cmd, 'failed to get the %s' % target_name)

    translated_kwargs = {}
    for line in cmd_result.stdout.splitlines():
      line = line.strip()
      for field_name, attr_name in fields.iteritems():
        if line.startswith(field_name + '='):
          translated_kwargs[attr_name] = line[len(field_name) + 1:]
    missing_fields = [field_name for field_name, attr_name in fields.iteritems()
                      if attr_name not in translated_kwargs]
    if missing_fields:
      raise GSCToolError('%r Field(s) are missing, gsctool stdout=%r' %
                         (missing_fields, cmd_result.stdout))

    return AttrClass(**translated_kwargs)

  def SetFactoryMode(self, enable):
    """Enable or disable the cr50 factory mode.

    Args:
      enable: `True` to enable the factory mode;  `False` to disable the
          factory mode.

    Raises:
      `GSCToolError` if fails.
    """
    enable_str = 'enable' if enable else 'disable'
    cmd = [GSCTOOL_PATH, '-a', '-F', enable_str]
    self._InvokeCommand(
        cmd, 'failed to %s the cr50 factory mode' % enable_str)

  def IsFactoryMode(self):
    """Queries if the cr50 is in factory mode or not.

    Returns:
      `True` if it's in factory mode.

    Raises:
      `GSCToolError` if fails.
    """
    result = self._InvokeCommand([GSCTOOL_PATH, '-a', '-I'],
                                 'getting ccd info fails in cr50')

    # The pattern of output is as below in case of factory mode enabled:
    # State: Locked
    # Password: None
    # Flags: 000000
    # Capabilities, current and default:
    #   ...
    # Capabilities are modified.
    #
    # If factory mode is disabed then the last line would be
    # Capabilities are default.
    return bool(re.search('^Capabilities are modified.$', result.stdout,
                          re.MULTILINE))

  def _InvokeCommand(self, cmd, failure_msg, cmd_result_checker=None):
    cmd_result_checker = cmd_result_checker or (lambda result: result.success)
    result = self._shell(cmd)
    if not cmd_result_checker(result):
      raise GSCToolError(failure_msg + ' (command result: %r)' % result)
    return result
