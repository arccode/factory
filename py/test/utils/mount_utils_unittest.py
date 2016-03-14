#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for mount_utils."""

import mock
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import dut
from cros.factory.test.utils.mount_utils import Mount


class MountUtilTest(unittest.TestCase):
  def setUp(self):
    self.dut = dut.Create()

  def testMount(self):
    source = '/dev/sda'
    target = '/tmp/mnt'

    self.dut.CheckCall = mock.MagicMock()
    with Mount(self.dut, source, target):
      self.dut.CheckCall.assert_called_with(['toybox', 'mount',
                                             source, target])
    self.dut.CheckCall.assert_called_with(['toybox', 'umount', target])

  def testMountWithOptions(self):
    source = '/dev/sda'
    target = '/tmp/mnt'
    options = 'remount,rw'
    types = 'ext2'

    self.dut.CheckCall = mock.MagicMock()
    with Mount(self.dut, source, target, options=options, types=types):
      self.dut.CheckCall.assert_called_with(['toybox', 'mount',
                                             '-t', '%s' % types,
                                             '-o', '%s' % options,
                                             source, target])
    self.dut.CheckCall.assert_called_with(['toybox', 'umount', target])


if __name__ == '__main__':
  unittest.main()
