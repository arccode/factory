# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import re
import threading
import time

from cros.factory.device import device_utils
from cros.factory.goofy.plugins import plugin
from cros.factory.test import state
from cros.factory.utils import config_utils
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


class LedIndicator(plugin.Plugin):
  """Plugin to indicate the test state of some given tests.

  This plugin will check the test state of the tests listed in the config file,
  and then change LED status to indicate the test state. If any of the tests
  failed, the LED status will set to FAILED to indicate the operator.
  UNTESTED will have the same LED status as PASSED, so it is recommended to set
  LED status of PASSED to the default LED procedure. If do so, the LED will
  behave normal if we passed all the monitored tests.
  """

  def __init__(self, goofy, check_tests=None):
    super(LedIndicator, self).__init__(goofy, [plugin.RESOURCE.LED])
    self._check_tests = check_tests
    self._thread = None
    self._stop_event = threading.Event()

  @type_utils.Overrides
  def OnStart(self):
    self._stop_event.clear()
    self._thread = process_utils.StartDaemonThread(target=self._RunTarget)

  @type_utils.Overrides
  def OnStop(self):
    self._stop_event.set()

  def _RunTarget(self):
    instance = state.GetInstance()
    all_test_states = instance.GetTestStates()

    check_tests_re = [re.compile(test_re) for test_re in self._check_tests]
    check_tests = []
    for name in all_test_states:
      for test_re in check_tests_re:
        if test_re.search(name):
          check_tests += [name]
          break

    dut = device_utils.CreateDUTInterface()
    config = config_utils.LoadConfig()

    def _SetLED(led, setting):
      color = setting['color']
      led_name = setting['led_name']
      brightness = setting['brightness']

      # Always set to AUTO after setting a color, so the LED will be off after
      # shutting down.
      if setting['on_time'] > 0:
        led.SetColor(color, led_name, brightness)
        led.SetColor('AUTO', led_name)
        time.sleep(setting['on_time'])

      if setting['off_time'] > 0:
        led.SetColor(color, led_name, brightness=0)
        led.SetColor('AUTO', led_name)
        time.sleep(setting['off_time'])

    blinks = {}
    for status in config:
      blinks[status] = False
      if config[status]['on_time'] > 0 and config[status]['off_time'] > 0:
        blinks[status] = True

    last_status = None
    while not self._stop_event.wait(0.1):
      # UNTESTED will have the same LED status as PASSED.
      led_status = state.TestState.PASSED
      for test in check_tests:
        test_status = instance.GetTestState(test).status
        if test_status == state.TestState.ACTIVE:
          led_status = state.TestState.ACTIVE
        elif test_status == state.TestState.FAILED:
          led_status = state.TestState.FAILED
          break

      # If the LED setting is not changing in the test state, do not keep
      # setting LED status to reduce logging.
      if blinks[led_status] or led_status != last_status:
        _SetLED(dut.led, config[led_status])
      last_status = led_status
