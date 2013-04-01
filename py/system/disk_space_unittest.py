#!/usr/bin/env python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import collections
import mox
import os
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.system import disk_space


FakeStatVFSResult = collections.namedtuple(
    'FakeStatVFSResult',
    ['f_bavail', 'f_blocks', 'f_favail', 'f_files'])


class DiskSpaceTest(unittest.TestCase):
  # pylint: disable=W0212
  def setUp(self):
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(disk_space, '_Open')
    self.mox.StubOutWithMock(os, 'statvfs')

    self.stateful_stats = FakeStatVFSResult(f_blocks=261305, f_bavail=60457,
                                            f_files=65536, f_favail=35168)
    self.tmp_stats = FakeStatVFSResult(f_blocks=497739, f_bavail=497699,
                                       f_files=497739, f_favail=497698)

    disk_space._Open('/etc/mtab').AndReturn([
        '/dev/sda1 /mnt/stateful_partition ext4 rw\n',
        '/dev/sda1 /home ext4 rw\n',
        'tmp /tmp tmpfs rw\n',
        'fusectl /sys/fs/fuse/connections fusectl rw\n'
        ])

    os.statvfs('/mnt/stateful_partition').AndReturn(self.stateful_stats)
    os.statvfs('/tmp').AndReturn(self.tmp_stats)

    self.mox.ReplayAll()

  def tearDown(self):
    self.mox.VerifyAll()
    self.mox.UnsetStubs()

  def testGetAllVFSInfo(self):
    self.assertEqual(
        {'tmp': disk_space.VFSInfo(['/tmp'], self.tmp_stats),
         '/dev/sda1': disk_space.VFSInfo(['/home', '/mnt/stateful_partition'],
                                         self.stateful_stats)},
        disk_space.GetAllVFSInfo())

  def testFormatSpaceUsed(self):
    self.assertEqual(
        ('Disk space used (bytes%/inodes%): '
         '[/home /mnt/stateful_partition: 76%/46%] [/tmp: 0%/0%]'),
        disk_space.FormatSpaceUsedAll(
            disk_space.GetAllVFSInfo()))


if __name__ == '__main__':
  unittest.main()
