#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for sys_util module."""

import mox
import unittest

import factory_common # pylint: disable=W0611
from cros.factory.utils import file_utils
from cros.factory.utils import sys_utils


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


if __name__ == "__main__":
  unittest.main()
