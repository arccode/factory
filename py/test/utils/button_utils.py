# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import time

from cros.factory.test.utils import evdev_utils

from cros.factory.external import evdev


_KEY_GPIO = 'gpio:'
_KEY_CROSSYSTEM = 'crossystem:'
_KEY_ECTOOL = 'ectool:'


class GenericButton:
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
      return (evdev.ecodes.__dict__[self._name] in dev.capabilities().get(
          evdev.ecodes.EV_KEY, []))

    super(EvtestButton, self).__init__(dut)
    self._name = name
    self._event_dev = evdev_utils.FindDevice(device_filter, dev_filter)

  def IsPressed(self):
    return self._dut.Call(
        ['evtest', '--query', self._event_dev.fn, 'EV_KEY', self._name]) != 0


class GpioButton(GenericButton):
  """GPIO-based buttons."""

  def __init__(self, dut, number, is_active_high):
    """Constructor.

    Args:
      dut: the DUT which this button belongs to.
      :type dut: cros.factory.device.device_types.DeviceInterface
      number: An integer for GPIO number.
      is_active_high: Boolean flag for polarity of GPIO ("active" = "pressed").
    """
    super(GpioButton, self).__init__(dut)
    gpio_base = '/sys/class/gpio'
    self._value_path = self._dut.path.join(gpio_base, 'gpio%d' % number,
                                           'value')
    if not self._dut.path.exists(self._value_path):
      self._dut.WriteFile(
          self._dut.path.join(gpio_base, 'export'), '%d' % number)

    # Exporting new GPIO may cause device busy for a while.
    for unused_counter in range(5):
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
      :type dut: cros.factory.device.device_types.DeviceInterface
      name: A string as crossystem parameter that outputs 1 or 0.
    """
    super(CrossystemButton, self).__init__(dut)
    self._name = name

  def IsPressed(self):
    return self._dut.Call(['crossystem', '%s?1' % self._name]) == 0


class ECToolButton(GenericButton):
  """Buttons can be checked by ectool."""

  def __init__(self, dut, name, active_value):
    """Constructor.

    Args:
      dut: the DUT which this button belongs to.
      :type dut: cros.factory.device.device_types.DeviceInterface
      name: A string as button name.
      active_value: An int indicates the active value.
    """
    super(ECToolButton, self).__init__(dut)
    self._name = name
    self._active_value = active_value

  def IsPressed(self):
    output = self._dut.CallOutput(['ectool', 'gpioget', self._name])
    # output should be: GPIO <NAME> = <0 | 1>
    value = int(output.split('=')[1])
    return value == self._active_value


def Button(dut, button_key_name, device_filter):
  """Get button interface.

  Args:
    dut: A cros.factory.device.device_types.DeviceInterface instance.
    button_key_name: Button key name. We support four kinds of name which are
        corresponding to different control method. Please refer to the document
        in "py/test/pytests/button.py".
    device_filter: Event ID or name for evdev. None for auto probe.

  Returns:
    A GenericButton instance that supports `IsPressed` method to check if the
    button is pressed.
  """
  if button_key_name.startswith(_KEY_GPIO):
    gpio_num = button_key_name[len(_KEY_GPIO):]
    return GpioButton(dut, abs(int(gpio_num, 0)), gpio_num.startswith('-'))

  if button_key_name.startswith(_KEY_CROSSYSTEM):
    return CrossystemButton(dut, button_key_name[len(_KEY_CROSSYSTEM):])

  if button_key_name.startswith(_KEY_ECTOOL):
    gpio_name = button_key_name[len(_KEY_ECTOOL):]
    if gpio_name.startswith('-'):
      gpio_name = gpio_name[1:]
      active_value = 0
    else:
      active_value = 1

    return ECToolButton(dut, gpio_name, active_value)

  return EvtestButton(dut, device_filter, button_key_name)
