# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Tests thunderbolt port with a loopback card.

Description
-----------
Verifies the thunderbolt port with a loopback card.

Test Procedure
--------------
1. Operator inserts the loopback card.
2. The tool sends payloads to the loopback card.
3. The tool receives payloads from the loopback card and checks correctness.
4. Operator removes the loopback card.

Dependency
----------
- Loopback card driver.

Examples
--------
The minimal working example::

  {
    "pytest_name": "thunderbolt_loopback"
  }

Test specific controller with 60 seconds timeout::

  {
    "pytest_name": "thunderbolt_loopback"
    "args": {
      "timeout_secs": 60,
      "controller_port": "0-1.*"
    }
  }
"""

import logging
import re

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


_LOOPBACK_TEST_PATH = '/sys/kernel/debug/thunderbolt'
_CONTROLLER_PORTS = ('0-1.*', '0-3.*', '1-1.*', '1-3.*')
_DMA_TEST = 'dma_test'
_TEST_MODULE = 'thunderbolt_dma_test'
LINK_WIDTH_TYPE = type_utils.Enum(['Single', 'Dual'])
ENCODE_LINK_WIDTH = {
    LINK_WIDTH_TYPE.Single: '1',
    LINK_WIDTH_TYPE.Dual: '2'
}
_RE_STATUS = re.compile(r'^result: (.+)\n(?:.|\n)*$')
_CARD_STATE = type_utils.Enum(['Absent', 'Multiple', 'Wrong'])


class ThunderboltLoopbackTest(test_case.TestCase):
  """Thunderbolt loopback card factory test."""
  ARGS = [
      Arg('timeout_secs', int, 'Timeout value for the test.', default=None),
      Arg('expected_link_speed', int, 'Link speed.', default=20),
      Arg('expected_link_width', LINK_WIDTH_TYPE, 'Link width.',
          default=LINK_WIDTH_TYPE.Dual),
      Arg('packets_to_send', int, 'Amount of packets to be sent.',
          default=1000),
      Arg('packets_to_receive', int, 'Amount of packets to be received.',
          default=1000),
      Arg('debugfs_path', str, 'The path of debugfs to test.', default=None),
      Arg('controller_port', str, 'The name of the controller port to test.',
          default=None),
      Arg('load_module', bool, 'Load test module.', default=True),
  ]

  def setUp(self):
    self.ui.ToggleTemplateClass('font-large', True)
    self._dut = device_utils.CreateDUTInterface()
    self._remove_module = False
    self._card_state = None

  def tearDown(self):
    if self._remove_module:
      self._dut.CheckCall(['modprobe', '-r', _TEST_MODULE], log=True)

  def _GlobLoopbackPath(self, controller_ports):
    devices = []
    for name in controller_ports:
      device_path = self._dut.path.join(_LOOPBACK_TEST_PATH, name, _DMA_TEST)
      devices.extend(
          self._dut.path.dirname(path) for path in self._dut.Glob(device_path))
    return devices

  def _SetCardState(self, state):
    if self._card_state == state:
      return False
    self._card_state = state
    return True

  def _FindLoopbackPath(self):
    if self.args.debugfs_path:
      if self._dut.path.exists(self.args.debugfs_path):
        return self.args.debugfs_path
      if self._SetCardState(_CARD_STATE.Absent):
        logging.info('No loopback card exists.')
      return None

    controller_ports = set([self.args.controller_port] if self.args
                           .controller_port else _CONTROLLER_PORTS)
    devices = self._GlobLoopbackPath(controller_ports)
    if len(devices) > 1:
      if self._SetCardState(_CARD_STATE.Multiple):
        self.ui.SetState(_('Do not insert more than one loopback card.'))
        logging.info('Multiple loopback cards exist: %r. controller_ports: %r',
                     devices, controller_ports)
      return None

    wrong_controller_ports = set(_CONTROLLER_PORTS) - controller_ports
    wrong_devices = self._GlobLoopbackPath(wrong_controller_ports)
    if wrong_devices:
      if self._SetCardState(_CARD_STATE.Wrong):
        self.ui.SetState(
            _('The loopback card is inserted into the wrong port.'))
        logging.info(('Wrong loopback cards exist: %r. '
                      'wrong_controller_ports: %r'), wrong_devices,
                     wrong_controller_ports)
      return None

    if not devices:
      if self._SetCardState(_CARD_STATE.Absent):
        self.ui.SetState(_('Insert the loopback card.'))
        logging.info('No loopback card exists. controller_ports: %r',
                     controller_ports)
      return None

    return devices[0]

  def _CheckModule(self, module_name):
    return self._dut.Call(['modinfo', module_name], log=True)

  def _LogAndWriteFile(self, filename, content):
    logging.info('echo %s > %s', content, filename)
    self._dut.WriteFile(filename, content)

  def runTest(self):
    if self.args.load_module and not self._CheckModule(_TEST_MODULE):
      self._dut.CheckCall(['modprobe', _TEST_MODULE], log=True)
      self._remove_module = True
    if self.args.timeout_secs:
      self.ui.StartFailingCountdownTimer(self.args.timeout_secs)
    # Wait for the loopback card.
    self.ui.SetState(_('Insert the loopback card.'))
    device_path = sync_utils.WaitFor(self._FindLoopbackPath,
                                     self.args.timeout_secs, poll_interval=0.5)
    self.ui.SetState(_('Test is in progress, please do not move the device.'))
    session.console.info('The loopback card path is at %r.', device_path)
    device_test_path = self._dut.path.join(device_path, _DMA_TEST)
    # Configure the test
    self._LogAndWriteFile(
        self._dut.path.join(device_test_path, 'speed'),
        str(self.args.expected_link_speed))
    self._LogAndWriteFile(
        self._dut.path.join(device_test_path, 'lanes'),
        ENCODE_LINK_WIDTH[self.args.expected_link_width])
    self._LogAndWriteFile(
        self._dut.path.join(device_test_path, 'packets_to_send'),
        str(self.args.packets_to_send))
    self._LogAndWriteFile(
        self._dut.path.join(device_test_path, 'packets_to_receive'),
        str(self.args.packets_to_receive))
    # Run the test.
    self._LogAndWriteFile(self._dut.path.join(device_test_path, 'test'), '1')
    # Check the result.
    status_path = self._dut.path.join(device_test_path, 'status')
    logging.info('cat %s', status_path)
    output = self._dut.ReadFile(status_path)
    logging.info('output:\n%s', output)
    match = _RE_STATUS.match(output)
    if not match:
      self.FailTask('Output format of status is changed.')
    result = match.group(1)
    if result == 'success':
      self.PassTask()
    elif result in ('fail', 'failed', 'not run'):
      self.FailTask(result)
    else:
      self.FailTask('Unknown result: %r' % result)
