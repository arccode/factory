# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs chromeos-firmwareupdate to force update EC/firmware."""

import logging
import os
import subprocess
import threading
import unittest

from cros.factory.system import vpd
from cros.factory.test.args import Arg
from cros.factory.test.event import Event
from cros.factory.test.test_ui import Escape, MakeLabel, UI
from cros.factory.test.ui_templates import OneScrollableSection
from cros.factory.utils.process_utils import Spawn

_TEST_TITLE = MakeLabel('Update Firmware', u'更新韧体')
_CSS = '#state {text-align:left;}'


class UpdateFirmwareTest(unittest.TestCase):
  ARGS = [
    Arg('firmware_updater', str, 'Full path of chromeos-firmwareupdate.',
        default='/usr/local/factory/board/chromeos-firmwareupdate'),
    Arg('update_ec', bool, 'Update EC firmware.', default=True),
    Arg('update_pd', bool, 'Update PD firmware.', default=True),
    Arg('update_main', bool, 'Update main firmware.', default=True),
    Arg('apply_customization_id', bool,
        'Update root key based on the customization_id stored in VPD.',
        default=False, optional=True),
  ]

  def setUp(self):
    self.assertTrue(os.path.isfile(self.args.firmware_updater),
                    msg='%s is missing.' % self.args.firmware_updater)
    self._ui = UI()
    self._template = OneScrollableSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._ui.AppendCSS(_CSS)

  def UpdateFirmware(self):
    """Runs firmware updater.

    While running updater, it shows updater activity on factory UI.
    """
    # Remove /tmp/chromeos-firmwareupdate-running if the process
    # doesn't seem to be alive anymore.  (http://crosbug.com/p/15642)
    LOCK_FILE = '/tmp/chromeos-firmwareupdate-running'
    if os.path.exists(LOCK_FILE):
      process = Spawn(['pgrep', '-f', 'chromeos-firmwareupdate'],
                      call=True, log=True, read_stdout=True)
      if process.returncode == 0:
        # Found a chromeos-firmwareupdate alive.
        self._ui.Fail('Lock file %s is present and firmware update already '
                      'running (PID %s)' % (
            LOCK_FILE, ', '.join(process.stdout_data.split())))
        return
      logging.warn('Removing %s', LOCK_FILE)
      os.unlink(LOCK_FILE)

    if self.args.apply_customization_id:
      customization_id = vpd.ro.get("customization_id")
      if customization_id is None:
        self._ui.Fail('Customization_id not found in VPD.')
        return
      if not self.args.update_main:
        self._ui.Fail(
            'Main firmware must be updated when apply customization_id.')
        return
      p = Spawn(
        [self.args.firmware_updater, '--force', '--factory',
         '--customization_id', customization_id, '--update_main',
         '--update_ec' if self.args.update_ec else '--noupdate_ec',],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, log=True)
    else:
      p = Spawn(
        [self.args.firmware_updater, '--force', '--factory',
         '--update_ec' if self.args.update_ec else '--noupdate_ec',
         '--update_pd' if self.args.update_pd else '--noupdate_pd',
         '--update_main' if self.args.update_main else '--noupdate_main',],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, log=True)
    for line in iter(p.stdout.readline, ''):
      logging.info(line.strip())
      self._template.SetState(Escape(line), append=True)

    # Updates system info so EC and Firmware version in system info box
    # are correct.
    self._ui.event_client.post_event(Event(Event.Type.UPDATE_SYSTEM_INFO))

    if p.poll() != 0:
      self._ui.Fail('Firmware update failed: %d.' % p.returncode)
    else:
      self._ui.Pass()

  def runTest(self):
    threading.Thread(target=self.UpdateFirmware).start()
    self._ui.Run()
