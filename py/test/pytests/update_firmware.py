# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs chromeos-firmwareupdate to force update Main(AP)/EC/PD firmwares.

Description
-----------
This test runs firmware updater from local storage or downloaded from remote
factory server to update Main(AP)/EC/PD firmware contents.

Test Procedure
--------------
This is an automatic test that doesn't need any user interaction.

1. If argument ``download_from_server`` is set to True, this test will try to
   download firmware updater from factory server and ignore argument
   ``firmware_updater``. If firmware update is not available, this test will
   just pass and exit. If argument ``download_from_server`` is set to False and
   the path indicated by argument ``firmware_updater`` doesn't exist, this test
   will abort.
2. This test will fail if there is another firmware updater running in the same
   time. Else, start running firmware updater.
3. If firmware updater finished successfully, this test will pass.
   Otherwise, fail.

Dependency
----------
- If argument ``download_from_server`` is set to True, firmware updater needs to
  be available on factory server. If ``download_from_server`` is set to False,
  firmware updater must be prepared in the path that argument
  ``firmware_updater`` indicated.

Examples
--------
To update all firmwares using local firmware updater, which is located in
'/usr/local/factory/board/chromeos-firmwareupdate'::

  {
    "pytest_name": "update_firmware"
  }

To update only RW Main(AP) firmware using remote firmware updater::

  {
    "pytest_name": "update_firmware",
    "args": {
      "download_from_server": true,
      "rw_only": true,
      "host_only": true
    }
  }

Not to update firmware if the version is the same with current one
in the DUT::

  {
    "pytest_name": "update_firmware",
    "args": {
      "force_update": false
    }
  }
"""

import contextlib
import logging
import os
import tempfile

from cros.factory.device import device_utils
from cros.factory.test.env import paths
from cros.factory.test import event
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.utils import update_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils

_FIRMWARE_UPDATER_NAME = 'chromeos-firmwareupdate'
_FIRMWARE_RELATIVE_PATH = 'usr/sbin/chromeos-firmwareupdate'



class NoUpdatesException(Exception):
  pass


class UpdateFirmwareTest(test_case.TestCase):
  ARGS = [
      Arg('firmware_updater', str, 'Full path of %s.' % _FIRMWARE_UPDATER_NAME,
          default=paths.FACTORY_FIRMWARE_UPDATER_PATH),
      Arg('rw_only', bool, 'Update only RW firmware', default=False),
      # Updating only EC/PD is not supported.
      Arg('host_only', bool, 'Update only host (AP, BIOS) firmware.',
          default=False),
      Arg('download_from_server', bool, 'Download firmware updater from server',
          default=False),
      Arg('from_release', bool, 'Find the firmware from release rootfs.',
          default=False),
      Arg('force_update', bool,
          'force to update firmware even if the version is the same.',
          default=True)
  ]

  ui_class = test_ui.ScrollableLogUI

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()

  def DownloadFirmware(self, force_update, target_path):
    """Downloads firmware updater from server."""
    updater = update_utils.Updater(update_utils.COMPONENTS.firmware)
    if not updater.IsUpdateAvailable():
      logging.warning('No firmware updater available on server.')
      return False

    rw_version = self._dut.info.firmware_version
    ro_version = self._dut.info.ro_firmware_version

    current_version = 'ro:%s;rw:%s' % (ro_version, rw_version)

    if not updater.IsUpdateAvailable(
        current_version, match_method=update_utils.MATCH_METHOD.substring):
      logging.info('Your firmware is already in same version as server (%s)',
                   updater.GetUpdateVersion())
      if not force_update:
        return False

    updater.PerformUpdate(destination=target_path)
    os.chmod(target_path, 0o755)
    return True

  def UpdateFirmware(self):
    """Runs firmware updater.

    While running updater, it shows updater activity on factory UI.
    """
    # Remove /tmp/chromeos-firmwareupdate-running if the process
    # doesn't seem to be alive anymore.  (http://crosbug.com/p/15642)
    LOCK_FILE = '/tmp/%s-running' % _FIRMWARE_UPDATER_NAME
    if os.path.exists(LOCK_FILE):
      process = process_utils.Spawn(['pgrep', '-f', _FIRMWARE_UPDATER_NAME],
                                    call=True, log=True, read_stdout=True)
      if process.returncode == 0:
        # Found a chromeos-firmwareupdate alive.
        self.FailTask('Lock file %s is present and firmware update already '
                      'running (PID %s)' %
                      (LOCK_FILE, ', '.join(process.stdout_data.split())))
        return
      logging.warning('Removing %s', LOCK_FILE)
      os.unlink(LOCK_FILE)

    command = [self.args.firmware_updater, '--force']
    if self.args.host_only:
      command += ['--host_only']
    if self.args.rw_only:
      command += ['--mode=recovery', '--wp=1']
    else:
      command += ['--mode=factory']

    returncode = self.ui.PipeProcessOutputToUI(command)

    # Updates system info so EC and Firmware version in system info box
    # are correct.
    self.event_loop.PostEvent(event.Event(event.Event.Type.UPDATE_SYSTEM_INFO))

    self.assertEqual(returncode, 0, 'Firmware update failed: %d.' % returncode)

  def runTest(self):
    # Either download_from_server or from_release can be True.
    self.assertFalse(self.args.download_from_server and self.args.from_release)

    @contextlib.contextmanager
    def GetUpdater():
      if self.args.download_from_server:
        # The temporary folder will not be removed after this test finished
        # for the convenient of debugging.
        temp_path = os.path.join(
            tempfile.mkdtemp(prefix='test_fw_update_'), _FIRMWARE_UPDATER_NAME)
        if self.DownloadFirmware(
            self.args.force_update, temp_path):
          yield temp_path
        else:
          raise NoUpdatesException
      elif self.args.from_release:
        with sys_utils.MountPartition(
            self._dut.partitions.RELEASE_ROOTFS.path, dut=self._dut) as root:
          yield os.path.join(root, _FIRMWARE_RELATIVE_PATH)
      else:
        yield self.args.firmware_updater

    try:
      with GetUpdater() as updater_path:
        self.assertTrue(
            os.path.isfile(updater_path), msg='%s is missing.' % updater_path)
        self.args.firmware_updater = updater_path
        self.UpdateFirmware()
    except NoUpdatesException:
      pass
