# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Check the retimer firmware version.

Description
-----------
Verifies the retimer firmware version.

We do the test twice because the retimer device only gets enumerated if the
port connect to nothing before boot. We need to make sure the ports are clean.
See b/181360981#comment6 for more information.

Test Procedure
--------------
1. The test tries to find all retimer nodes.
2. If the test finds all nodes then go to 7.
3. If the test fails to find all nodes then tell the operator to remove all
   devices from usb type c ports.
4. Reboot.
5. The test tries to find all retimer nodes.
6. If the test fails to find all nodes then the test fails.
7. The test compares the actual version and the expected version.

Dependency
----------
- The retimer device node must support nvm_version.

Examples
--------
The minimal working example::

  {
    "CheckRetimerFirmware": {
      "pytest_name": "check_retimer_firmware",
      "args": {
        "wait_all_ports_unplugged": false,
        "controller_ports": [
          "0-0:1.1",
          "0-0:3.1"
        ],
        "usb_ports": [
          0,
          1
        ],
        "min_retimer_version": "21.0"
      }
    },
    "CheckRetimerFirmwareGroup": {
      "subtests": [
        {
          "inherit": "CheckRetimerFirmware",
          "args": {
            "wait_all_ports_unplugged": true
          }
        },
        {
          "inherit": "RebootStep",
          "run_if": "not device.factory.retimer_firmware_checked"
        },
        "CheckRetimerFirmware"
      ]
    }
  }
"""

from distutils import version
import logging

from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test.i18n import _
from cros.factory.test.rules import phase
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


_RETIMER_VERSION_PATH = '/sys/bus/thunderbolt/devices/%s/nvm_version'
_CONTROLLER_PORTS = ('0-0:1.1', '0-0:3.1', '1-0:1.1', '1-0:3.1')
_REBOOT_DEVICE_DATA_PATH = 'factory.retimer_firmware_reboot'


class RetimerFirmwareTest(test_case.TestCase):
  """Retimer firmware test."""

  ARGS = [
      Arg('wait_all_ports_unplugged', bool,
          'Tell the operator to unplug all usb c ports if the test fails.',
          default=None),
      Arg('controller_ports', list,
          ('All the controller ports that we want ot test. Must be a subset of '
           f'{_CONTROLLER_PORTS!r}'), default=None),
      Arg('usb_ports', list, ('All the usb ports that we want ot test.'),
          default=None),
      Arg('min_retimer_version', str,
          ('The minimum Retimer firmware version. Set to None to disable the '
           'check.'), default=None),
      Arg('max_retimer_version', str,
          ('The maximum Retimer firmware version. Set to None to disable the '
           'check.'), default=None),
      Arg('timeout_secs', int,
          ('Timeout in seconds when we ask operator to complete the challenge.'
           ' None means no timeout.'), default=30),
  ]

  def setUp(self):
    self.ui.ToggleTemplateClass('font-large', True)
    self._dut = device_utils.CreateDUTInterface()
    self.controller_ports = self.args.controller_ports
    self.usb_ports = self.args.usb_ports
    if not set(_CONTROLLER_PORTS).issuperset(self.controller_ports):
      raise ValueError(f'controller_ports {self.controller_ports!r} must be a '
                       f'subset of {_CONTROLLER_PORTS!r}.')
    phase.AssertStartingAtPhase(phase.PVT, self.args.min_retimer_version,
                                'min_retimer_version must be specified.')

  def _CheckOneRetimer(self, controller_port: str,
                       wait_before_get_version: bool):
    """Check the firmware version of the retimer.

    Args:
      controller_port: The target controller port.
      wait_before_get_version: If set to True, wait for 20 seconds before
        retrieving the firmware version. The retimer doesn't get enumerated
        until 20 seconds after booting. Otherwise, wait for 1 second since we
        have waited for 20 seconds already.

    Raises:
      type_utils.TimeoutError: The device does not get enumerated.
      ValueError: If the version does not meet the constraints.
    """
    retimer_version_path = _RETIMER_VERSION_PATH % controller_port
    logging.info('cat %s', retimer_version_path)

    def _TryToGetVersion():
      try:
        return self._dut.ReadFile(retimer_version_path)
      except Exception:
        return None

    # We need to wait 20 seconds. See b/181360981#comment6.
    timeout_secs = 21 if wait_before_get_version else 1
    version_string = sync_utils.WaitFor(_TryToGetVersion, timeout_secs,
                                        poll_interval=1)
    retimer_version = version.LooseVersion(version_string.strip())
    logging.info('retimer_version %s', retimer_version)

    if self.args.min_retimer_version:
      min_retimer_version = version.LooseVersion(self.args.min_retimer_version)
      if retimer_version < min_retimer_version:
        raise ValueError('retimer_version %s < min_retimer_version %s' %
                         (retimer_version, min_retimer_version))

    if self.args.max_retimer_version:
      max_retimer_version = version.LooseVersion(self.args.max_retimer_version)
      if retimer_version > max_retimer_version:
        raise ValueError('retimer_version %s > max_retimer_version %s' %
                         (retimer_version, max_retimer_version))

  def _WaitOneUSBUnplugged(self, usb_port):
    """Waits until usb_port is disconnected."""
    test_timer = None
    if self.args.timeout_secs:
      test_timer = self.ui.StartCountdownTimer(self.args.timeout_secs)

    self.ui.SetState(
        _('Please remove USB type-C cable from port {port}', port=usb_port))

    def _VerifyDisconnect():
      usbpd_verified, unused_mismatch = self._dut.usb_c.VerifyPDStatus({
          'connected': False,
          'port': usb_port,
      })
      return usbpd_verified

    sync_utils.WaitFor(_VerifyDisconnect, self.args.timeout_secs,
                       poll_interval=0.5)
    if test_timer:
      test_timer.set()

  def _WaitUSBUnplugged(self):
    """Waits until all ports in self.usb_ports are disconnected."""
    for usb_port in self.usb_ports:
      self._WaitOneUSBUnplugged(usb_port)
    self.ui.SetInstruction('')

  def runTest(self):
    device_data.UpdateDeviceData({_REBOOT_DEVICE_DATA_PATH: False})
    errors = {}
    not_found_ports = {}
    wait_before_get_version = True
    for controller_port in self.controller_ports:
      try:
        self._CheckOneRetimer(controller_port, wait_before_get_version)
      except type_utils.TimeoutError as e:
        not_found_ports[controller_port] = e
      except Exception as e:
        errors[controller_port] = e
      wait_before_get_version = False

    if self.args.wait_all_ports_unplugged:
      if errors:
        self.FailTask(f'{errors!r}')
      if not_found_ports:
        self._WaitUSBUnplugged()
        device_data.UpdateDeviceData({_REBOOT_DEVICE_DATA_PATH: True})
    else:
      errors.update(not_found_ports.items())
      if errors:
        self.FailTask(f'{errors!r}')
