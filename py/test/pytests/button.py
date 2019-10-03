# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests button functionality.

Description
-----------
This test verifies if a button is working properly by checking if its state is
changed per given instruction.

You can specify the button in different ways using the ``button_key_name``
argument:

=================== ============================================================
Key Name            Description
=================== ============================================================
``gpio:[-]NUM``     A GPIO button. ``NUM`` indicates GPIO number, and ``+/-``
                    indicates polarity (minus for active low, otherwise active
                    high).
``crossystem:NAME`` A ``crossystem`` value (1 or 0) that can be retrieved by
                    NAME.
``ectool:NAME``     A value for ``ectool gpioget`` to fetch.
``KEYNAME``         An ``evdev`` key name that can be read from ``/dev/input``.
                    Try to find the right name by running ``evtest``.
=================== ============================================================

Test Procedure
--------------
When started, the test will prompt operator to press and release given button N
times, and fail if not finished in given timeout.

Dependency
----------
Depends on the driver of specified button source: GPIO, ``crossystem``,
``ectool``, or ``evdev`` (which also needs ``/dev/input`` and ``evtest``).

Examples
--------
To test the recovery button 1 time in 30 seconds, add this in test list::

  {
    "pytest_name": "button",
    "args": {
      "button_key_name": "crossystem:recoverysw_cur"
    }
  }

To test volume down button (using ``evdev``) 3 times in 10 seconds::

  {
    "pytest_name": "button",
    "args": {
      "timeout_secs": 10,
      "button_key_name": "KEY_VOLUMEDOWN",
      "repeat_times": 3
    }
  }
