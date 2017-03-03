# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs chromeos-firmwareupdate to force update EC/firmware."""

import logging
import os
import subprocess
import threading
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.env import paths
from cros.factory.test import event
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils

_TEST_TITLE = i18n_test_ui.MakeI18nLabel('Update Firmware')
_CSS = '#state {text-align:left;}'


class UpdateFirmwareTest(unittest.TestCase):
  ARGS = [
      Arg('firmware_updater', str, 'Full path of chromeos-firmwareupdate.',
          default='/usr/local/factory/board/chromeos-firmwareupdate'),
      Arg('rw_only', bool, 'Update only RW firmware', default=False),
      Arg('update_ec', bool, 'Update EC firmware.', default=True),
      Arg('update_pd', bool, 'Update PD firmware.', default=True),
      Arg('umpire', bool, 'Update firmware updater from Umpire server',
          default=False),
      Arg('update_main', bool, 'Update main firmware.', default=True),
      Arg('apply_customization_id', bool,
          'Update root key based on the customization_id stored in VPD.',
          default=False, optional=True),
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.just_pass = False
    if self.args.umpire:
      if shopfloor.get_firmware_updater():
        self.args.firmware_updater = paths.FIRMWARE_UPDATER_PATH
      else:
        self.just_pass = True
    else:
      self.assertTrue(os.path.isfile(self.args.firmware_updater),
                      msg='%s is missing.' % self.args.firmware_updater)
    self._ui = test_ui.UI()
    self._template = ui_templates.OneScrollableSection(self._ui)
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
      process = process_utils.Spawn(['pgrep', '-f', 'chromeos-firmwareupdate'],
                                    call=True, log=True, read_stdout=True)
      if process.returncode == 0:
        # Found a chromeos-firmwareupdate alive.
        self._ui.Fail('Lock file %s is present and firmware update already '
                      'running (PID %s)' % (
                          LOCK_FILE, ', '.join(process.stdout_data.split())))
        return
      logging.warn('Removing %s', LOCK_FILE)
      os.unlink(LOCK_FILE)

    command = [self.args.firmware_updater, '--force',
               '--update_main' if self.args.update_main else '--noupdate_main',
               '--update_ec' if self.args.update_ec else '--noupdate_ec',
               '--update_pd' if self.args.update_pd else '--noupdate_pd']
    if self.args.rw_only:
      command += ['--mode=recovery', '--wp=1']
    else:
      command += ['--mode=factory']

    if self.args.apply_customization_id:
      customization_id = self.dut.vpd.ro.get('customization_id')
      if customization_id is None:
        self._ui.Fail('Customization_id not found in VPD.')
        return
      if not self.args.update_main:
        self._ui.Fail(
            'Main firmware must be updated when apply customization_id.')
        return
      command += ['--customization_id', customization_id]

    p = process_utils.Spawn(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, log=True)
    for line in iter(p.stdout.readline, ''):
      logging.info(line.strip())
      self._template.SetState(test_ui.Escape(line), append=True)

    # Updates system info so EC and Firmware version in system info box
    # are correct.
    self._ui.event_client.post_event(
        event.Event(event.Event.Type.UPDATE_SYSTEM_INFO))

    if p.poll() != 0:
      self._ui.Fail('Firmware update failed: %d.' % p.returncode)
    else:
      self._ui.Pass()

  def runTest(self):
    if self.just_pass:
      return
    threading.Thread(target=self.UpdateFirmware).start()
    self._ui.Run()
