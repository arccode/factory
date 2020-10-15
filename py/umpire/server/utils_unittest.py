#!/usr/bin/env python3
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import errno
import unittest
from unittest import mock

from cros.factory.umpire.server import utils


class CreateLoopDeviceTest(unittest.TestCase):

  @mock.patch('os.mknod', return_value=True)
  @mock.patch('os.chown', return_value=True)
  def testCreateLoopDevice(self, *unused_mocked_funcs):
    self.assertTrue(utils.CreateLoopDevice("/dev/loop", 0, 256))

  @mock.patch('os.mknod', return_value=True)
  @mock.patch('os.chown', side_effect=OSError(errno.ENOENT, 'No such file'))
  def testCreateLoopDeviceRaiseException(self, *unused_mocked_funcs):
    self.assertFalse(utils.CreateLoopDevice("/dev/loop", 0, 256))


if __name__ == '__main__':
  unittest.main()
