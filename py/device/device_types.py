# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Interfaces, classes and types for Device API."""

from cros.factory.utils import sys_interface
from cros.factory.utils import type_utils


# Default component property - using lazy loaded property implementation.
DeviceProperty = type_utils.LazyProperty
# TODO(hungte) Change DeviceProperty to also check if it has overridden an
# existing component; and NewDeviceProperty to declare new component.
Overrides = type_utils.Overrides

# Use sys_interface.CalledProcessError for invocation exceptions.
CalledProcessError = sys_interface.CalledProcessError


class DeviceException(Exception):
  """Common exception for all components."""


class DeviceLink:
  """An abstract class for connection to remote or local device."""

  def Push(self, local, remote):
    """Uploads a local file to target device.

    Args:
      local: A string for local file path.
      remote: A string for remote file path on device.
    """
    raise NotImplementedError

  def PushDirectory(self, local, remote):
    """Copies a local file to target device.

    `local` should be a local directory, and `remote` should be a non-existing
    file path on device.

    Example::

     PushDirectory('/path/to/local/dir', '/remote/path/to/some_dir')

    Will create directory `some_dir` under `/remote/path/to` and copy
    files and directories under `/path/to/local/dir/` to `some_dir`.

    Args:
      local: A string for directory path in local.
      remote: A string for directory path on remote device.
    """
    raise NotImplementedError

  def Pull(self, remote, local=None):
    """Downloads a file from target device to local.

    Args:
      remote: A string for file path on remote device.
      local: A string for local file path to receive downloaded content, or
             None to return the contents directly.

    Returns:
      If local is None, return a string as contents in remote file.
      Otherwise, do not return anything.
    """
    raise NotImplementedError

  def Shell(self, command, stdin=None, stdout=None, stderr=None, cwd=None,
            encoding='utf-8'):
    """Executes a command on device.

    The calling convention is similar to subprocess.Popen, but only a subset of
    parameters are supported due to platform limitation.

    Args:
      command: A string or a list of strings for command to execute.
      stdin: A file object to override standard input.
      stdout: A file object to override standard output.
      stderr: A file object to override standard error.
      cwd: The working directory for the command.
      encoding: Same as subprocess.Popen, we will use `utf-8` as default to make
          it output str type.

    Returns:
      An object representing the process, similar to subprocess.Popen.
    """
    raise NotImplementedError

  def IsReady(self):
    """Checks if device is ready for connection.

    Returns:
      A boolean indicating if target device is ready.
    """
    raise NotImplementedError

  def IsLocal(self):
    """Returns if the target device exactly the local machine.

    This is helpful for tests to decide if they can use Python native modules or
    need to invoke system commands.
    """
    return False

  @classmethod
  def PrepareLink(cls):
    """Setup prerequisites of device connections.

    Some device types need to do some setup before we can connect to.
    For example, we might need to start a DHCP server that assigns IP addresses
    to devices.
    """


class DeviceComponent:
  """A base class for system components available on device.

  All modules under cros.factory.device (and usually a property of
  DeviceInterface) should inherit from DeviceComponent.

  Example::

  class MyComponent(DeviceComponent):

    @DeviceProperty
    def controller(self):
      return MyController(self)

    def SomeFunction(self):
      return self._do_something()

  Attributes:
    _device: A cros.factory.device.device_types.DeviceInterface instance for
             accessing target device.
    _dut: A legacy alias for _device.
    Error: Exception type for raising unexpected errors.
  """

  Error = DeviceException

  def __init__(self, device):
    """Constructor of DeviceComponent.

    :type device: cros.factory.device.device_types.DeviceInterface
    """
    self._device = device
    # TODO(hungte) Remove the legacy reference _dut.
    self._dut = device


