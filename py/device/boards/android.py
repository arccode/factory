#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Android family boards."""

import pipes

import factory_common  # pylint: disable=W0611
from cros.factory.device.audio import utils as audio_utils
from cros.factory.device import component
from cros.factory.device import memory
from cros.factory.device import path
from cros.factory.device import storage
from cros.factory.device import temp
from cros.factory.device import thermal
from cros.factory.device import vpd
from cros.factory.device.boards import linux

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

  @component.DeviceProperty
  def audio(self):
    return audio_utils.CreateAudioControl(
        self, controller=audio_utils.CONTROLLERS.TINYALSA)

  @component.DeviceProperty
  def memory(self):
    return memory.AndroidMemory(self)

  @component.DeviceProperty
  def temp(self):
    return temp.AndroidTemporaryFiles(self)

  @component.DeviceProperty
  def _RemotePath(self):
    return path.AndroidPath(self)

  @component.DeviceProperty
  def storage(self):
    return storage.AndroidStorage(self)

  @component.DeviceProperty
  def thermal(self):
    return thermal.SysFSThermal(self)

  @component.DeviceProperty
  def vpd(self):
    return vpd.FileBasedVitalProductData(self, '/persist')
