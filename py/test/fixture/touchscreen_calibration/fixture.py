# -*- coding: utf-8 -*-
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import time

from collections import namedtuple

from cros.factory.test import factory
from cros.factory.test.serial_utils import FindTtyByDriver, SerialDevice


# Define the driver name and the interface protocols to find the arduino ports.
# NATIVE_USB_PORT:  used to monitor the internal state of test fixture.
# PROGRAMMING_PORT: used to upload the firmware from host to the arduino and
#                   issue calibration commands to control the test fixture.
NATIVE_USB_PORT = 0
PROGRAMMING_PORT = 1
ARDUINO_DRIVER = 'cdc_acm'
interface_protocol_dict = {NATIVE_USB_PORT: '00', PROGRAMMING_PORT: '01'}


ArduinoCommand = namedtuple('ArduinoCommand', ['DOWN', 'UP', 'STATE', 'RESET'])
COMMAND = ArduinoCommand('d', 'u', 's', 'r')

ArduinoState = namedtuple('ArduinoState',
                          ['INIT', 'STOP_DOWN', 'STOP_UP', 'GOING_DOWN',
                           'GOING_UP', 'EMERGENCY_STOP'])
STATE = ArduinoState('i', 'D', 'U', 'd', 'u', 'e')


class FixtureException(Exception):
  """A dummy exception class for FixutreSerialDevice."""
  pass


class FixutreNativeUSB(SerialDevice):
  """A native usb port used to monitor the internal state of the fixture."""

  def __init__(self, driver=ARDUINO_DRIVER,
               interface_protocol=interface_protocol_dict[NATIVE_USB_PORT],
               timeout=86400):
    super(FixutreNativeUSB, self).__init__()
    self.driver = driver
    self.interface_protocol = interface_protocol
    self.timeout = timeout

    self.port = self._GetPort()
    self._Connect(self.port)
    self.state_string = None
    self.last_state_string = None

    # The ordering of the state names should match that in
    # touchscreen_calibration.ino
    self.state_name_dict = [
        'state',
        'jumper',
        'button debug',
        'sensor extreme up',
        'sensor up',
        'sensor down',
        'sensor safety',
        'motor direction',
        'motor enabled',
        'motor locked',
        'motor duty cycle',
        'pwm frequency',
        'count',
    ]

  def _GetPort(self):
    return FindTtyByDriver(self.driver, self.interface_protocol)

  def _Connect(self, port):
    try:
      self.Connect(port=port, timeout=self.timeout)
      msg = 'Connect to native USB port "%s" for monitoring internal state.'
      factory.console.info(msg % port)
    except Exception:
      msg = 'FixtureNativeUSB: failed to connect to native usb port: %s'
      factory.console.warn(msg, port)

  def _CheckReconnection(self):
    """Reconnect the native usb port if it has been refreshed."""
    curr_port = self._GetPort()
    if curr_port != self.port:
      self.Disconnect()
      self._Connect(curr_port)
      self.port = curr_port
      factory.console.info('Reconnect to new port: %s', curr_port)

  def GetState(self):
    """Get the fixture state from the native usb port.

    The complete state_string looks like: <i1001000000.6000.0>
    Its format is defined in self.state_name_dict in __init__() above.
    The first character describes the main state.

    This call is blocked until a complete fixture state has been received.
    Call this method with a new thread if needed.
    """
    self._CheckReconnection()
    reply = []
    while True:
      ch = self.Receive()
      reply.append(ch)
      if ch == '>':
        self.last_state_string = self.state_string
        self.state_string = ''.join(reply)
        return self.state_string

  def QueryFixtureState(self):
    """Query fixture internal state."""
    self._CheckReconnection()
    self.Send('s')

  def _ExtractStateList(self, state_string):
    if state_string:
      state, pwm_freq, count = state_string.strip().strip('<>').split('.')
      state_list = [s for s in state]
      state_list.extend([pwm_freq, count])
    else:
      state_list = []
    return state_list

  def DiffState(self):
    """Get the difference of between this state and the last state."""
    old_state_list = self._ExtractStateList(self.last_state_string)
    new_state_list = self._ExtractStateList(self.state_string)
    return [(self.state_name_dict[i], new_state_list[i])
            for i in xrange(len(new_state_list))
            if old_state_list == [] or new_state_list[i] != old_state_list[i]]

  def CompleteState(self):
    """Get the complete state snap shot."""
    state_list = self._ExtractStateList(self.state_string)
    return [(self.state_name_dict[i], state_list[i])
            for i in xrange(len(state_list))]


