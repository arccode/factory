#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import unittest

import factory_common # pylint: disable=W0611
from cros.factory.utils import file_utils
from cros.factory.test.pytests import interrupt


_SAMPLE_INTERRUPTS = """           CPU0       CPU1       CPU2       CPU3
  0:        124          0          0          0   IO-APIC-edge      timer
  1:         19        683          7         14   IO-APIC-edge      i8042
NMI:        612        631        661        401   Non-maskable interrupts
SPU:          0          0          0          0   Spurious interrupts"""


class ProcInterruptsTest(unittest.TestCase):

  def setUp(self):
    self._mox = mox.Mox()

  def tearDown(self):
    self._mox.VerifyAll()
    self._mox.UnsetStubs()

  def testGetCount(self):
    self._mox.StubOutWithMock(file_utils, 'ReadLines')
    file_utils.ReadLines('/proc/interrupts').AndReturn(
      _SAMPLE_INTERRUPTS.split('\n'))
    self._mox.ReplayAll()

    proc_int = interrupt.ProcInterrupts()
    # Digit-type interrupts:
    # The below three queries are for the same interrupt.
    self.assertEqual(proc_int.GetCount('0'), 124)
    self.assertEqual(proc_int.GetCount(0), 124)

    self.assertEqual(proc_int.GetCount(1), 19 + 683 + 7 + 14)

    # String-type interrupts:
    self.assertEqual(proc_int.GetCount('NMI'), 612 + 631 + 661 + 401)
    self.assertEqual(proc_int.GetCount('SPU'), 0)

    # Invalid interrupts:
    self.assertEqual(proc_int.GetCount('2'), -1)
    self.assertEqual(proc_int.GetCount('foobar'), -1)

  def testFailToReadProcInterrupts(self):
    self._mox.StubOutWithMock(file_utils, 'ReadLines')
    file_utils.ReadLines('/proc/interrupts').AndReturn(None)
    self._mox.ReplayAll()

    proc_int = interrupt.ProcInterrupts()
    self.assertEqual(proc_int.GetCount(0), -1)
    self.assertEqual(proc_int.GetCount('NMI'), -1)


if __name__ == "__main__":
  unittest.main()