class DeviceInterface(sys_interface.SystemInterface):
  """Abstract interface for accessing a device.

  This class provides an interface for accessing a device, for example reading
  its keyboard, turn on display, forcing charge state, forcing fan speeds, and
  reading temperature sensors.

  To obtain a :py:class:`cros.factory.device.device_types.DeviceInterface`
  object for the device under test, use the
  :py:func:`cros.factory.device.device_utils.CreateDUTInterface` function.

  Implementations of this interface should be in the
  :py:mod:`cros.factory.device.boards` package. Most Chromebook projects will
  inherit from :py:class:`cros.factory.device.boards.chromeos.ChromeOSBoard`.

  In general, this class is only for functionality that may need to be
  implemented separately on a board-by-board basis.  If there is a
  standard system-level interface available for certain functionality
  (e.g., using a Python API, a binary available on all boards, or
  ``/sys``) then it should not be in this class, but rather wrapped in
  a class in the :py:mod:`cros.factory.test.utils` module, or in a utility
  method in :py:mod:`cros.factory.utils`.  See
  :ref:`board-api-extending`.

  All methods may raise a :py:class:`DeviceException` on failure, or a
  :py:class:`NotImplementedError` if not implemented for this board.

  Attributes:
    link: A cros.factory.device.device_types.DeviceLink instance for accessing
          device.
  """

  def __init__(self, link=None):
    """Constructor.

    Arg:
      link: A cros.factory.device.device_types.DeviceLink instance for accessing
            device.
    """
    super(DeviceInterface, self).__init__()
    self.link = link

  @DeviceProperty
  def accelerometer(self):
    """Sensor measures proper acceleration (also known as g-sensor)."""
    raise NotImplementedError

  @DeviceProperty
  def ambient_light_sensor(self):
    """Ambient light sensors."""
    raise NotImplementedError

  @DeviceProperty
  def audio(self):
    """Audio input and output, including headset, mic, and speakers."""
    raise NotImplementedError

  @DeviceProperty
  def bluetooth(self):
    """Interface to connect and control Bluetooth devices."""
    raise NotImplementedError

  @DeviceProperty
  def camera(self):
    """Interface to control camera devices."""
    raise NotImplementedError

  @DeviceProperty
  def display(self):
    """Interface for showing images or taking screenshot."""
    raise NotImplementedError

  @DeviceProperty
  def ec(self):
    """Module for controlling Embedded Controller."""
    raise NotImplementedError

  @DeviceProperty
  def fan(self):
    """Module for fan control."""
    raise NotImplementedError

  @DeviceProperty
  def gyroscope(self):
    """Gyroscope sensors."""
    raise NotImplementedError

  @DeviceProperty
  def hwmon(self):
    """Hardware monitor devices."""
    raise NotImplementedError

  @DeviceProperty
  def i2c(self):
    """Module for accessing to peripheral devices on I2C bus."""
    raise NotImplementedError

  @DeviceProperty
  def info(self):
    """Module for static information about the system."""
    raise NotImplementedError

  @DeviceProperty
  def init(self):
    """Module for adding / removing start-up jobs."""
    raise NotImplementedError

  @DeviceProperty
  def led(self):
    """Module for controlling LED."""
    raise NotImplementedError

  @DeviceProperty
  def magnetometer(self):
    """Magnetometer / Compass."""
    raise NotImplementedError

  @DeviceProperty
  def memory(self):
    """Module for memory information."""
    raise NotImplementedError

  @DeviceProperty
  def partitions(self):
    """Provide information of partitions on a device."""
    raise NotImplementedError

  @DeviceProperty
  def path(self):
    """Provides operations on path names, similar to os.path."""
    raise NotImplementedError

  @DeviceProperty
  def power(self):
    """Interface for reading and controlling battery."""
    raise NotImplementedError

  @DeviceProperty
  def status(self):
    """Returns live system status (dynamic data like CPU loading)."""
    raise NotImplementedError

  @DeviceProperty
  def storage(self):
    """Information of the persistent storage on device."""
    raise NotImplementedError

  @DeviceProperty
  def temp(self):
    """Provides access to temporary files and directories."""
    raise NotImplementedError

  @DeviceProperty
  def thermal(self):
    """System module for thermal control (temperature sensors, fans)."""
    raise NotImplementedError

  @DeviceProperty
  def touch(self):
    """Module for touch."""
    raise NotImplementedError

  @DeviceProperty
  def toybox(self):
    """A python wrapper for http://www.landley.net/toybox/."""
    raise NotImplementedError

  @DeviceProperty
  def udev(self):
    """Module for detecting udev event."""
    raise NotImplementedError

  @DeviceProperty
  def usb_c(self):
    """System module for USB type-C."""
    raise NotImplementedError

  @DeviceProperty
  def vpd(self):
    """Interface for read / write Vital Product Data (VPD)."""
    raise NotImplementedError

  @DeviceProperty
  def vsync_sensor(self):
    """Camera vertical sync sensors."""
    return NotImplementedError

  @DeviceProperty
  def wifi(self):
    """Interface for controlling WiFi devices."""
    raise NotImplementedError

  def GetStartupMessages(self):
    """Get various startup messages.

    This is usually useful for debugging issues like unexpected reboot during
    test.

    Returns: a dict that contains logs.
    """
    raise NotImplementedError

  def IsReady(self):
    """Returns True if a device is ready for access.

    This is usually simply forwarded to ``link.IsReady()``, but some devices may
    need its own readiness check in additional to link layer.
    """
    return self.link.IsReady()


# pylint:disable=abstract-method
class DeviceBoard(DeviceInterface):
  """A base class all for board implementations to inherit from."""
