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
4. The tool collects lane margining data and uploads it to server.
5. Operator removes the loopback card.

Dependency
----------
- Loopback card driver.
- tdtl tool if we want to test lane margining.
- Write serial number to device data before the test for data collecting.
- The DUT must be able to connect factory server when running the test.

Examples
--------
The minimal working example::

  {
    "pytest_name": "thunderbolt_loopback",
    "args": {
      "usbpd_spec": {
        "port": 0
      }
    }
  }

Test specific controller and test lane margining with 60 seconds timeout::

  {
    "pytest_name": "thunderbolt_loopback"
    "args": {
      "usbpd_spec": {
        "port": 0
      },
      "timeout_secs": 60,
      "controller_port": "0-1.*",
      "lane_margining": true
    }
  }

Test controller 0-3 with CC1 port 1 with 60 seconds timeout::

  {
    "pytest_name": "thunderbolt_loopback"
    "args": {
      "usbpd_spec": {
        "port": 1,
        "polarity": 1
      },
      "timeout_secs": 60,
      "controller_port": "0-3.*"
    }
  }
"""

import logging
import os
import re
import subprocess
import time

from cros.factory.device import device_utils
from cros.factory.device import usb_c
from cros.factory.test import device_data
from cros.factory.test.env import paths
from cros.factory.test.i18n import _
from cros.factory.testlog import testlog
from cros.factory.test import server_proxy
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


_LOOPBACK_TEST_PATH = '/sys/kernel/debug/thunderbolt'
_CONTROLLER_PORTS = ('0-1.*', '0-3.*', '1-1.*', '1-3.*')
_RE_ADP_DOMAIN = re.compile(r'^.*(?P<domain>\d+)-(?P<adapter>\d+)\.\d+$')
_RE_MARGIN_LOOPBACK = re.compile(
    r'(RT\d+ L\d+ )(BOTTOM|LEFT),(TOP|RIGHT) = (\d+),(\d+)')
_DMA_TEST = 'dma_test'
_TEST_MODULE = 'thunderbolt_dma_test'
LINK_WIDTH_TYPE = type_utils.Enum(['Single', 'Dual'])
LINK_SPEED_TYPE = type_utils.Enum(['Slow', 'Fast'])
ENCODE_LINK_WIDTH = {
    LINK_WIDTH_TYPE.Single: '1',
    LINK_WIDTH_TYPE.Dual: '2'
}
ENCODE_LINK_SPEED = {
    LINK_SPEED_TYPE.Slow: '10',
    LINK_SPEED_TYPE.Fast: '20'
}
_RE_STATUS = re.compile(r'^result: (.+)\n(?:.|\n)*$')
_CARD_STATE = type_utils.Enum(['Absent', 'Multiple', 'Wrong'])
_TDTL_PATH = os.path.join(paths.FACTORY_DIR, 'tdtl-master')


class ThunderboltLoopbackTest(test_case.TestCase):
  """Thunderbolt loopback card factory test."""
  LOG_GROUP_NAME = 'usb4_lane_margining_log'
  LOG_KEYS = [
      'DOMAIN',
      'ADP',
      'RT1 L0 BOTTOM',
      'RT1 L0 TOP',
      'RT1 L0 LEFT',
      'RT1 L0 RIGHT',
      'RT1 L1 BOTTOM',
      'RT1 L1 TOP',
      'RT1 L1 LEFT',
      'RT1 L1 RIGHT',
      'RT2 L0 BOTTOM',
      'RT2 L0 TOP',
      'RT2 L0 LEFT',
      'RT2 L0 RIGHT',
      'RT2 L1 BOTTOM',
      'RT2 L1 TOP',
      'RT2 L1 LEFT',
      'RT2 L1 RIGHT',
  ]
  ARGS = [
      Arg('timeout_secs', int, 'Timeout value for the test.', default=None),
      Arg('expected_link_speed', LINK_SPEED_TYPE, 'Link speed.',
          default=LINK_SPEED_TYPE.Fast),
      Arg('expected_link_width', LINK_WIDTH_TYPE, 'Link width.',
          default=LINK_WIDTH_TYPE.Dual),
      Arg('packets_to_send', int, 'Amount of packets to be sent.',
          default=1000),
      Arg('packets_to_receive', int, 'Amount of packets to be received.',
          default=1000),
      Arg('debugfs_path', str, 'The path of debugfs to test.', default=None),
      Arg('controller_port', str, 'The name of the controller port to test.',
          default=None),
      Arg('usbpd_spec', dict,
          ('A dict which must contain "port" and optionally specify "polarity".'
           ' For example, `{"port": 1, "polarity": 1}`.'),
          schema=usb_c.USB_PD_SPEC_SCHEMA, _transform=usb_c.MigrateUSBPDSpec),
      Arg('load_module', bool, 'Load test module.', default=True),
      Arg('check_muxinfo_only', bool, 'Check muxinfo only.', default=False),
      Arg('lane_margining', bool, 'Collet lane margining data.', default=False),
      Arg('lane_margining_timeout_secs', (int, float),
          'Timeout for colleting lane margining data.', default=10),
      Arg('check_card_removal', bool,
          'If set, require removing the card after DMA test.', default=True),
  ]

  def setUp(self):
    self.ui.ToggleTemplateClass('font-large', True)
    self._dut = device_utils.CreateDUTInterface()
    self._usbpd_port = self.args.usbpd_spec['port']
    self._usbpd_polarity = {
        1: 'NORMAL',
        2: 'INVERTED'
    }.get(self.args.usbpd_spec.get('polarity'))
    self._remove_module = False
    self._card_state = None
    self._muxinfo = {}
    self._first_typec_control = True
    self._first_check_mux_info = True

    self._group_checker = None
    if self.args.lane_margining:
      # Group checker and details for Testlog.
      self._group_checker = testlog.GroupParam(self.LOG_GROUP_NAME,
                                               self.LOG_KEYS)
      testlog.UpdateParam('ADP', param_type=testlog.PARAM_TYPE.argument)
      testlog.UpdateParam('DOMAIN', param_type=testlog.PARAM_TYPE.argument)
    self._errors = []

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

  def _SendTypecControl(self):
    """Send typeccontrol control command."""
    _first_typec_control = self._first_typec_control
    self._first_typec_control = False
    mode = {
        'DP': '0',
        'TBT': '1',
        'USB4': '2'
    }
    try:
      self._dut.CheckCall(
          ['ectool', 'typeccontrol',
           str(self._usbpd_port), '2', mode['TBT']], log=_first_typec_control)
    except Exception:
      pass

  def _CheckMuxinfo(self):
    """Returns True if TBT=1."""
    fail_tag = 'GetPDMuxInfo'
    _first_check_mux_info = self._first_check_mux_info
    self._first_check_mux_info = False
    try:
      outputs = self._dut.usb_c.GetPDMuxInfo(self._usbpd_port,
                                             log=_first_check_mux_info)
    except Exception:
      if self._muxinfo.get(fail_tag) != 1:
        logging.exception('%s failed', fail_tag)
        self.ui.SetState(_('Please unplug and replug.'))
        self._muxinfo = {
            fail_tag: 1
        }
      return False
    else:
      if self._muxinfo != outputs:
        logging.info('%s %r', fail_tag, outputs)
        self.ui.SetState(
            'Port %d<br>%s %r' % (self._usbpd_port, fail_tag, outputs))
        self._muxinfo = outputs
      if self._usbpd_polarity:
        if outputs['POLARITY'] != self._usbpd_polarity:
          self.ui.SetInstruction(
              _('Wrong USB side, please flip over {media}.',
                media='Loopback card'))
          return False
        self.ui.SetInstruction('')
      if outputs['TBT']:
        return True
      if outputs['USB']:
        self._SendTypecControl()
      return False

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

  def _LogAndWriteFile(self, filename, content):
    logging.info('echo %s > %s', content, filename)
    self._dut.WriteFile(filename, content)

  def _TestLaneMargining(self, domain: str, adapter: str):
    """Uses tdtl tool to collect lane margining data.

    Args:
      domain: A string we pass to tdtl tool.
      adapter: A string we pass to tdtl tool.

    Returns:
      log_result: A dict to save the result.
    """
    session.console.info('Start collecting lane margining data.')
    # Log 0 when failed.
    # Log -1 when timeout.
    log_result = dict.fromkeys(self.LOG_KEYS, None)
    log_result.update({
        'ADP': int(adapter),
        'DOMAIN': int(domain),
    })
    # self._dut.CheckOutput do not support env and timeout
    # process_utils.Spawn do not support timeout
    cmd = [
        'cli.py', 'margin_loopback', '-d', domain, '-a', adapter, '-r', '0',
        '-i', '1'
    ]
    env = {
        'ADP': adapter,
        'LC_ALL': 'en_US.utf-8',
    }
    logging.info('env: %r, cmd: %r, cwd: %r', env, cmd, _TDTL_PATH)
    stop_timer = self.ui.StartCountdownTimer(
        self.args.lane_margining_timeout_secs)
    try:
      result = subprocess.run(cmd, env=env, cwd=_TDTL_PATH,
                              timeout=self.args.lane_margining_timeout_secs,
                              encoding='utf-8', stdout=subprocess.PIPE,
                              check=False)
    except subprocess.TimeoutExpired:
      logging.exception('_TestLaneMargining timeout')
      self._errors.append('_TestLaneMargining timeout')
      for key, value in log_result.items():
        if value is None:
          log_result[key] = -1
      return log_result
    finally:
      stop_timer.set()
    try:
      logging.info('stdout:\n%s', result.stdout)
      result.check_returncode()
    except Exception:
      logging.exception('_TestLaneMargining failed')
      self._errors.append('_TestLaneMargining failed')
      for key, value in log_result.items():
        if value is None:
          log_result[key] = 0
    # The output of `cli.py margin_loopback` looks like below.
    #
    # RT1 L0 BOTTOM,TOP = 56,54
    # RT2 L0 BOTTOM,TOP = 56,62
    # RT1 L0 LEFT,RIGHT = 20,17
    # RT2 L0 LEFT,RIGHT = 22,24
    # RT1 L1 BOTTOM,TOP = 62,70
    # RT2 L1 BOTTOM,TOP = 60,68
    # RT1 L1 LEFT,RIGHT = 21,22
    # RT2 L1 LEFT,RIGHT = 17,16
    for line in result.stdout.splitlines():
      match = _RE_MARGIN_LOOPBACK.match(line)
      if not match:
        continue
      for index in range(2, 4):
        log_result.update(
            {match.group(1) + match.group(index): int(match.group(index + 2))})
    return log_result

  def _GetUITimer(self):
    """Returns the stop event flag of the timer or None if no timeout."""
    if self.args.timeout_secs:
      return self.ui.StartFailingCountdownTimer(self.args.timeout_secs)
    return None

  def _UploadLaneMargining(self, log_result: dict):
    """Uploads the result of lane margining."""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
    csv_entries = [device_data.GetSerialNumber(), timestamp]
    csv_entries.extend(log_result[key] for key in self.LOG_KEYS)
    self.ui.SetState(_('Trying to check server protocol...'))
    try:
      server = server_proxy.GetServerProxy(timeout=5)
      server.Ping()
      server.UploadCSVEntry(self.LOG_GROUP_NAME, csv_entries)
    except server_proxy.Fault:
      messages = 'Server fault %s' % server_proxy.GetServerURL()
      logging.exception(messages)
      self._errors.append(messages)
    except Exception:
      messages = 'Unable to sync with server %s' % server_proxy.GetServerURL()
      logging.exception(messages)
      self._errors.append(messages)
    with self._group_checker:
      for key, value in log_result.items():
        testlog.LogParam(key, value)

  def _WaitMuxInfoBecomingTBT(self):
    """Waits until Mux info becomes TBT=1."""
    stop_timer = self._GetUITimer()

    self.ui.SetState(_('Insert the loopback card.'))
    sync_utils.WaitFor(self._CheckMuxinfo, self.args.timeout_secs,
                       poll_interval=0.5)
    if stop_timer:
      stop_timer.set()

  def _WaitForLoopbackCardInsertion(self):
    """Waits until device node appears."""
    stop_timer = self._GetUITimer()

    self.ui.SetState(_('Insert the loopback card.'))
    device_path = sync_utils.WaitFor(self._FindLoopbackPath,
                                     self.args.timeout_secs, poll_interval=0.5)
    match = _RE_ADP_DOMAIN.match(device_path)
    if not match:
      raise Exception('device_path is not in expected format.')
    adapter = match.group('adapter')
    domain = match.group('domain')
    session.console.info('The ADP is at %r, domain is %r.', adapter, domain)

    if stop_timer:
      stop_timer.set()

    return device_path, domain, adapter

  def _WaitForLoopbackCardRemoval(self, device_path):
    """Waits until device node disappears."""
    stop_timer = self._GetUITimer()

    self.ui.SetState(_('Remove the loopback card.'))

    sync_utils.WaitFor(lambda: not self._dut.path.exists(device_path),
                       self.args.timeout_secs, poll_interval=0.5)
    if stop_timer:
      stop_timer.set()

  def _TestDMA(self, device_path):
    """Performs DMA test."""
    stop_timer = self._GetUITimer()

    self.ui.SetState(_('Test is in progress, please do not move the device.'))
    session.console.info('The loopback card path is at %r.', device_path)
    device_test_path = self._dut.path.join(device_path, _DMA_TEST)
    # Configure the test
    self._LogAndWriteFile(
        self._dut.path.join(device_test_path, 'speed'),
        ENCODE_LINK_SPEED[self.args.expected_link_speed])
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
    if stop_timer:
      stop_timer.set()
    # Check the result.
    status_path = self._dut.path.join(device_test_path, 'status')
    logging.info('cat %s', status_path)
    output = self._dut.ReadFile(status_path)
    logging.info('output:\n%s', output)
    match = _RE_STATUS.match(output)
    if not match:
      self._errors.append('Output format of status is changed.')
    result = match.group(1)
    if result == 'success':
      return
    if result in ('fail', 'failed', 'not run'):
      self._errors.append('result: %s' % result)
    else:
      self._errors.append('Unknown result: %r' % result)

  def runTest(self):
    self._WaitMuxInfoBecomingTBT()
    if self.args.check_muxinfo_only:
      self.PassTask()

    if self.args.load_module:
      # Fail the test if the module doesn't exist.
      self._dut.CheckCall(['modinfo', _TEST_MODULE])
      # If the module is loaded before the test then do not remove it.
      loaded = self._dut.Call(['modprobe', '--first-time', _TEST_MODULE],
                              log=True)
      self._remove_module = not loaded

    device_path, domain, adapter = self._WaitForLoopbackCardInsertion()
    self._TestDMA(device_path)

    if self.args.lane_margining:
      log_result = self._TestLaneMargining(domain, adapter)
      self._UploadLaneMargining(log_result)

    if self.args.check_card_removal:
      self._WaitForLoopbackCardRemoval(device_path)

    if self._errors:
      self.FailTask('\n'.join(self._errors))
