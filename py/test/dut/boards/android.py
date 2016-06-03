#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Android family boards."""

import pipes

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component
from cros.factory.test.dut import memory
from cros.factory.test.dut import path
from cros.factory.test.dut import storage
from cros.factory.test.dut import temp
from cros.factory.test.dut import thermal
from cros.factory.test.dut import vpd
from cros.factory.test.dut.boards import linux

# pylint: disable=abstract-method
class AndroidBoard(linux.LinuxBoard):
  """Common interface for Android boards."""

  TMPDIR = '/data/local/tmp'

  def Popen(self, command, stdin=None, stdout=None, stderr=None, log=False):
    # On Android, TMPDIR environment variable is only specified when
    # /system/etc/mkshrc was executed.  When we access to Android via ADBLink or
    # SSHLink ("adb shell" or "ssh host cmd"), ${TMPDIR} will be empty and
    # causing most tools, including mktemp, to fail. We have to always provide
    # the environment variable because programs invoked indirectly (for
    # instance, flashrom) may need TMPDIR.

    # To make sure TMPDIR is applied on all sub commands (for instance, "a; b"
    # or "(a; b)" we want to make sure the command is quoted before invocation.
    if not isinstance(command, basestring):
      command = ' '.join(pipes.quote(param) for param in command)

    command = ['TMPDIR=%s' % self.TMPDIR, 'sh', '-c', command]
    return super(AndroidBoard, self).Popen(command, stdin, stdout, stderr, log)

  @component.DUTProperty
  def memory(self):
    return memory.AndroidMemory(self)

  @component.DUTProperty
  def temp(self):
    return temp.AndroidTemporaryFiles(self)

  @component.DUTProperty
  def _RemotePath(self):
    return path.AndroidPath(self)

  @component.DUTProperty
  def storage(self):
    return storage.AndroidStorage(self)

  @component.DUTProperty
  def thermal(self):
    return thermal.SysFSThermal(self)

  @component.DUTProperty
  def vpd(self):
    return vpd.FileBasedVitalProductData(self, '/persist')
