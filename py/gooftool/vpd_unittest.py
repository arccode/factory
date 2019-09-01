#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.gooftool import common
from cros.factory.gooftool import vpd
from cros.factory.utils import type_utils


class VPDToolTest(unittest.TestCase):
  """Unittest for VPDTool."""

  def setUp(self):
    self.mocked_shell = mock.Mock(spec=common.Shell)
    self.vpd = vpd.VPDTool(shell=self.mocked_shell)

  def testGetData(self):
    self.mocked_shell.return_value = self._CreateSuccessShellOutput('bbb')
    self.assertEqual(self.vpd.GetValue('aaa'), 'bbb')
    self._CheckMockedShellCmd(['vpd', '-g', 'aaa'])

    self.mocked_shell.return_value = self._CreateSuccessShellOutput('')
    self.assertEqual(self.vpd.GetValue('ccc'), '')

    self.mocked_shell.return_value = self._CreateFailShellOutput(1)
    self.assertEqual(self.vpd.GetValue('aaa', 123), 123)

  def testGetAllData(self):
    self.mocked_shell.return_value = self._CreateSuccessShellOutput(
        'aa=bb\0cc==\0')
    self.assertEqual(self.vpd.GetAllData(), {'aa': 'bb', 'cc': '='})
    self._CheckMockedShellCmd(['vpd', '-l', '--null-terminated'])

  def testUpdateData(self):
    self.vpd.UpdateData({'cc': None})
    self._CheckMockedShellCmd(['vpd', '-d', 'cc'])

    self.vpd.UpdateData({'aa': 'bb'})
    self._CheckMockedShellCmd(['vpd', '-s', 'aa=bb'])

  def testInvalidKey(self):
    self.assertRaises(ValueError, self.vpd.GetValue, '')
    self.assertRaises(ValueError, self.vpd.GetValue, 'aaa=bb')
    self.assertRaises(ValueError, self.vpd.UpdateData, {'aa': 'bb', '': None})

  def testSpecificFilenameAndPartition(self):
    self.mocked_shell.return_value = self._CreateSuccessShellOutput('v')
    self.assertEqual(
        self.vpd.GetValue('key', filename='f',
                          partition=vpd.VPD_READONLY_PARTITION_NAME),
        'v')
    self._CheckMockedShellCmd(['vpd', '-i', 'RO_VPD', '-f', 'f', '-g', 'key'])

  @classmethod
  def _CreateSuccessShellOutput(cls, stdout):
    return type_utils.Obj(stdout=stdout, stderr='', status=0, success=True)

  @classmethod
  def _CreateFailShellOutput(cls, status):
    return type_utils.Obj(stdout='', stderr='', status=status, success=False)

  def _CheckMockedShellCmd(self, cmd):
    # pylint: disable=unpacking-non-sequence
    args, unused_kwargs = self.mocked_shell.call_args
    self.assertTrue(len(args) > 0)
    self.assertEqual(args[0], cmd)


if __name__ == '__main__':
  unittest.main()
