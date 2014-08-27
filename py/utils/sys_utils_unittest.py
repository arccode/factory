#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for sys_utils module."""

import mox
import os
import tempfile
import unittest

import factory_common # pylint: disable=W0611
from cros.factory.utils import file_utils
from cros.factory.utils import sys_utils
from cros.factory.utils.process_utils import Spawn


SAMPLE_INTERRUPTS = """           CPU0       CPU1       CPU2       CPU3
  0:        124          0          0          0   IO-APIC-edge      timer
  1:         19        683          7         14   IO-APIC-edge      i8042
NMI:        612        631        661        401   Non-maskable interrupts
SPU:          0          0          0          0   Spurious interrupts"""


class GetInterruptsTest(unittest.TestCase):
  """Unit tests for GetInterrupts."""
  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.VerifyAll()
    self.mox.UnsetStubs()

  def testGetCount(self):
    self.mox.StubOutWithMock(file_utils, 'ReadLines')
    file_utils.ReadLines('/proc/interrupts').AndReturn(
      SAMPLE_INTERRUPTS.split('\n'))
    self.mox.ReplayAll()

    ints = sys_utils.GetInterrupts()
    # Digit-type interrupts:
    self.assertEqual(ints['0'], 124)
    self.assertEqual(ints['1'], 19 + 683 + 7 + 14)

    # String-type interrupts:
    self.assertEqual(ints['NMI'], 612 + 631 + 661 + 401)
    self.assertEqual(ints['SPU'], 0)

  def testFailToReadProcInterrupts(self):
    self.mox.StubOutWithMock(file_utils, 'ReadLines')
    file_utils.ReadLines('/proc/interrupts').AndReturn(None)
    self.mox.ReplayAll()

    self.assertRaisesRegexp(
        OSError, r"Unable to read /proc/interrupts",
        sys_utils.GetInterrupts)


SAMPLE_INPUT_DEVICES = """I: Bus=0019 Vendor=0000 Product=0005 Version=0000
N: Name="Lid Switch"
P: Phys=PNP0C0D/button/input0
S: Sysfs=/devices/LNXSYSTM:00/device:00/PNP0C0D:00/input/input0
U: Uniq=
H: Handlers=lid_event_handler lid_event_handler event0
B: PROP=0
B: EV=21
B: SW=1

I: Bus=0019 Vendor=0000 Product=0001 Version=0000
N: Name="Power Button"
P: Phys=PNP0C0C/button/input0
S: Sysfs=/devices/LNXSYSTM:00/device:00/PNP0C0C:00/input/input1
U: Uniq=
H: Handlers=kbd event1
B: PROP=0
B: EV=3
B: KEY=10000000000000 0

I: Bus=0019 Vendor=0000 Product=0001 Version=0000
N: Name="Power Button"
P: Phys=LNXPWRBN/button/input0
S: Sysfs=/devices/LNXSYSTM:00/LNXPWRBN:00/input/input2
U: Uniq=
H: Handlers=kbd event2
B: PROP=0
B: EV=3
B: KEY=10000000000000 0

I: Bus=0011 Vendor=0001 Product=0001 Version=ab83
N: Name="AT Translated Set 2 keyboard"
P: Phys=isa0060/serio0/input0
S: Sysfs=/devices/platform/i8042/serio0/input/input3
U: Uniq=
H: Handlers=sysrq kbd event3
B: PROP=0
B: EV=120013
B: KEY=400402000000 3803078f800d001 feffffdfffefffff fffffffffffffffe
B: MSC=10
B: LED=7

I: Bus=0018 Vendor=0000 Product=0000 Version=0000
N: Name="Atmel maXTouch Touchscreen"
P: Phys=i2c-3-004a/input0
S: Sysfs=/devices/platform/80860F41:03/i2c-3/3-004a/input/input4
U: Uniq=
H: Handlers=event4
B: PROP=0
B: EV=b
B: KEY=400 0 0 0 0 0
B: ABS=661800001000003

I: Bus=0018 Vendor=0000 Product=0000 Version=0000
N: Name="Atmel maXTouch Touchpad"
P: Phys=i2c-0-004b/input0
S: Sysfs=/devices/platform/80860F41:00/i2c-0/0-004b/input/input5
U: Uniq=
H: Handlers=event5
B: PROP=5
B: EV=b
B: KEY=e520 10000 0 0 0 0
B: ABS=661800001000003

I: Bus=0000 Vendor=0000 Product=0000 Version=0000
N: Name="HDA Intel HDMI"
P: Phys=ALSA
S: Sysfs=/devices/pci0000:00/0000:00:1b.0/sound/card1/input6
U: Uniq=
H: Handlers=event6
B: PROP=0
B: EV=21
B: SW=140

I: Bus=0000 Vendor=0000 Product=0000 Version=0000
N: Name="HDA Intel HDMI"
P: Phys=ALSA
S: Sysfs=/devices/pci0000:00/0000:00:1b.0/sound/card1/input7
U: Uniq=
H: Handlers=event7
B: PROP=0
B: EV=21
B: SW=140
"""


