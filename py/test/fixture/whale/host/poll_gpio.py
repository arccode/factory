# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""GPIO polling utility.

Be warned that the interface of PollGpio is not thread-safe.
"""

import atexit
import logging
import os
import select
import socket
import time


# Ref: https://www.kernel.org/doc/Documentation/gpio/sysfs.txt
_GPIO_ROOT = '/sys/class/gpio'
_EXPORT_FILE = os.path.join(_GPIO_ROOT, 'export')
_UNEXPORT_FILE = os.path.join(_GPIO_ROOT, 'unexport')
_GPIO_PIN_PATTERN = os.path.join(_GPIO_ROOT, 'gpio%d')


class PollGpioError(Exception):
  """Exception class for PollGpio."""
  pass


class PollGpio(object):
  """Monitors the status of one GPIO input.

  Do not create PollGpio object directly. Use factory method
  PollGpio.GetInstance() to get a PollGpio object to use. Otherwise, it'd be
  problematic when two PollGpio objects controlling the same port.
  """
  # Mapping from GPIO port to (PollGpio instance, edge).
  _instances = dict()

  # Mapping edge values for /sys/class/gpio/gpioN/edge.
  _EDGE_VALUES = {
      'gpio_rising': 'rising',
      'gpio_falling': 'falling',
      'gpio_both': 'both'
  }

  @classmethod
  def GetInstance(cls, port, edge):
    """Constructs or returns an existing PollGpio object.

    Args:
      port: GPIO port.
      edge: Triggering edge in _EDGE_VALUES.

    Returns:
      PollGpio object for the port.
    """
    if port not in cls._instances:
      cls._instances[port] = (PollGpio(port, edge), edge)
    elif cls._instances[port][1] != edge:
      # It's possible to support different edge types for one GPIO by setting
      # edge='both' in sysfs. But it's impractical in real-world use case
      # because hardware design should already demand one specific edge type.
      raise PollGpioError('The gpio %d was assigned different edge' % port)
    return cls._instances[port][0]

  def __init__(self, port, edge):
    """Constructor.

    Args:
      port: GPIO port

    Attributes:
      _port: Same as argument 'port'.
      _edge: Same as argument 'edge'.
      _stop_sockets: Socket pair used to interrupt poll() syscall when
                     program exits.
      _poll_fd: Open file descriptor for gpio value file.

    Raises:
      PollGpioError
    """
    try:
      self._port = port
      self._edge = edge
      self._stop_sockets = socket.socketpair()
      self._poll_fd = None

      self._ExportSysfs()
      atexit.register(self._CleanUp)  # must release system resource
    except Exception as e:
      raise PollGpioError('Fail to __init__ GPIO %d: %s' % (self._port, e))

  def _CleanUp(self):
    """Aborts any blocking poll() syscall and unexports the sysfs interface."""
    try:
      logging.debug('PollGpio._CleanUp')
      self._stop_sockets[0].send('.')  # send a dummy char
      time.sleep(0.5)
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
    gpio_path = _GPIO_PIN_PATTERN % self._port
    if attribute:
      return os.path.join(gpio_path, attribute)
    else:
      return gpio_path

  def _ExportSysfs(self):
    """Exports GPIO sysfs interface."""
    logging.debug('export GPIO port %d', self._port)
    if not os.path.exists(self._GetSysfsPath()):
      with open(_EXPORT_FILE, 'w') as f:
        f.write(str(self._port))
    with open(self._GetSysfsPath('edge'), 'w') as f:
      f.write(self._EDGE_VALUES[self._edge])

  def _UnexportSysfs(self):
    """Unexports GPIO sysfs interface."""
    logging.debug('unexport GPIO port %d', self._port)
    with open(_UNEXPORT_FILE, 'w') as f:
      f.write(str(self._port))

  def _ReadValue(self):
    """Reads the current GPIO value."""
    with open(self._GetSysfsPath('value'), 'r') as f:
      return int(f.read().strip())

  def Poll(self, timeout_secs=0):
    """Waits for a GPIO port being edge triggered.

    This method may block up to 'timeout_secs' seconds.

    Args:
      timeout_secs: (int) polling timeout in seconds. 0 if no timeout.

    Returns:
      True if the GPIO port is edge triggered.
      False if timeout occurs or the operation is interrupted.

    Raises:
      PollGpioError
    """
    try:
      logging.debug('GpioPoll.Poll() starts waiting')
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
          if len(self._stop_sockets[1].recv(1)) > 0:
            logging.debug('poll() interrupted by socketpair')
            return False
      logging.debug('GpioPoll.Poll() finishes waiting')
    except Exception as e:
      raise PollGpioError('Fail to poll GPIO %d %s' % (self._port, e))
