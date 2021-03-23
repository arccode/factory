# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Basic linux specific interface."""


import logging
import posixpath  # Assume most linux devices will be running POSIX os.

from cros.factory.device import device_types
from cros.factory.utils import file_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils


DeviceProperty = device_types.DeviceProperty
Overrides = type_utils.Overrides


class LinuxBoard(device_types.DeviceBoard):

  @DeviceProperty
  def accelerometer(self):
    from cros.factory.device import accelerometer
    return accelerometer.Accelerometer(self)

  @DeviceProperty
  def ambient_light_sensor(self):
    from cros.factory.device import ambient_light_sensor
    return ambient_light_sensor.AmbientLightSensor(self)

  @DeviceProperty
  def audio(self):
    # Override this property in sub-classed boards to specify different audio
    # config path if required.
    from cros.factory.device.audio import utils as audio_utils
    return audio_utils.CreateAudioControl(self)

  @DeviceProperty
  def bluetooth(self):
    raise NotImplementedError

  @DeviceProperty
  def camera(self):
    from cros.factory.device import camera
    return camera.Camera(self)

  @DeviceProperty
  def display(self):
    raise NotImplementedError

  @DeviceProperty
  def ec(self):
    from cros.factory.device import ec
    return ec.EmbeddedController(self)

  @DeviceProperty
  def fan(self):
    raise NotImplementedError

  @DeviceProperty
  def gyroscope(self):
    from cros.factory.device import gyroscope
    return gyroscope.Gyroscope(self)

  @DeviceProperty
  def hwmon(self):
    from cros.factory.device import hwmon
    return hwmon.HardwareMonitor(self)

  @DeviceProperty
  def i2c(self):
    from cros.factory.device import i2c
    return i2c.I2CBus(self)

  @DeviceProperty
  def info(self):
    from cros.factory.device import info
    return info.SystemInfo(self)

  @DeviceProperty
  def init(self):
    from cros.factory.device import init
    return init.FactoryInit(self)

  @DeviceProperty
  def led(self):
    from cros.factory.device import led
    return led.LED(self)

  @DeviceProperty
  def magnetometer(self):
    from cros.factory.device import magnetometer
    return magnetometer.Magnetometer(self)

  @DeviceProperty
  def memory(self):
    from cros.factory.device import memory
    return memory.LinuxMemory(self)

  @DeviceProperty
  def partitions(self):
    """Returns the partition names of system boot disk."""
    from cros.factory.device import partitions
    return partitions.Partitions(self)

  @DeviceProperty
  def path(self):
    """Returns a module to handle path operations.

    If self.link.IsLocal() == True, then module posixpath is returned,
    otherwise, self._RemotePath is returned.
    If you only need to change the implementation of remote DUT, try to override
    _RemotePath.
    """
    if self.link.IsLocal():
      return posixpath
    return self._RemotePath

  @DeviceProperty
  def _RemotePath(self):
    """Returns a module to handle path operations on remote DUT.

    self.path will return this object if DUT is not local. Override this to
    change the implementation of remote DUT.
    """
    from cros.factory.device import path as path_module
    return path_module.Path(self)

  @DeviceProperty
  def power(self):
    from cros.factory.device import power
    return power.LinuxPower(self)

  @DeviceProperty
  def status(self):
    """Returns live system status (dynamic data like CPU loading)."""
    from cros.factory.device import status
    return status.SystemStatus(self)

  @DeviceProperty
  def storage(self):
    from cros.factory.device import storage
    return storage.Storage(self)

  @DeviceProperty
  def temp(self):
    from cros.factory.device import temp
    return temp.TemporaryFiles(self)

  @DeviceProperty
  def thermal(self):
    from cros.factory.device import thermal
    return thermal.Thermal(self)

  @DeviceProperty
  def touch(self):
    from cros.factory.device import touch
    return touch.Touch(self)

  @DeviceProperty
  def toybox(self):
    from cros.factory.device import toybox
    return toybox.Toybox(self)

  @DeviceProperty
  def udev(self):
    from cros.factory.device import udev
    return udev.LocalUdevMonitor(self)

  @DeviceProperty
  def usb_c(self):
    from cros.factory.device import usb_c
    return usb_c.USBTypeC(self)

  @DeviceProperty
  def vpd(self):
    raise NotImplementedError

  @DeviceProperty
  def vsync_sensor(self):
    from cros.factory.device import vsync_sensor
    return vsync_sensor.VSyncSensor(self)

  @DeviceProperty
  def wifi(self):
    from cros.factory.device import wifi
    return wifi.WiFi(self)

  @type_utils.Overrides
  def ReadFile(self, path, count=None, skip=None):
    """Returns file contents on target device.

    By default the "most-efficient" way of reading file will be used, which may
    not work for special files like device node or disk block file. Use
    ReadSpecialFile for those files instead.

    Meanwhile, if count or skip is specified, the file will also be fetched by
    ReadSpecialFile.

    Args:
      path: A string for file path on target device.
      count: Number of bytes to read. None to read whole file.
      skip: Number of bytes to skip before reading. None to read from beginning.

    Returns:
      A string as file contents.
    """
    if count is None and skip is None:
      return self.link.Pull(path)
    return self.ReadSpecialFile(path, count=count, skip=skip)

  @type_utils.Overrides
  def ReadSpecialFile(self, path, count=None, skip=None, encoding='utf-8'):
    """Returns contents of special file on target device.

    Reads special files (device node, disk block, or sys driver files) on device
    using the most portable approach.

    Args:
      path: A string for file path on target device.
      count: Number of bytes to read. None to read whole file.
      skip: Number of bytes to skip before reading. None to read from beginning.
      encoding: The encoding of the file content.

    Returns:
      A string or bytes as file contents.
    """
    if self.link.IsLocal():
      return super(LinuxBoard, self).ReadSpecialFile(path, count, skip,
                                                     encoding)

    args = ['dd', 'bs=1', 'if=%s' % path]
    if count is not None:
      args += ['count=%d' % count]
    if skip is not None:
      args += ['skip=%d' % skip]

    return self.CheckOutput(args)

  @type_utils.Overrides
  def WriteFile(self, path, content):
    """Writes some content into file on target device.

    Args:
      path: A string for file path on target device.
      content: A string to be written into file.
    """
    # If the link is local, we just open file and write content.
    if self.link.IsLocal():
      super(LinuxBoard, self).WriteFile(path, content)
      return

    with file_utils.UnopenedTemporaryFile() as temp_path:
      with open(temp_path, 'w') as f:
        f.write(content)
      self.link.Push(temp_path, path)

  @type_utils.Overrides
  def WriteSpecialFile(self, path, content):
    """Writes some content into a special file on target device.

    Args:
      path: A string for file path on target device.
      content: A string to be written into file.
    """
    # If the link is local, we just open file and write content.
    if self.link.IsLocal():
      super(LinuxBoard, self).WriteSpecialFile(path, content)
      return

    with file_utils.UnopenedTemporaryFile() as local_temp:
      with open(local_temp, 'w') as f:
        f.write(content)
      with self.temp.TempFile() as remote_temp:
        self.link.Push(local_temp, remote_temp)
        self.CheckOutput(['dd', 'if=%s' % remote_temp, 'of=%s' % path])

  @type_utils.Overrides
  def SendDirectory(self, local, remote):
    """Copies a local directory to target device.

    `local` should be a local directory, and `remote` should be a non-existing
    file path on target device.

    Example::

     dut.SendDirectory('/path/to/local/dir', '/remote/path/to/some_dir')

    Will create directory `some_dir` under `/remote/path/to` and copy
    files and directories under `/path/to/local/dir/` to `some_dir`.

    Args:
      local: A string for directory path in local.
      remote: A string for directory path on remote device.
    """
    return self.link.PushDirectory(local, remote)

  @type_utils.Overrides
  def SendFile(self, local, remote):
    """Copies a local file to target device.

    Args:
      local: A string for file path in local.
      remote: A string for file path on remote device.
    """
    return self.link.Push(local, remote)

  @type_utils.Overrides
  def Popen(self, command, stdin=None, stdout=None, stderr=None, cwd=None,
            log=False, encoding='utf-8'):
    """Executes a command on target device using subprocess.Popen convention.

    This function should be the single entry point for invoking link.Shell
    because boards that need customization to shell execution (for example,
    adding PATH or TMPDIR) will override this.

    Args:
      command: A string or a list of strings for command to execute.
      stdin: A file object to override standard input.
      stdout: A file object to override standard output.
      stderr: A file object to override standard error.
      cwd: The working directory for the command.
      log: True (for logging.info) or a logger object to keep logs before
          running the command.
      encoding: Same as subprocess.Popen, we will use `utf-8` as default to make
          it output str type.

    Returns:
      An object similar to subprocess.Popen (see link.Shell).
    """
    if log:
      logger = logging.info if log is True else log
      logger('%s Running: %r', type(self), command)
    return self.link.Shell(command, cwd=cwd, stdin=stdin, stdout=stdout,
                           stderr=stderr, encoding=encoding)

  @type_utils.Overrides
  def Glob(self, pattern):
    """Finds files on target device by pattern, similar to glob.glob.

    Args:
      pattern: A file path pattern (allows wild-card '*' and '?).

    Returns:
      A list of files matching pattern on target device.
    """
    if self.link.IsLocal():
      return super(LinuxBoard, self).Glob(pattern)

    results = self.CallOutput('ls -d %s' % pattern)
    return results.splitlines() if results else []

  @type_utils.Overrides
  def GetStartupMessages(self):
    res = {}
    try:
      # Grab /var/log/messages for context.
      var_log_message = sys_utils.GetVarLogMessagesBeforeReboot(dut=self)
      res['var_log_messages_before_reboot'] = var_log_message
    except Exception:
      logging.exception('Unable to grok /var/log/messages')

    # The console-ramoops file changed names with linux-3.19+.
    try:
      res['console_ramoops'] = file_utils.TailFile(
          '/sys/fs/pstore/console-ramoops-0', dut=self)
    except Exception:
      try:
        res['console_ramoops'] = file_utils.TailFile(
            '/sys/fs/pstore/console-ramoops', dut=self)
      except Exception:
        logging.debug('Error to retrieve console ramoops log '
                      '(This is normal for cold reboot).')

    try:
      res['i915_error_state'] = file_utils.TailFile(
          '/sys/kernel/debug/dri/0/i915_error_state', dut=self)
    except Exception:
      logging.debug('Error to retrieve i915 error state log '
                    '(This is normal on an non-Intel systems).')

    try:
      res['ec_console_log'] = self.ec.GetECConsoleLog()
    except Exception:
      logging.exception('Error retrieving EC console log')

    try:
      res['ec_panic_info'] = self.ec.GetECPanicInfo()
    except Exception:
      logging.exception('Error retrieving EC panic info')

    return res
