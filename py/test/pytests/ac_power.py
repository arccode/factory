# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A test to instruct the operator / BFT fixture to plug/unplug AC power."""

import threading
import time
import unittest

from cros.factory import system
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg

from cros.factory.test.fixture.bft_fixture import (BFTFixture,
                                                   CreateBFTFixture)


_TEST_TITLE_PLUG = test_ui.MakeLabel('Connect AC', u'连接充电器')
_TEST_TITLE_UNPLUG = test_ui.MakeLabel('Remove AC', u'移除充电器')

_PLUG_AC = lambda x: test_ui.MakeLabel(
    'Plug in the charger' + (' (%s)' % x if x else ''),
    u'请连接充电器' + (' (%s)' % x if x else ''))
_UNPLUG_AC = test_ui.MakeLabel('Unplug the charger.', u'请移除充电器')

_PROBE_TIMES_ID = 'probed_times'
_PROBE_TIMES = lambda total: '%s <span id="%s">0</span> / %d' % (
    test_ui.MakeLabel('Probed', u'侦测次数'), _PROBE_TIMES_ID, total)

_AC_STATUS_ID = 'ac_status'
_NO_AC = test_ui.MakeLabel('No AC adapter', u'沒有充电器')
_AC_TYPE_PROBING = test_ui.MakeLabel('Identifying AC adapter...',
                                     u'充电器型号识别中...')
_AC_TYPE = test_ui.MakeLabel('AC adapter type: ', u'充电器型号: ')

class ACPowerTest(unittest.TestCase):
  """A test to instruct the operator to plug/unplug AC power.

  Args:
    power_type: The type of the power. None to skip power type check.
    online: True if expecting AC power. Otherwise, False.
    bft_fixture: If assigned, it commands the BFT fixture to
        plug/unplug an AC adapter.
    retries: Maximum number of retries allowed to pass the test.
    polling_period_secs: Polling period in seconds.
    silent_warning: Skips first N charger type mismatch before giving a
        warning.
  """

  ARGS = [
    Arg('power_type', str, 'Type of the power source', optional=True),
    Arg('online', bool, 'True if expecting AC power', default=True),
    Arg('bft_fixture', dict,
        '{class_name: BFTFixture\'s import path + module name\n'
        ' params: a dict of params for BFTFixture\'s Init()}.\n'
        'Default None means no BFT fixture is used.', optional=True),
    Arg('retries', int,
        'Maximum number of retries allowed to pass the test. '
        '0 means only probe once. Default None means probe forever.',
        optional=True),
    Arg('polling_period_secs', (int, float),
        'Polling period in seconds.', default=1),
    Arg('silent_warning', int,
        'Skips first N charger type mismatch before giving a warning. '
        'Because EC needs about 1.6 seconds to identify charger type after '
        'it is plugged in, it skips first N mismatched probe.',
        default=2),
  ]

  def setUp(self):
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE_PLUG if self.args.online
                            else _TEST_TITLE_UNPLUG)

    instruction = (_PLUG_AC(self.args.power_type)
                   if self.args.online else _UNPLUG_AC)
    probe_count_message = ''
    if self.args.retries is not None:
      probe_count_message = _PROBE_TIMES(self.args.retries)
    self._template.SetState(
        '%s<br>%s<div id="%s"></div>' %
        (instruction, probe_count_message, _AC_STATUS_ID))

    self._power_state = dict()
    self._done = threading.Event()
    self._power = system.GetBoard().power
    self._last_type = None
    self._last_ac_present = None
    self._skip_warning_remains = self.args.silent_warning

    # Prepare fixture auto test if needed.
    self.fixture = None
    if self.args.bft_fixture:
      self.fixture = CreateBFTFixture(**self.args.bft_fixture)

  def Done(self):
    self._done.set()

  def UpdateACStatus(self, status):
    self._ui.SetHTML(status, id=_AC_STATUS_ID)

  def CheckCondition(self):
    ac_present = self._power.CheckACPresent()
    current_type = self._power.GetACType()

    # Reset silent warning countdown when AC present status change.
    # Also reset _last_type as we want to give a warning for each
    # mismatched charger attached.
    if self._last_ac_present != ac_present:
      self._last_ac_present = ac_present
      self._skip_warning_remains = self.args.silent_warning
      self._last_type = None

    if ac_present != self.args.online:
      if not ac_present:
        self.UpdateACStatus(_NO_AC)
      return False

    if self.args.power_type and self.args.power_type != current_type:
      if self._skip_warning_remains > 0:
        self.UpdateACStatus(_AC_TYPE_PROBING)
        self._skip_warning_remains -= 1
      elif self._last_type != current_type:
        self.UpdateACStatus(_AC_TYPE + current_type)
        factory.console.warning(
            'Expecting %s but see %s', self.args.power_type, current_type)
        self._last_type = current_type
      return False
    return True

  def runTest(self):
    self._ui.Run(blocking=False, on_finish=self.Done)
    if self.fixture:
      self.fixture.SetDeviceEngaged(BFTFixture.Device.AC_ADAPTER,
                                    self.args.online)
    num_probes = 0

    while not self._done.is_set():
      if self.CheckCondition():
        break
      if self.args.retries is not None:
        # retries is set.
        num_probes += 1
        self._ui.SetHTML(str(num_probes), id=_PROBE_TIMES_ID)
        if self.args.retries < num_probes:
          self.fail('Failed after probing %d times' % num_probes)
      # Prevent busy polling.
      time.sleep(self.args.polling_period_secs)
