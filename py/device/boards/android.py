# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Android family boards."""

import pipes

from cros.factory.device.boards import linux
from cros.factory.device import device_types

# pylint: disable=abstract-method
class AndroidBoard(linux.LinuxBoard):
  """Common interface for Android boards."""

  TMPDIR = '/data/local/tmp'

  def Popen(self, command, stdin=None, stdout=None, stderr=None, cwd=None,
            log=False, encoding='utf-8'):
    # On Android, TMPDIR environment variable is only specified when
    # /system/etc/mkshrc was executed.  When we access to Android via ADBLink or
    # SSHLink ("adb shell" or "ssh host cmd"), ${TMPDIR} will be empty and
    # causing most tools, including mktemp, to fail. We have to always provide
    # the environment variable because programs invoked indirectly (for
    # instance, flashrom) may need TMPDIR.

    # To make sure TMPDIR is applied on all sub commands (for instance, "a; b"
    # or "(a; b)" we want to make sure the command is quoted before invocation.
    if not isinstance(command, str):
      command = ' '.join(pipes.quote(param) for param in command)

    command = ['TMPDIR=%s' % self.TMPDIR, 'sh', '-c', command]
    return super(AndroidBoard, self).Popen(
        command, stdin=stdin, stdout=stdout, stderr=stderr, cwd=cwd, log=log,
        encoding=encoding)

  @device_types.DeviceProperty
  def audio(self):
    from cros.factory.device.audio import utils as audio_utils
    return audio_utils.CreateAudioControl(
        self, controller=audio_utils.CONTROLLERS.TINYALSA)

  @device_types.DeviceProperty
  def memory(self):
    from cros.factory.device import memory
    return memory.AndroidMemory(self)

  @device_types.DeviceProperty
  def temp(self):
    from cros.factory.device import temp
    return temp.AndroidTemporaryFiles(self)

  @device_types.DeviceProperty
  def _RemotePath(self):
    from cros.factory.device import path
    return path.AndroidPath(self)

  @device_types.DeviceProperty
  def storage(self):
    from cros.factory.device import storage
    return storage.AndroidStorage(self)

  @device_types.DeviceProperty
  def vpd(self):
    from cros.factory.device import vpd
    return vpd.AndroidVitalProductData(self)
