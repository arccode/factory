#!/usr/bin/env python
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.gooftool import common
from cros.factory.gooftool import gsctool
from cros.factory.utils import type_utils


class GSCToolTest(unittest.TestCase):
  def setUp(self):
    self.shell = mock.Mock(spec=common.Shell)
    self.gsctool = gsctool.GSCTool(shell=self.shell)

  def testGetCr50FirmwareVersion(self):
    self._SetGSCToolUtilityResult(stdout=('start\n'
                                          'target running protocol version -1\n'
                                          'offsets: .....\n'
                                          'RO_FW_VER=1.2.34\n'
                                          'RW_FW_VER=5.6.78\n'))
    fw_ver = self.gsctool.GetCr50FirmwareVersion()
    self._CheckCalledCommand(['/usr/sbin/gsctool', '-M', '-a', '-f'])
    self.assertEqual(fw_ver.ro_version, '1.2.34')
    self.assertEqual(fw_ver.rw_version, '5.6.78')

    self._SetGSCToolUtilityResult(stdout=('invalid output\n'))
    self.assertRaises(gsctool.GSCToolError, self.gsctool.GetCr50FirmwareVersion)

    self._SetGSCToolUtilityResult(status=1)
    self.assertRaises(gsctool.GSCToolError, self.gsctool.GetCr50FirmwareVersion)

  def testUpdateCr50Firmware(self):
    self._SetGSCToolUtilityResult()
    self.assertEqual(self.gsctool.UpdateCr50Firmware('img'),
                     gsctool.UpdateResult.NOOP)
    self._CheckCalledCommand(['/usr/sbin/gsctool', '-a', '-u', 'img'])

    self._SetGSCToolUtilityResult(status=1)
    self.assertEqual(self.gsctool.UpdateCr50Firmware('img'),
                     gsctool.UpdateResult.ALL_UPDATED)

    self._SetGSCToolUtilityResult(status=2)
    self.assertEqual(self.gsctool.UpdateCr50Firmware('img'),
                     gsctool.UpdateResult.RW_UPDATED)

    self._SetGSCToolUtilityResult(status=3)
    self.assertRaises(gsctool.GSCToolError, self.gsctool.UpdateCr50Firmware,
                      'img')

  def testGetImageInfo(self):
    self._SetGSCToolUtilityResult(stdout=('read ... bytes from ...\n'
                                          'IMAGE_RO_FW_VER=1.2.34\n'
                                          'IMAGE_RW_FW_VER=5.6.78\n'
                                          'IMAGE_BID_STRING=00000000\n'
                                          'IMAGE_BID_MASK=00000000\n'
                                          'IMAGE_BID_FLAGS=00000abc\n'))
    image_info = self.gsctool.GetImageInfo('img')
    self._CheckCalledCommand(['/usr/sbin/gsctool', '-M', '-b', 'img'])
    self.assertEqual(image_info.ro_fw_version, '1.2.34')
    self.assertEqual(image_info.rw_fw_version, '5.6.78')
    self.assertEqual(image_info.board_id_flags, 0xabc)

    self._SetGSCToolUtilityResult(stdout=('read ... bytes from ...\n'
                                          'IMAGE_BID_FLAGS=00000abc\n'))
    self.assertRaises(gsctool.GSCToolError, self.gsctool.GetImageInfo, 'img')

    self._SetGSCToolUtilityResult(status=1)
    self.assertRaises(gsctool.GSCToolError, self.gsctool.GetImageInfo, 'img')

  def testSetFactoryMode(self):
    self._SetGSCToolUtilityResult()
    self.gsctool.SetFactoryMode(True)
    self._CheckCalledCommand(['/usr/sbin/gsctool', '-a', '-F', 'enable'])

    self.gsctool.SetFactoryMode(False)
    self._CheckCalledCommand(['/usr/sbin/gsctool', '-a', '-F', 'disable'])

    self._SetGSCToolUtilityResult(status=1)
    self.assertRaises(gsctool.GSCToolError, self.gsctool.SetFactoryMode, True)

  def testIsFactoryMode(self):
    self._SetGSCToolUtilityResult(stdout=('...\nCapabilities are default.\n'))
    self.assertFalse(self.gsctool.IsFactoryMode())
    self._CheckCalledCommand(['/usr/sbin/gsctool', '-a', '-I'])

    self._SetGSCToolUtilityResult(stdout=('...\nCapabilities are modified.\n'))
    self.assertTrue(self.gsctool.IsFactoryMode())

    self._SetGSCToolUtilityResult(status=1)
    self.assertRaises(gsctool.GSCToolError, self.gsctool.IsFactoryMode)

  def _SetGSCToolUtilityResult(self, stdout='', status=0):
    self.shell.return_value = type_utils.Obj(
        success=status == 0, status=status, stdout=stdout, stderr='')

  def _CheckCalledCommand(self, cmd):
    # pylint: disable=unsubscriptable-object
    self.assertEqual(self.shell.call_args[0][0], cmd)


if __name__ == '__main__':
  unittest.main()