"""

import logging
import time

from six.moves import xrange

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.external import evdev
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test import test_case
from cros.factory.test.utils import evdev_utils
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils

_DEFAULT_TIMEOUT = 30

_KEY_GPIO = 'gpio:'
_KEY_CROSSYSTEM = 'crossystem:'
_KEY_ECTOOL = 'ectool:'


class GenericButton(object):
  """Base class for buttons."""

  def __init__(self, dut):
    """Constructor.

    Args:
      dut: the DUT which this button belongs to.
    """
    self._dut = dut

  def IsPressed(self):
    """Returns True the button is pressed, otherwise False."""
    raise NotImplementedError


class EvtestButton(GenericButton):
  """Buttons can be probed by evtest using /dev/input/event*."""

  def __init__(self, dut, device_filter, name):
    """Constructor.

    Args:
      dut: the DUT which this button belongs to.
      device_filter: /dev/input/event ID or evdev name.
      name: A string as key name to be captured by evtest.
    """

    def dev_filter(dev):
      return (evdev.ecodes.__dict__[self._name] in
              dev.capabilities().get(evdev.ecodes.EV_KEY, []))

    super(EvtestButton, self).__init__(dut)
    self._name = name
    self._event_dev = evdev_utils.FindDevice(device_filter, dev_filter)

  def IsPressed(self):
    return self._dut.Call(['evtest', '--query', self._event_dev.fn, 'EV_KEY',
                           self._name]) != 0


class GpioButton(GenericButton):
  """GPIO-based buttons."""

  def __init__(self, dut, number, is_active_high):
    """Constructor.

    Args:
      dut: the DUT which this button belongs to.
      :type dut: cros.factory.device.types.DeviceInterface
      number: An integer for GPIO number.
      is_active_high: Boolean flag for polarity of GPIO ("active" = "pressed").
    """
    super(GpioButton, self).__init__(dut)
    gpio_base = '/sys/class/gpio'
    self._value_path = self._dut.path.join(gpio_base, 'gpio%d' % number,
                                           'value')
    if not self._dut.path.exists(self._value_path):
      self._dut.WriteFile(self._dut.path.join(gpio_base, 'export'),
                          '%d' % number)

    # Exporting new GPIO may cause device busy for a while.
    for unused_counter in xrange(5):
      try:
        self._dut.WriteFile(
            self._dut.path.join(gpio_base, 'gpio%d' % number, 'active_low'),
            '%d' % (0 if is_active_high else 1))
        break
      except Exception:
        time.sleep(0.1)

  def IsPressed(self):
    return int(self._dut.ReadSpecialFile(self._value_path)) == 1


class CrossystemButton(GenericButton):
  """A crossystem value that can be mapped as virtual button."""

  def __init__(self, dut, name):
    """Constructor.

    Args:
      dut: the DUT which this button belongs to.
      :type dut: cros.factory.device.types.DeviceInterface
      name: A string as crossystem parameter that outputs 1 or 0.
    """
    super(CrossystemButton, self).__init__(dut)
    self._name = name

  def IsPressed(self):
    return self._dut.Call(['crossystem', '%s?1' % self._name]) == 0


class ECToolButton(GenericButton):
  def __init__(self, dut, name, active_value):
    super(ECToolButton, self).__init__(dut)
    self._name = name
    self._active_value = active_value

  def IsPressed(self):
    output = self._dut.CallOutput(['ectool', 'gpioget', self._name])
    # output should be: GPIO <NAME> = <0 | 1>
    value = int(output.split('=')[1])
    return value == self._active_value


class ButtonTest(test_case.TestCase):
  """Button factory test."""
  ARGS = [
      Arg('timeout_secs', int, 'Timeout value for the test.',
          default=_DEFAULT_TIMEOUT),
      Arg('button_key_name', str, 'Button key name.'),
      Arg('device_filter', (int, str),
          'Event ID or name for evdev. None for auto probe.',
          default=None),
      Arg('repeat_times', int, 'Number of press/release cycles to test',
          default=1),
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP,
          default=None),
      Arg('bft_button_name', str, 'Button name for BFT fixture',
          default=None),
      i18n_arg_utils.I18nArg('button_name', 'The name of the button.')
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui.ToggleTemplateClass('font-large', True)

    if self.args.button_key_name.startswith(_KEY_GPIO):
      gpio_num = self.args.button_key_name[len(_KEY_GPIO):]
      self.button = GpioButton(self.dut, abs(int(gpio_num, 0)),
                               gpio_num.startswith('-'))
    elif self.args.button_key_name.startswith(_KEY_CROSSYSTEM):
      self.button = CrossystemButton(
          self.dut, self.args.button_key_name[len(_KEY_CROSSYSTEM):])
    elif self.args.button_key_name.startswith(_KEY_ECTOOL):
      gpio_name = self.args.button_key_name[len(_KEY_ECTOOL):]
      if gpio_name.startswith('-'):
        gpio_name = gpio_name[1:]
        active_value = 0
      else:
        active_value = 1

      self.button = ECToolButton(
          self.dut, gpio_name, active_value)
    else:
      self.button = EvtestButton(self.dut, self.args.device_filter,
                                 self.args.button_key_name)

    # Timestamps of starting, pressing, and releasing
    # [started, pressed, released, pressed, released, pressed, ...]
    self._action_timestamps = [time.time()]

    if self.args.bft_fixture:
      self._fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)
    else:
      self._fixture = None

    # Group checker for Testlog.
    self.group_checker = testlog.GroupParam(
        'button_wait', ['time_to_press', 'time_to_release'])

  def tearDown(self):
    timestamps = self._action_timestamps + [float('inf')]
    for release_index in xrange(2, len(timestamps), 2):
      time_to_press = (timestamps[release_index - 1] -
                       timestamps[release_index - 2])
      time_to_release = (timestamps[release_index] -
                         timestamps[release_index - 1])
      event_log.Log('button_wait_sec',
                    time_to_press_sec=time_to_press,
                    time_to_release_sec=time_to_release)
      with self.group_checker:
        testlog.LogParam('time_to_press', time_to_press)
        testlog.LogParam('time_to_release', time_to_release)
    if self._fixture:
      try:
        self._fixture.SimulateButtonRelease(self.args.bft_button_name)
      except Exception:
        logging.warning('failed to release button', exc_info=True)
      try:
        self._fixture.Disconnect()
      except Exception:
        logging.warning('disconnection failure', exc_info=True)

  def _PollForCondition(self, poll_method, condition_name):
    elapsed_time = time.time() - self._action_timestamps[0]
    sync_utils.PollForCondition(
        poll_method=poll_method,
        timeout_secs=self.args.timeout_secs - elapsed_time,
        condition_name=condition_name)
    self._action_timestamps.append(time.time())

  def runTest(self):
    self.ui.StartFailingCountdownTimer(self.args.timeout_secs)

    for done in xrange(self.args.repeat_times):
      if self.args.repeat_times == 1:
        label = _('Press the {name} button', name=self.args.button_name)
      else:
        label = _(
            'Press the {name} button ({count}/{total})',
            name=self.args.button_name,
            count=done,
            total=self.args.repeat_times)
      self.ui.SetState(label)

      if self._fixture:
        self._fixture.SimulateButtonPress(self.args.bft_button_name, 0)

      self._PollForCondition(self.button.IsPressed, 'WaitForPress')
      self.ui.SetState(_('Release the button'))

      if self._fixture:
        self._fixture.SimulateButtonRelease(self.args.bft_button_name)

      self._PollForCondition(lambda: not self.button.IsPressed(),
                             'WaitForRelease')
