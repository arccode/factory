# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A test to instruct the operator / BFT fixture to plug/unplug AC power."""

import threading
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg


_TEST_TITLE_PLUG = i18n_test_ui.MakeI18nLabel('Connect AC')
_TEST_TITLE_UNPLUG = i18n_test_ui.MakeI18nLabel('Remove AC')

_PLUG_AC = lambda type: (
    i18n_test_ui.MakeI18nLabel('Plug in the charger ({type})', type=type)
    if type else i18n_test_ui.MakeI18nLabel('Plug in the charger'))
_UNPLUG_AC = i18n_test_ui.MakeI18nLabel('Unplug the charger.')

_PROBE_TIMES_ID = 'probed_times'
_PROBE_TIMES_MSG = lambda times, total: i18n_test_ui.MakeI18nLabel(
    'Probed {times} / {total}', times=times, total=total)

_AC_STATUS_ID = 'ac_status'
_NO_AC = i18n_test_ui.MakeI18nLabel('No AC adapter')
_AC_TYPE_PROBING = i18n_test_ui.MakeI18nLabel('Identifying AC adapter...')
_AC_TYPE = i18n_test_ui.MakeI18nLabel('AC adapter type: ')


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
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP, optional=True),
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
    self._power = device_utils.CreateDUTInterface().power
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE_PLUG if self.args.online
                            else _TEST_TITLE_UNPLUG)

    instruction = (_PLUG_AC(self.args.power_type)
                   if self.args.online else _UNPLUG_AC)
    probe_count_message = ''
    if self.args.retries is not None:
      probe_count_message = _PROBE_TIMES_MSG(0, self.args.retries)
    self._template.SetState(
        '%s<br><span id="%s">%s</span><div id="%s"></div>' %
        (instruction, _PROBE_TIMES_ID, probe_count_message, _AC_STATUS_ID))

    self._power_state = {}
    self._done = threading.Event()
    self._last_type = None
    self._last_ac_present = None
    self._skip_warning_remains = self.args.silent_warning

    # Prepare fixture auto test if needed.
    self.fixture = None
    if self.args.bft_fixture:
      self.fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)

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

  def _runTest(self):
    if self.fixture:
      self.fixture.SetDeviceEngaged(bft_fixture.BFTFixture.Device.AC_ADAPTER,
                                    self.args.online)
    num_probes = 0

    while not self._done.is_set():
      if self.CheckCondition():
        break
      if self.args.retries is not None:
        # retries is set.
        num_probes += 1
        self._ui.SetHTML(_PROBE_TIMES_MSG(num_probes, self.args.retries),
                         id=_PROBE_TIMES_ID)
        if self.args.retries < num_probes:
          self.fail('Failed after probing %d times' % num_probes)
      # Prevent busy polling.
      time.sleep(self.args.polling_period_secs)

  def runTest(self):
    self._ui.RunInBackground(self._runTest)
    self._ui.Run(on_finish=self.Done)
