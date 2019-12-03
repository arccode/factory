#!/usr/bin/env python2
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.gooftool import commands
from cros.factory.utils import type_utils


class HasFpmcuTest(unittest.TestCase):
  @mock.patch.object(commands, 'Shell')
  @mock.patch('os.path.exists')
  def testHasFpmcu(self, mock_exists, mock_shell):
    # Normal case: FPMCU exists:
    commands._has_fpmcu = None  # pylint: disable=protected-access
    mock_exists.return_value = True
    mock_shell.return_value = type_utils.Obj(
        stdout='mock_fp_board', stderr='', status=0, success=True)
    self.assertTrue(commands.HasFpmcu())

    # Normal case: FPMCU not exist:
    commands._has_fpmcu = None  # pylint: disable=protected-access
    mock_exists.return_value = False
    mock_shell.return_value = type_utils.Obj(
        stdout='', stderr='', status=0, success=True)
    self.assertFalse(commands.HasFpmcu())

    # Mismatch, case 1:
    commands._has_fpmcu = None  # pylint: disable=protected-access
    mock_exists.return_value = False
    mock_shell.return_value = type_utils.Obj(
        stdout='mock_fp_board', stderr='', status=0, success=True)
    with self.assertRaises(type_utils.Error):
      commands.HasFpmcu()

    # Mismatch, case 2:
    commands._has_fpmcu = None  # pylint: disable=protected-access
    mock_exists.return_value = True
    mock_shell.return_value = type_utils.Obj(
        stdout='stdout', stderr='stderr', status=1, success=False)
    with self.assertRaises(type_utils.Error):
      commands.HasFpmcu()

    # Mismatch, case 3:
    commands._has_fpmcu = None  # pylint: disable=protected-access
    mock_exists.return_value = True
    mock_shell.return_value = type_utils.Obj(
        stdout='', stderr='', status=0, success=True)
    with self.assertRaises(type_utils.Error):
      commands.HasFpmcu()


if __name__ == '__main__':
  unittest.main()
