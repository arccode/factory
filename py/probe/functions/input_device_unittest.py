#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import textwrap
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import input_device
from cros.factory.utils import file_utils


class InputDeviceFunctionTest(unittest.TestCase):
  def setUp(self):
    self.tmp_file = file_utils.CreateTemporaryFile()
    mock_content = textwrap.dedent("""\
    I: Bus=0000 Vendor=0000 Product=0000 Version=0000
    N: Name="Google HDMI"
    P: Phys=ALSA
    S: Sysfs=/devices/pci0000:00/0000:00:02.0/0000:05:00.1/sound/card1/input13
    U: Uniq=
    H: Handlers=event12
    B: PROP=0
    B: EV=21
    B: SW=140

    I: Bus=0003 Vendor=147d Product=1020 Version=0110
    N: Name="Google Mouse"
    P: Phys=usb-0000:00:1d.0-1.1/input0
    S: Sysfs=/devices/pci0000:00/0000:00:1d.0/usb2/2-1/input/input17
    U: Uniq=
    H: Handlers=mouse0 event3
    B: PROP=0
    B: EV=17
    B: KEY=f0000 0 0 0 0
    B: REL=103
    B: MSC=10
    """)
    with open(self.tmp_file, 'w') as f:
      f.write(mock_content)
    self.original_path = input_device.INPUT_DEVICE_PATH
    input_device.INPUT_DEVICE_PATH = self.tmp_file

  def tearDown(self):
    if os.path.isfile(self.tmp_file):
      os.remove(self.tmp_file)
    input_device.INPUT_DEVICE_PATH = self.original_path

  def testGetInputDevices(self):
    expected = [
        {'vendor': '0000',
         'product': '0000',
         'version': '0000',
         'bus': '0000',
         'name': 'Google HDMI',
         'sysfs': '/devices/pci0000:00/0000:00:02.0/0000:05:00.1/'
                  'sound/card1/input13',
         'event': 'event12'},
        {'vendor': '147d',
         'product': '1020',
         'version': '0110',
         'bus': '0003',
         'name': 'Google Mouse',
         'sysfs': '/devices/pci0000:00/0000:00:1d.0/usb2/2-1/input/input17',
         'event': 'event3'}]

    devices = input_device.GetInputDevices()
    self.assertEquals(devices, expected)


if __name__ == '__main__':
  unittest.main()
