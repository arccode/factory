# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.gooftool import common as gooftool_common


class CrosConfig:
  """Helper class to get data from cros_config."""

  def __init__(self, shell=None, dut=None):
    self._shell = shell or gooftool_common.Shell
    self._dut = dut

  def GetValue(self, path, key):
    return self._shell(['cros_config', path, key], sys_interface=self._dut)

  def GetWhiteLabelTag(self):
    """Get whitelabel-tag value of this device.

    Returns:
      A tuple of (|is_whitelabel|, |whitelabel_tag|).
      |is_whitelabel| indicates if this device is whitelabel or not.
      |whitelabel_tag| is the value of whitelabel-tag if |is_whitelabel| is
      True.
    """
    result = self.GetValue('/identity', 'whitelabel-tag')
    return result.success, (result.stdout.strip() if result.stdout else '')
