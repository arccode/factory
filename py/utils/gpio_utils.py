# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""GPIO monitor and control utility.

Provides interface of GPIO management either locally or remotely via polld
(src/third_party/hdctools/polld). Be warned that the interface of gpio polling
is not thread-safe.

Usage:

>> # Generates a GpioManager instance. Make sure polld is running if using
>> # remote server.
>> g = gpio_utils.GpioManager(use_polld=<True: use remote server polld,
>>                                       False: use locally>,
>>                            host=<remote server host>,
>>                            tcp_port=<remote server port>,
>>                            verbose=<verbose>)

>> # Call method Poll to poll gpio status, or Read to read gpio value, or Write
>> # to write gpio value. (Note: WriteGPIO will set gpio direction to output
>> # mode)
>> poll_result = g.Poll(port=<number, ex. 7 for '/sys/class/gpio7'>,
>>                      edge=<'gpio_rising', 'gpio_falling', 'gpio_both'>,
>>                      timeout_secs=<polling timeout seconds>)
>> # True if gpio is triggered with specified edge, False if timeout.
>> read_value = g.Read(port=<number, ex. 7 for '/sys/class/gpio7'>)
>> # 1 for gpio high, 0 for low.
>> g.Write(port=<number, ex. 7 for '/sys/class/gpio7'>, value=<1, 0>)
"""

import logging
import os
import select
import socket
import sys
import time

from . import net_utils
from . import sync_utils
from . import type_utils


class GpioManagerError(Exception):
  """Exception class for GpioManager."""


class GpioManager:
  """GPIO monitor and control manager."""

  GPIO_EDGE_RISING = 'gpio_rising'
  GPIO_EDGE_FALLING = 'gpio_falling'
  GPIO_EDGE_BOTH = 'gpio_both'
  GPIO_EDGE_LIST = [GPIO_EDGE_RISING, GPIO_EDGE_FALLING, GPIO_EDGE_BOTH]

  def __init__(self, use_polld, host=None, tcp_port=None, timeout=10,
               verbose=False):
    """Constructor.

    Args:
      use_polld: True to use polld to manage GPIO on remote server, or False
                 to manage local GPIO port directly.
      host: Name or IP address of servo server host.
      tcp_port: TCP port on which servod is listening on.
      timeout: Timeout for HTTP connection.
      verbose: Enables verbose messaging across xmlrpclib.ServerProxy.
    """
    self._use_polld = use_polld
    self._server = None
    if use_polld:
      remote = 'http://%s:%s' % (host, tcp_port)
      self._server = net_utils.TimeoutXMLRPCServerProxy(
          remote, timeout=timeout, verbose=verbose)

  def Poll(self, port, edge, timeout_secs=None):
    """Polls a GPIO port.

    Args:
      port: An integer as the port number of target GPIO.
      edge: value in GPIO_EDGE_LIST
      timeout_secs: (int) polling timeout in seconds.

    Returns:
      True if the GPIO port is edge triggered.
      False if timeout occurs.

    Raises:
      GpioManagerError: If error occurs when polling the GPIO port.
    """
    if edge not in self.GPIO_EDGE_LIST:
      raise GpioManagerError(
          'Invalid edge %r. Valid values: %r' % (edge, self.GPIO_EDGE_LIST))

    try:
      if self._use_polld:
        try:
          # TODO: Interrupting HTTP requests with Timeout() is problematic.
          #       Use with caution!
          with sync_utils.Timeout(timeout_secs):
            self._server.poll_gpio(port, edge)
            return True
        except type_utils.TimeoutError:
          return False
      else:
        # Use with statement to make sure releasing system resource
        with Gpio(port) as gpio:
          return gpio.Poll(edge, timeout_secs)
    except Exception as e:
      exception_name = sys.exc_info()[0].__name__
      raise GpioManagerError('Problem to poll GPIO %s %s: %s(%s)' %
                             (str(port), edge, exception_name, str(e)))

  def Read(self, port):
    """Reads data from GPIO by given port.

    Args:
      port: An integer as the port number of target GPIO.

    Returns:
      (int) 1 if GPIO high; 0 for low.

    Raises:
      GpioManagerError: If error occurs when reading GPIO port.
    """
    try:
      if self._use_polld:
        return self._server.read_gpio(port)
      # Use with statement to make sure releasing system resource
      with Gpio(port) as gpio:
        return gpio.Read()
    except Exception as e:
      exception_name = sys.exc_info()[0].__name__
      raise GpioManagerError('Problem to read GPIO %s: %s(%s)' %
                             (str(port), exception_name, str(e)))

  def Write(self, port, value):
    """Writes data to GPIO by given port.

    Be aware that writing action will set GPIO direction to output mode.

    Args:
      port: An integer as the port number of target GPIO.
      value: An integer to be written into GPIO. Non-zero will all be
          converted as 1 (GPIO high).

    Raises:
      GpioManagerError: If error occurs when writing GPIO port.
    """
    try:
      if self._use_polld:
        self._server.write_gpio(port, value)
      else:
        # Use with statement to make sure releasing system resource
        with Gpio(port) as gpio:
          gpio.Write(1 if value else 0)
    except Exception as e:
      exception_name = sys.exc_info()[0].__name__
      raise GpioManagerError('Problem to write GPIO %s: %s(%s)' %
                             (str(port), exception_name, str(e)))


class GpioError(Exception):
  """Exception class for Gpio."""


class Gpio:
  """Monitors and controls the status of one GPIO port.

  Usage:
    >> # Create a Gpio instance using 'with' statement
    >> with Gpio(<gpio_port>) as gpio:
    >>   [do something for gpio_port]
  """
  # Mapping edge values for /sys/class/gpio/gpioN/edge.
  _EDGE_VALUES = {
      'gpio_rising': 'rising',
      'gpio_falling': 'falling',
      'gpio_both': 'both'
  }

  # Ref: https://www.kernel.org/doc/Documentation/gpio/sysfs.txt
  _GPIO_ROOT = '/sys/class/gpio'
  _EXPORT_FILE = os.path.join(_GPIO_ROOT, 'export')
  _UNEXPORT_FILE = os.path.join(_GPIO_ROOT, 'unexport')
  _GPIO_PIN_PATTERN = os.path.join(_GPIO_ROOT, 'gpio%d')

  def __init__(self, port):
    """Constructor.

    Args:
      port: An integer as the port number of target GPIO.

    Attributes:
      _port: Same as argument 'port'.
      _stop_sockets: Socket pair used to interrupt poll() syscall when
                     program exits.
      _poll_fd: Open file descriptor for gpio value file.

    Raises:
      GpioError
    """
    self._port = port
    self._stop_sockets = socket.socketpair()
    self._poll_fd = None

  def __enter__(self):
    self._ExportSysfs()
    return self

  def __exit__(self, exc_type, value, traceback):
    self._CleanUp()

  def _CleanUp(self):
    """Aborts any blocking poll() syscall and unexports the sysfs interface."""
    try:
      logging.debug('Gpio._CleanUp')
      self._stop_sockets[0].send('.')  # send a dummy char
      time.sleep(0.5)
      if self._poll_fd:
        self._poll_fd.close()
      self._UnexportSysfs()
    except Exception as e:
      logging.error('Fail to clean up GPIO %d: %s', self._port, e)

  def _GetSysfsPath(self, attribute=None):
    """Gets the path of GPIO sysfs interface.

    Args:
      attribute: Optional read/write attribute.

    Returns:
      The corresponding full sysfs path.
    """
    gpio_path = self._GPIO_PIN_PATTERN % self._port
    if attribute:
      return os.path.join(gpio_path, attribute)
    return gpio_path

  def _ExportSysfs(self):
    """Exports GPIO sysfs interface."""
    logging.debug('export GPIO port %d', self._port)
    if not os.path.exists(self._GetSysfsPath()):
      with open(self._EXPORT_FILE, 'w') as f:
        f.write(str(self._port))

  def _UnexportSysfs(self):
    """Unexports GPIO sysfs interface."""
    logging.debug('unexport GPIO port %d', self._port)
    with open(self._UNEXPORT_FILE, 'w') as f:
      f.write(str(self._port))

  def _AssignEdge(self, edge):
    """Writes edge value to GPIO sysfs interface.

    Args:
      edge: value in _EDGE_VALUES.
    """
    # for poll action, write edge value to /sys/class/gpio/gpioN/edge.
    with open(self._GetSysfsPath('edge'), 'w') as f:
      f.write(self._EDGE_VALUES[edge])

  def _ReadValue(self):
    """Reads the current GPIO value.

    Returns:
      GPIO value. 1 for high and 0 for low.
    """
    with open(self._GetSysfsPath('value'), 'r') as f:
      return int(f.read().strip())

  def _WriteValue(self, value):
    """Writes the GPIO value.

    Args:
      value: GPIO value. 1 for high and 0 for low.
    """
    # set gpio direction to output mode
    with open(self._GetSysfsPath('direction'), 'w') as f:
      f.write('out')
    with open(self._GetSysfsPath('value'), 'w') as f:
      f.write(str(value))

  def Poll(self, edge, timeout_secs=0):
    """Waits for a GPIO port being edge triggered.

    This method may block up to 'timeout_secs' seconds.

    Args:
      timeout_secs: (int) polling timeout in seconds. 0 if no timeout.

    Returns:
      True if the GPIO port is edge triggered.
      False if timeout occurs or the operation is interrupted.

    Raises:
      GpioError
    """
    try:
      logging.debug('Gpio.Poll() assigns edge: %s', edge)
      self._AssignEdge(edge)
    except Exception as e:
      raise GpioError('Fail to assign edge to GPIO %d %s' % (self._port, e))

    try:
      logging.debug('Gpio.Poll() starts waiting')
      if not self._poll_fd:
        self._poll_fd = open(self._GetSysfsPath('value'), 'r')

      poll = select.poll()
      # Poll for POLLPRI and POLLERR of 'value' file according to
      # https://www.kernel.org/doc/Documentation/gpio/sysfs.txt.
      poll.register(self._poll_fd, select.POLLPRI | select.POLLERR)
      poll.register(self._stop_sockets[1], select.POLLIN | select.POLLERR)
      logging.debug('poll()-ing on gpio %d for %r seconds',
                    self._port, timeout_secs)
      # After edge is triggered, re-read from head of 'gpio[N]/value'.
      # Or poll() will return immediately next time.
      self._poll_fd.seek(0)
      self._poll_fd.read()
      ret = poll.poll(timeout_secs * 1000 if timeout_secs > 0 else None)
      logging.debug('poll() on gpio %d returns %r', self._port, ret)
      if not ret:
        return False  # timeout
      for fd, _ in ret:
        if fd == self._poll_fd.fileno():
          return True
        if fd == self._stop_sockets[1].fileno():
          if self._stop_sockets[1].recv(1):
            logging.debug('poll() interrupted by socketpair')
            return False
      logging.debug('Gpio.Poll() finishes waiting')
      return False
    except Exception as e:
      raise GpioError('Fail to poll GPIO %d %s' % (self._port, e))

  def Read(self):
    """Reads current GPIO port value.

    Returns:
      1 for GPIO high; 0 for low.

    Raises:
      GpioError
    """
    try:
      logging.debug('Gpio.Read() starts')
      return self._ReadValue()
    except Exception as e:
      raise GpioError('Fail to read GPIO %d %s' % (self._port, e))

  def Write(self, value):
    """Writes GPIO port value.

    Be aware that writing action will set GPIO direction to output mode.

    Args:
      value: GPIO value 1 for high and 0 for low.

    Raises:
      GpioError
    """
    try:
      logging.debug('Gpio.Write() starts')
      self._WriteValue(value)
    except Exception as e:
      raise GpioError(
          'Fail to write %d to GPIO %d %s' % (value, self._port, e))
