# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.gooftool import common as gooftool_common

# Path to the product name and sku id of the device.
# ARM devices: DEVICE_TREE_COMPATIBLE_PATH and DEVICE_TREE_SKU_ID_PATH
# x86 devices: PRODUCT_NAME_PATH and PRODUCT_SKU_ID_PATH
DEVICE_TREE_COMPATIBLE_PATH = '/proc/device-tree/compatible'
PRODUCT_NAME_PATH = '/sys/class/dmi/id/product_name'
DEVICE_TREE_SKU_ID_PATH = '/proc/device-tree/firmware/coreboot/sku-id'
PRODUCT_SKU_ID_PATH = '/sys/class/dmi/id/product_sku'


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

  def GetPlatformName(self):
    result = self.GetValue('/identity', 'platform-name')
    return result.stdout.strip() if result.stdout else ''

  def GetModelName(self):
    result = self.GetValue('/', 'name')
    return result.stdout.strip() if result.stdout else ''

  def GetFingerPrintBoard(self):
    result = self.GetValue('/fingerprint', 'board')
    return result.stdout.strip() if result.stdout else ''

  def GetProductName(self):
    result_x86 = self.GetValue('/identity', 'smbios-name-match')
    result_arm = self.GetValue('/identity', 'device-tree-compatible-match')
    result = result_x86 or result_arm
    return result.stdout.strip() if result.stdout else ''

  def GetCustomizationId(self):
    result = self.GetValue('/identity', 'customization-id')
    return result.stdout.strip() if result.stdout else ''

  def GetSkuID(self):
    result = self.GetValue('/identity', 'sku-id')
    return result.stdout.strip() if result.stdout else ''

  def GetBrandCode(self):
    result = self.GetValue('/', 'brand-code')
    return result.stdout.strip() if result.stdout else ''
