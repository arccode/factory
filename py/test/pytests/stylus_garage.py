# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests stylus garage detection functionality.

Description
-----------
Verifies if stylus garage is functional by asking operator to insert and remove
the stylus.

Test Procedure
--------------
1. Operator inserts the stylus into the stylus garage.
2. Operator removes the stylus from the stylus garage.

Dependency
----------
- Based on Linux evdev.

Examples
--------
The minimal working example::

  {
    "pytest_name": "stylus_garage"
  }

A test group tests both the stylus and the garage. A similar group called
StylusAndGarage is defined in generic_common.test_list.json::

  {
    "subtests": [
      {
        "pytest_name": "stylus_garage",
        "args": {
          "target_state": "ejected"
        }
      },
      {
        "pytest_name": "stylus"
      },
      {
        "pytest_name": "stylus_garage",
        "args": {
          "target_state": "inserted"
        }
      }
    ]
  }
"""

from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test.utils import evdev_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import type_utils

from cros.factory.external import evdev


STYLUS_STATUS = type_utils.Enum(['inserted', 'ejected'])


class StylusGarageTest(test_case.TestCase):
  """Stylus garage detection factory test."""
  ARGS = [
      Arg('timeout_secs', int, 'Timeout value for the test.',
          default=180),
      Arg('device_filter', (int, str),
          'Event ID or name for evdev. None for auto probe.',
          default=None),
      Arg('garage_is_stylus', bool, 'Some garages are not stylus devices. Set '
          'this flag to False to skip the check.', default=True),
      Arg('target_state', STYLUS_STATUS, 'The test passes when reaches the '
          'target state. If not specified, pass after an insertion and then '
          'an ejection or an ejection and then an insertion.', default=None),
  ]

  def setUp(self):
    filters = []
    if self.args.device_filter is not None:
      filters.append(self.args.device_filter)
    if self.args.garage_is_stylus:
      filters.append(evdev_utils.IsStylusDevice)
    self.event_dev = evdev_utils.FindDevice(*filters)
    self.ui.ToggleTemplateClass('font-large', True)
    self._current_status = None
    self.dispatcher = evdev_utils.InputDeviceDispatcher(
        self.event_dev, self.event_loop.CatchException(self.HandleEvent))

  def tearDown(self):
    self.dispatcher.close()

  def HandleEvent(self, event):
    if (event.type == evdev.ecodes.EV_SW and
        event.code == evdev.ecodes.SW_PEN_INSERTED):
      if event.value == 1:  # Stylus inserted
        if self._current_status == STYLUS_STATUS.inserted:
          self.FailTask('Consecutive insertion')
        elif self._current_status == STYLUS_STATUS.ejected:
          self.PassTask()
        self._current_status = STYLUS_STATUS.inserted
      elif event.value == 0:  # Stylus ejected
        if self._current_status == STYLUS_STATUS.inserted:
          self.PassTask()
        elif self._current_status == STYLUS_STATUS.ejected:
          self.FailTask('Consecutive ejection')
        self._current_status = STYLUS_STATUS.ejected

      if self._current_status == self.args.target_state:
        self.PassTask()
      elif self._current_status == STYLUS_STATUS.inserted:
        self.ui.SetState(_('Remove stylus'))
      else:
        self.ui.SetState(_('Insert stylus'))

  def runTest(self):
    self.ui.SetState(_('Insert or Remove stylus'))
    self.dispatcher.StartDaemon()
    self.ui.StartFailingCountdownTimer(self.args.timeout_secs)

    self.WaitTaskEnd()
