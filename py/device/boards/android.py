# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Android family boards."""

import pipes

import factory_common  # pylint: disable=unused-import
from cros.factory.device.audio import utils as audio_utils
from cros.factory.device.boards import linux
from cros.factory.device import memory
from cros.factory.device import path
from cros.factory.device import storage
from cros.factory.device import temp
from cros.factory.device import types
from cros.factory.device import vpd

# pylint: disable=abstract-method
class AndroidBoard(linux.LinuxBoard):
  """Common interface for Android boards."""

  TMPDIR = '/data/local/tmp'

  def Popen(self, command, stdin=None, stdout=None, stderr=None, cwd=None,
            log=False):
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
    return super(AndroidBoard, self).Popen(
        command, stdin=stdin, stdout=stdout, stderr=stderr, cwd=cwd, log=log)

  @types.DeviceProperty
  def audio(self):
    return audio_utils.CreateAudioControl(
        self, controller=audio_utils.CONTROLLERS.TINYALSA)

  @types.DeviceProperty
  def memory(self):
    return memory.AndroidMemory(self)

  @types.DeviceProperty
  def temp(self):
    return temp.AndroidTemporaryFiles(self)

  @types.DeviceProperty
  def _RemotePath(self):
    return path.AndroidPath(self)

  @types.DeviceProperty
  def storage(self):
    return storage.AndroidStorage(self)

  @types.DeviceProperty
  def vpd(self):
    return vpd.AndroidVitalProductData(self)
