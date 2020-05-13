# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import time

from cros.factory.device import device_utils
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test.utils import stress_manager
from cros.factory.utils.arg_utils import Arg


class PowerUnderStressTest(test_case.TestCase):
  """Measure the power consumption (voltage and current) under heavy load."""

  ARGS = [
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP, default=None),
      Arg('adb_remote_test', bool, 'Run test against remote ADB target.',
          default=False),
      Arg('seconds', int,
          'Time to execute the stressapptest.', default=60),
      Arg('memory_ratio', float,
          'Fraction of free memory', default=0.9),
      Arg('free_memory_only', bool,
          'Only use free memory for test. When set to True, only '
          'memory_radio * free_memory are used for stressapptest.',
          default=False),
      Arg('wait_secs', int,
          'Time to wait in seconds before executing stressapptest.',
          default=30),
      Arg('disk_thread', bool,
          'stress disk using -f argument of stressapptest.',
          default=True),
      Arg('usb_port_id', int, 'The ID of USB port connected to charger',
          default=0),
      Arg('voltage_threshold_min', int,
          'Minimum voltage (mV) allowed through out the entire test.',
          default=None),
      Arg('voltage_threshold_max', int,
          'Maximum voltage (mV) allowed through out the entire test.',
          default=None),
      Arg('current_threshold_min', int,
          'Minimum current (mA) allowed through out the entire test.',
          default=None),
      Arg('current_threshold_max', int,
          'Maximum current (mA) allowed through out the entire test.',
          default=None),
  ]

  def setUp(self):
    if self.args.bft_fixture is not None:
      self._bft_fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)
      if not self._bft_fixture.IsParallelTest():
        if self.args.adb_remote_test:
          self._bft_fixture.SetDeviceEngaged('ADB_HOST', engage=True)
        else:
          self._bft_fixture.SetDeviceEngaged('USB3', engage=True)
    else:
      self._bft_fixture = None
    self._dut = device_utils.CreateDUTInterface()
    self.ui.SetState('<div id="voltage"></div>'
                     '<div id="current"></div>')

  def UpdateState(self, voltage, current):
    self.ui.SetHTML(_('Voltage: {voltage} mV', voltage=voltage), id='voltage')
    self.ui.SetHTML(_('Current: {current} mA', current=current), id='current')

  def runTest(self):
    self.ui.StartCountdownTimer(self.args.wait_secs)

    with stress_manager.StressManager(self._dut).Run(
        duration_secs=None,
        memory_ratio=self.args.memory_ratio,
        free_memory_only=self.args.free_memory_only,
        disk_thread=self.args.disk_thread):

      start_time = time.time()
      for elapsed in range(1, self.args.wait_secs + 1):
        if self._bft_fixture:
          ina_values = self._bft_fixture.ReadINAValues()
          voltage = ina_values['voltage']
          current = ina_values['current']
        else:
          usb_port_info = (
              self._dut.power.GetUSBPDPowerInfo()[self.args.usb_port_id])
          voltage, current = usb_port_info.voltage, usb_port_info.current

        self.UpdateState(voltage, current)

        if self.args.voltage_threshold_min:
          self.assertTrue(voltage >= self.args.voltage_threshold_min)
        if self.args.voltage_threshold_max:
          self.assertTrue(voltage <= self.args.voltage_threshold_max)
        if self.args.current_threshold_min:
          self.assertTrue(current >= self.args.current_threshold_min)
        if self.args.current_threshold_max:
          self.assertTrue(current <= self.args.current_threshold_max)

        self.Sleep(start_time + elapsed - time.time())
