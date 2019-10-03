# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Probes SIM card tray

Detects SIM card tray by GPIO.

Args:
  tray_already_present:SIM card tray is in machine before test starts.
  tray_detection_gpio: SIM card tray detection gpio number.
"""

import logging
import os

from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


_INSERT_CHECK_PERIOD_SECS = 1
_GPIO_PATH = '/sys/class/gpio'

_TrayState = type_utils.Enum(['INSERTED', 'REMOVED'])


class ProbeTrayException(Exception):
  pass


class ProbeSimCardTrayTest(test_case.TestCase):
  """Test to probe sim card tray.

  Usage examples:
    1.Just check presence or absence:
      tray_already_present=True/False
    2.Ask user to insert tray:
      tray_already_present=False,
      insert=True,
      only_check_presence=False
    3.Ask user to remove tray:
      tray_already_present=True,
      remove=True,
      only_check_presence=False
    4.Ask user to insert then remove tray.
      tray_already_present=False,
      insert=True,
      remove=True,
      only_check_presence=False
    5.Ask user to remove then insert tray.
      tray_already_present=True,
      insert=True,
      remove=True,
      only_check_presence=False
  """
  ARGS = [
      Arg('timeout_secs', int,
          'timeout in seconds for insertion/removal', default=10),
      Arg('tray_already_present', bool,
          'SIM card tray is in machine before test starts', default=False),
      Arg('tray_detection_gpio', int,
          'SIM card tray detection gpio number', default=159),
      Arg('insert', bool, 'Check sim card tray insertion', default=False),
      Arg('remove', bool, 'Check sim card tray removal', default=False),
      Arg('only_check_presence', bool,
          'Only checks sim card tray presence matches tray_already_present. '
          'No user interaction required', default=True),
      Arg('gpio_active_high', bool, 'Whether GPIO is active high.',
          default=True)]

  def setUp(self):
    self._detection_gpio_path = os.path.join(
        _GPIO_PATH, 'gpio%d' % self.args.tray_detection_gpio)

  def runTest(self):
    self.ExportGPIO()
    self.CheckPresence()

    if self.args.only_check_presence:
      return

    self.ui.StartFailingCountdownTimer(self.args.timeout_secs)

    if self.args.tray_already_present:
      self.assertTrue(self.args.remove, 'Must set remove to Ture '
                      'since tray_already_present is True')
      self.WaitTrayRemoved()
      if self.args.insert:
        self.WaitTrayInserted()
    else:
      self.assertTrue(self.args.insert, 'Must set insert to Ture '
                      'since tray_already_present is False')
      self.WaitTrayInserted()
      if self.args.remove:
        self.WaitTrayRemoved()

  def ExportGPIO(self):
    """Exports GPIO of tray detection pin.

    Raises:
      ProbeTrayException if gpio can not be exported.
    """
    if os.path.exists(self._detection_gpio_path):
      logging.info('gpio %s was exported before', self._detection_gpio_path)
      return

    export_path = os.path.join(_GPIO_PATH, 'export')
    try:
      file_utils.WriteFile(export_path, str(self.args.tray_detection_gpio),
                           log=True)
    except IOError:
      logging.exception('Can not write %s into %s',
                        self.args.tray_detection_gpio, export_path)
      raise ProbeTrayException('Can not export detection gpio %s' %
                               self.args.tray_detection_gpio)

    direction_path = os.path.join(self._detection_gpio_path, 'direction')
    try:
      file_utils.WriteFile(direction_path, 'out', log=True)
    except IOError:
      logging.exception('Can not write "out" into %s', direction_path)
      raise ProbeTrayException('Can set detection gpio direction to out')

  def GetDetection(self):
    """Returns tray status _TrayState.INSERTED or _TrayState.REMOVED."""
    value_path = os.path.join(self._detection_gpio_path, 'value')
    lines = file_utils.ReadLines(value_path)
    if not lines:
      raise ProbeTrayException('Can not get detection result from %s' %
                               value_path)

    ret = lines[0].strip()
    if ret not in ['0', '1']:
      raise ProbeTrayException('Get invalid detection %s from %s' %
                               (ret, value_path))

    if self.args.gpio_active_high:
      return _TrayState.INSERTED if ret == '1' else _TrayState.REMOVED
    return _TrayState.INSERTED if ret == '0' else _TrayState.REMOVED

  def CheckPresence(self):
    self.assertEqual(
        self.args.tray_already_present,
        self.GetDetection() == _TrayState.INSERTED,
        ('Unexpected tray %s. Please %s SIM card tray and retest.' %
         (('absence', 'insert')
          if self.args.tray_already_present else ('presence', 'remove'))))

  def WaitTrayInserted(self):
    self.ui.SetState(_('Please insert the SIM card tray'))
    self.WaitTrayState(_TrayState.INSERTED)

  def WaitTrayRemoved(self):
    self.ui.SetState(_('Detected! Please remove the SIM card tray'))
    self.WaitTrayState(_TrayState.REMOVED)

  def WaitTrayState(self, state):
    logging.info('wait for %s event', state)

    while True:
      if self.GetDetection() == state:
        logging.info('%s detected', state)
        session.console.info('%s detected', state)
        return
      self.Sleep(_INSERT_CHECK_PERIOD_SECS)
