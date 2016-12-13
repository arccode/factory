# -*- coding: utf-8 -*-
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Write value to hwmon files."""

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.utils.arg_utils import Arg


class HwmonWriteTest(unittest.TestCase):
  """Write value the the hwmon files."""
  ARGS = [
      Arg('name', str, 'The name of the hwmon.'),
      Arg('index', int,
          'The hwmon index if we have more than 1 with the same name.',
          default=0),
      Arg('file', str, 'The filename to write.'),
      Arg('value', str, 'The value we want to write to the file.'),
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()

  def runTest(self):
    devices = self._dut.hwmon.FindDevices('name', self.args.name)
    device = devices[self.args.index]
    path = self._dut.path.join(device.GetPath(), self.args.file)
    factory.console.info('Write %s to %s', self.args.value, path)
    self._dut.WriteFile(path, self.args.value)
