# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Fixture connection interface and implementation.

FixtureConnection defines the interface for communicating with a fixture.
Currently the following kind of FixtureConnection is supported:

MockFixtureConnection: a fake FixtureConnection for testing purpose.
SerialFixtureConnection: a serial port based FixtureConnection.
"""

import abc
import time

import serial

from cros.factory.test.utils import serial_utils


class FixtureConnectionError(Exception):
  pass


class FixtureConnection(metaclass=abc.ABCMeta):
  """Abstract fixture connection."""

  @abc.abstractmethod
  def Connect(self):
    """Establishes the fixture connection.

    Raise:
      FixtureConnectionError
    """
    raise NotImplementedError

  @abc.abstractmethod
  def Disconnect(self):
    """Destroys the fixture connection.

    Raise:
      FixtureConnectionError
    """
    raise NotImplementedError

  @abc.abstractmethod
  def Send(self, msg, read_response=False):
    """Sends message to fixture.

    Args:
      msg: string or bytes to be sent to the fixture.
      read_response: whether to read response after sending the message.

    Raise:
      FixtureConnectionError
    """
    raise NotImplementedError

  @abc.abstractmethod
  def Recv(self, length=0):
    """Receives message from fixture.

    Args:
      length: length of characters to receive from fixture. If length == 0
              then Recv all available characters in the buffer.

    Raise:
      FixtureConnectionError
    """
    raise NotImplementedError


class MockFixtureConnection(FixtureConnection):
  """A fake FixtureConnection for simulation."""

  def __init__(self, script):
    """Constructor.

    Args:
      script: A dictionary containing the mapping of command and response.
    """
    super(MockFixtureConnection, self).__init__()

    self._script = script
    self._curr_cmd = None

  def Connect(self):
    pass

  def Disconnect(self):
    pass

  def Send(self, msg, read_response=False):
    self._curr_cmd = msg.strip()
    if read_response:
      return self.Recv()
    return None

  def Recv(self, length=0):
    if self._curr_cmd in self._script:
      return self._script[self._curr_cmd]
    raise FixtureConnectionError("Unexpected fixture command '%s'" %
                                 self._curr_cmd)


class SerialFixtureConnection(FixtureConnection):

  def __init__(self, driver, serial_delay, serial_params, response_delay,
               retries=5):
    """Constructor.

    Args:
      driver: name of the driver, e.g. pl2303
      serial_delay: delay time in seconds between writing each character to
          serial port
      serial_params: a dictionary containing the following keys:
          {
            'baudrate': 9600,
            'bytesize': 8,
            'parity': 'N',
            'stopbits': 1,
            'xonxoff': False,
            'rtscts': False,
            'timeout': None
          }
      response_delay: delay time in seconds before reading the response
      retries: number of retires when write failed
    """
    super(SerialFixtureConnection, self).__init__()

    self._tty = None
    self._driver = driver
    self._serial_delay = serial_delay
    self._serial_params = serial_params
    self._response_delay = response_delay
    self._retries = retries

  def Connect(self):
    port = serial_utils.FindTtyByDriver(self._driver)
    if not port:
      raise FixtureConnectionError('Cannot find TTY with driver %s' %
                                   self._driver)
    self._tty = serial_utils.OpenSerial(port=port, **self._serial_params)
    self._tty.flush()

  def Disconnect(self):
    self._tty.close()

  def Send(self, msg, read_response=False):
    for c in msg:
      retries = self._retries
      while True:
        try:
          self._tty.write(str(c))
          self._tty.flush()
          time.sleep(self._serial_delay)
        except serial.SerialTimeoutException as e:
          if retries <= 0:
            raise FixtureConnectionError(str(e))
          retries -= 1
        else:
          break

    time.sleep(self._response_delay)
    if read_response:
      return self.Recv()

  def Recv(self, length=0):
    if length:
      return self._tty.read(length)
    return self._tty.read(self._tty.inWaiting())