class FixutreSerialDevice(SerialDevice):
  """A serial device to control touchscreen fixture."""

  def __init__(self, driver=ARDUINO_DRIVER,
               interface_protocol=interface_protocol_dict[PROGRAMMING_PORT],
               timeout=20):
    super(FixutreSerialDevice, self).__init__()
    try:
      port = FindTtyByDriver(driver, interface_protocol)
      self.Connect(port=port, timeout=timeout)
      msg = 'Connect to programming port "%s" for issuing commands.'
      factory.console.info(msg % port)
      factory.console.info('Wait up to %d seconds for arduino initialization.' %
                           timeout)
    except:
      raise FixtureException('Failed to connect the test fixture.')

    self.AssertStateWithTimeout([STATE.INIT, STATE.STOP_UP,
                                 STATE.EMERGENCY_STOP], timeout)

    # The 2nd-generation tst fixture has a native usb port.
    self.native_usb = FixutreNativeUSB()
    if not self.native_usb:
      raise FixtureException('Fail to connect the native usb port.')

  def QueryState(self):
    """Queries the state of the arduino board."""
    try:
      state = self.SendReceive(COMMAND.STATE)
    except Exception:
      raise FixtureException('QueryState failed.')

    return state

  def IsStateUp(self):
    """Checks if the fixture is in the INIT or STOP_UP state."""
    return (self.QueryState() in [STATE.INIT, STATE.STOP_UP])

  def IsEmergencyStop(self):
    """Checks if the fixture is in the EMERGENCY_STOP state."""
    return (self.QueryState() == STATE.EMERGENCY_STOP)

  def AssertStateWithTimeout(self, expected_states, timeout):
    """Assert the state with timeout."""
    while True:
      result, state = self._AssertState(expected_states)
      if result is True:
        factory.console.info('state: %s (expected)', state)
        return
      factory.console.info('state: %s (transient, probe still moving)', state)
      time.sleep(1)
      timeout -= 1
      if timeout == 0:
        break

    msg = 'AssertState failed: actual state: "%s", expected_states: "%s".'
    raise FixtureException(msg % (state, str(expected_states)))

  def _AssertState(self, expected_states):
    """Confirms that the arduino is in the specified state.

    It returns True if the actual state is in the expected states;
    otherwise, it returns the actual state.
    """
    if not isinstance(expected_states, list):
      expected_states = [expected_states]
    actual_state = self.QueryState()
    return (actual_state in expected_states, actual_state)

  def AssertState(self, expected_states):
    result, _ = self._AssertState(expected_states)
    if result is not True:
      msg = 'AssertState failed: actual state: "%s", expected_states: "%s".'
      raise FixtureException(msg % (result, str(expected_states)))

  def DriveProbeDown(self):
    """Drives the probe to the 'down' position."""
    try:
      response = self.SendReceive(COMMAND.DOWN)
      factory.console.info('Send COMMAND.DOWN(%s). Receive state(%s).' %
                           (COMMAND.DOWN, response))
    except Exception:
      raise FixtureException('DriveProbeDown failed.')

    self.AssertState(STATE.STOP_DOWN)

  def DriveProbeUp(self):
    """Drives the probe to the 'up' position."""
    try:
      response = self.SendReceive(COMMAND.UP)
      factory.console.info('Send COMMAND.UP(%s). Receive state(%s).' %
                           (COMMAND.UP, response))
    except Exception:
      raise FixtureException('DriveProbeUp failed.')

    self.AssertState(STATE.STOP_UP)
