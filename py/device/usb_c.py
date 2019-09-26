# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import re

from six import iteritems

import factory_common  # pylint: disable=unused-import
from cros.factory.device import types


class USBTypeC(types.DeviceComponent):
  """System module for USB type-C.

  System module for controlling or monitoring USB type-C port.
  A USB type-C port may include the following functions:
  * DP (DisplayPort): Mode when connected to an external display.
  * PD (Power Delivery):
    * Sink: Mode when connected to a charging adapter.
    * Source: Mode when charging other devices.
  * USB: Normal host and device mode.
  """

  # EC tool arguments for accessing PD. Subclass may override this to match the
  # arguments used on the actual board. For example, boards with separate PD
  # like samus=Pixel2015), this should be ['--interface=dev', '--dev=1'].
  ECTOOL_PD_ARGS = []

  # Available functions for an USB type-C port.
  PORT_FUNCTION = {'dp', 'usb', 'sink', 'source'}

  # USB PD info.
  USB_PD_INFO_RE_ALL = {
      'USB_PD_INFO_RE_V0':
          re.compile(
              r'Port C(?P<port>\d+) is (?P<enabled>enabled|disabled), '
              r'Role:(?P<role>SRC|SNK) Polarity:(?P<polarity>CC1|CC2) '
              r'State:(?P<state>\d+)'),
      'USB_PD_INFO_RE_V1':
          re.compile(
              r'Port C(?P<port>\d+) is (?P<enabled>enabled|disabled), '
              r'Role:(?P<role>SRC|SNK) (?P<datarole>DFP|UFP) '
              r'Polarity:(?P<polarity>CC1|CC2) State:(?P<state>\w*)'),
      'USB_PD_INFO_RE_V1_1':
          re.compile(
              r'Port C(?P<port>\d+) is (?P<enabled>enabled|disabled),'
              r'(?P<connected>connected|disconnected), '
              r'Role:(?P<role>SRC|SNK) (?P<datarole>DFP|UFP) '
              r'Polarity:(?P<polarity>CC1|CC2) State:(?P<state>\w*)'),
      'USB_PD_INFO_RE_V1_2':
          re.compile(
              r'Port C(?P<port>\d+): (?P<enabled>enabled|disabled), '
              r'(?P<connected>connected|disconnected)  State:(?P<state>\w*)\n'
              r'Role:(?P<role>SRC|SNK) (?P<datarole>DFP|UFP) *(?P<vconn>VCONN|)'
              r', Polarity:(?P<polarity>CC1|CC2)'),
  }

  # USB PD Power info.
  # Known it from ectool source code(ectool.c print_pd_power_info function).
  # According to the code, it won't have voltage information when role is 'SRC'
  # or 'Disconnected'.
  USB_PD_POWER_INFO_SKIP_ROLE_RE = re.compile(
      r'Port (?P<port>\d+): (?P<role>Disconnected|SRC)')

  USB_PD_POWER_INFO_RE = re.compile(
      r'Port (?P<port>\d+): (?P<role>.*) (Charger|DRP) (?P<type>.*) '
      r'(?P<millivolt>\d+)mV / (?P<milliampere>\d+)mA, '
      r'max (?P<max_millivolt>\d+)mV / (?P<max_milliampere>\d+)mA'
      r'( / (?P<max_milliwatt>\d+)mW)?')

  def GetPDVersion(self):
    """Gets the PD firmware version.

    Returns:
      A string of the PD firmware version.
    """
    return (self._device.CallOutput(
        ['mosys', 'pd', 'info', '-s', 'fw_version']) or '').strip()

  def GetPDGPIOValue(self, gpio_name):
    """Gets PD GPIO value.

    Args:
      gpio_name: GPIO name.

    Returns:
      Return 1 if GPIO is high; otherwise 0.

    """
    gpio_info_re = re.compile(r'^GPIO %s = (\d)' % gpio_name)
    response = self._CallPD(['gpioget', gpio_name])
    gpio_value = gpio_info_re.findall(response)
    if gpio_value:
      return int(gpio_value[0])
    else:
      raise self.Error('Fail to get GPIO %s value' % gpio_name)

  def GetPDStatus(self, port):
    """Gets the USB PD status.

    Args:
      port: The USB port number.

    Returns:
      A dict that contains the following fields:

        'enabled': True or False
        'role': 'SNK' or 'SRC'
        'polarity': 'CC1' or 'CC2'
        'state': <state>
    """
    response = self._CallPD(['usbpd', '%d' % port])
    for pd_version, re_pattern in iteritems(self.USB_PD_INFO_RE_ALL):
      match = re_pattern.match(response)
      if match:
        status = dict(
            enabled=match.group('enabled') == 'enabled',
            role=match.group('role'),
            polarity=match.group('polarity'))
        if pd_version == 'USB_PD_INFO_RE_V0':
          status['state'] = int(match.group('state'))
        else:
          status['state'] = match.group('state')
          status['datarole'] = match.group('datarole')
          if (pd_version == 'USB_PD_INFO_RE_V1_1' or
              pd_version == 'USB_PD_INFO_RE_V1_2'):
            status['connected'] = match.group('connected') == 'connected'
            if pd_version == 'USB_PD_INFO_RE_V1_2':
              status['vconn'] = match.group('vconn')
        return status
    raise self.Error('Unable to parse USB PD status from: %s' % response)

  def GetPDPowerStatus(self):
    """Get USB PD Power Status
    The function will call 'ectool usbpdpower' to get the status and transform
    it to a dict.

    Returns:
      A dict for all ports' power status.
      Key is port number(int). Value is also a dict that contains the port's
      status.
    """
    status = {}
    response = self._device.CheckOutput(
        ['ectool'] + self.ECTOOL_PD_ARGS + ['usbpdpower'])
    for line in response.splitlines():
      port_status = {}
      match = self.USB_PD_POWER_INFO_SKIP_ROLE_RE.match(line)
      if match:
        port_status['role'] = match.group('role')
        status[int(match.group('port'))] = port_status
        continue
      match = self.USB_PD_POWER_INFO_RE.match(line)
      if not match:
        raise self.Error('Unable to parse USB Power status from: %s' % line)
      status[int(match.group('port'))] = port_status
      port_status['role'] = match.group('role')
      port_status['type'] = match.group('type')
      port_status['millivolt'] = int(match.group('millivolt'))
      port_status['milliampere'] = int(match.group('milliampere'))
      port_status['max_millivolt'] = int(match.group('max_millivolt'))
      port_status['max_milliampere'] = int(match.group('max_milliampere'))
      max_milliwatt = match.group('max_milliwatt')
      port_status['max_milliwatt'] = int(max_milliwatt) if max_milliwatt else 0

    return status

  def SetHPD(self, port):
    """Manually pulls up DP HPD (Hot Plug Detection) GPIO.
    This pin is used for detecting plugging of external display. Manually pulls
    up it can be used for triggering events for testing.

    Args:
      port: The USB port number.
    """
    # Pull-up HPD GPIO
    self._CallPD(['gpioset', 'USB_C%d_DP_HPD' % port, '1'])

  def ResetHPD(self, port):
    """Manually pulls down DP HPD (Hot Plug Detection) GPIO.
    This pin is used for detecting plugging of external display. Manually pulls
    up it can be used for triggering events for testing.

    Args:
      port: The USB port number.
    """
    # Pull-down HPD GPIO
    self._CallPD(['gpioset', 'USB_C%d_DP_HPD' % port, '0'])

  def SetPortFunction(self, port, function):
    """Sets USB type-C port's function.

    Args:
      port: The USB port number.
      function: USB Type-C function, should be one of 'dp', 'usb', 'sink', and
          'source'.
    """
    logging.info('Set USB type-C port %d to %s', port, function)
    if function not in self.PORT_FUNCTION:
      raise types.DeviceException(
          'unsupported USB Type-C function: %s' % function)
    self._CallPD([function], port)

  def ResetPortFunction(self, port):
    """Resets USB Type-C port to default function.

    Set PD mux to auto-toggle, and disable USB3.0/DP function.

    Args:
      port: The USB port number.
    """
    logging.info('Reset USB type-C port %d', port)
    self._CallPD(['toggle'], port)  # Auto-toggle charge/discharge
    self._CallPD(['usb'], port)  # Default USB3.0

  def _CallPD(self, command, port=None):
    """Sends ectool PD command.

    Args:
      command: A list of strings for command to execute.
      port: The USB port number. None for sending command without indicating
          port.

    Returns:
      The output on STDOUT from executed command.

    Raises:
      CalledProcessError if the exit code is non-zero.
    """
    return self._device.CheckOutput(
        ['ectool'] + self.ECTOOL_PD_ARGS +
        ([] if port is None else ['usbpd', '%d' % port]) + command)