class GetI2CBusTest(unittest.TestCase):
  """Unit tests for GetI2CBus."""
  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.VerifyAll()
    self.mox.UnsetStubs()

  def testTouchpad(self):
    self.mox.StubOutWithMock(file_utils, 'Read')
    file_utils.Read('/proc/bus/input/devices').AndReturn(SAMPLE_INPUT_DEVICES)
    self.mox.ReplayAll()
    self.assertEqual(sys_utils.GetI2CBus(['Dummy device name',
                                          'Atmel maXTouch Touchpad']), 0)

  def testTouchscreen(self):
    self.mox.StubOutWithMock(file_utils, 'Read')
    file_utils.Read('/proc/bus/input/devices').AndReturn(SAMPLE_INPUT_DEVICES)
    self.mox.ReplayAll()
    self.assertEqual(sys_utils.GetI2CBus(['Atmel maXTouch Touchscreen']), 3)

  def testNoMatch(self):
    self.mox.StubOutWithMock(file_utils, 'Read')
    file_utils.Read('/proc/bus/input/devices').AndReturn(SAMPLE_INPUT_DEVICES)
    self.mox.ReplayAll()
    self.assertEqual(sys_utils.GetI2CBus(['Unknown Device']), None)

  def testNonI2CDevice(self):
    self.mox.StubOutWithMock(file_utils, 'Read')
    file_utils.Read('/proc/bus/input/devices').AndReturn(SAMPLE_INPUT_DEVICES)
    self.mox.ReplayAll()
    self.assertEqual(sys_utils.GetI2CBus(['Lid Switch']), None)


SAMPLE_PARTITIONS = """major minor  #blocks  name

   7        0     313564 loop0
 179        0   15388672 mmcblk0
 179        1   11036672 mmcblk0p1
 179        2      16384 mmcblk0p2
 179        3    2097152 mmcblk0p3
 179        4      16384 mmcblk0p4
 179        5    2097152 mmcblk0p5
 179        6          0 mmcblk0p6
 179        7          0 mmcblk0p7
 179        8      16384 mmcblk0p8
 179        9          0 mmcblk0p9
 179       10          0 mmcblk0p10
 179       11       8192 mmcblk0p11
 179       12      16384 mmcblk0p12
 179       32       4096 mmcblk0boot1
 179       16       4096 mmcblk0boot0
 254        0    1048576 dm-0
 254        1     313564 dm-1
 253        0    1953128 zram0"""

class GetPartitionsTest(unittest.TestCase):
  """Unit tests for GetInterrupts."""

  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.VerifyAll()
    self.mox.UnsetStubs()

  def testGetPartitions(self):
    self.mox.StubOutWithMock(file_utils, 'ReadLines')
    file_utils.ReadLines('/proc/partitions').AndReturn(
        SAMPLE_PARTITIONS.split('\n'))
    self.mox.ReplayAll()

    partitions = sys_utils.GetPartitions()
    for p in partitions:
      print unicode(p)


class MountDeviceAndReadFileTest(unittest.TestCase):
  """Unittest for MountDeviceAndReadFile."""
  def setUp(self):
    # Creates a temp file and create file system on it as a mock device.
    self.device = tempfile.NamedTemporaryFile(prefix='MountDeviceAndReadFile')
    Spawn(['truncate', '-s', '1M', self.device.name], log=True,
          check_call=True)
    Spawn(['/sbin/mkfs', '-F', '-t', 'ext3', self.device.name],
          log=True, check_call=True)

    # Creates a file with some content on the device.
    mount_point = tempfile.mkdtemp(prefix='MountDeviceAndReadFileSetup')
    Spawn(['mount', self.device.name, mount_point], sudo=True, check_call=True,
          log=True)
    self.content = 'file content'
    self.file_name = 'file'
    with open(os.path.join(mount_point, self.file_name), 'w') as f:
      f.write(self.content)
    Spawn(['umount', '-l', mount_point], sudo=True, check_call=True, log=True)

  def tearDown(self):
    self.device.close()

  def testMountDeviceAndReadFile(self):
    self.assertEqual(self.content,
        sys_utils.MountDeviceAndReadFile(self.device.name, self.file_name))

  def testMountDeviceAndReadFileWrongFile(self):
    with self.assertRaises(IOError):
      sys_utils.MountDeviceAndReadFile(self.device.name, 'no_file')

  def testMountDeviceAndReadFileWrongDevice(self):
    with self.assertRaises(Exception):
      sys_utils.MountDeviceAndReadFile('no_device', self.file_name)


if __name__ == "__main__":
  unittest.main()
