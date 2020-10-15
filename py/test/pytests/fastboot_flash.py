# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs fastboot flash to update images on the device."""

import os
import re
import subprocess

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils


_RE_SENDING_TIME = re.compile(
    r'^sending.*\(([0-9]+) KB\).*\nOKAY\s*\[\s*([0-9]+\.[0-9]+)s\]',
    re.MULTILINE)


class FastbootFlash(test_case.TestCase):
  """Flash images using fastboot with the give image files.

  The device will be rebooted into fastboot, and 'fastboot flash' will be
  applied to flash the given image files.

  This test can also be used to verify the throughput of USB in device mode
  by checking the flash speed.
  """
  ARGS = [
      Arg('image_dir', str, 'Full path of the dir that contains images.',
          default='/usr/local/factory/images/android'),
      Arg('images', list, 'list of images to be updated. Each item should be '
          '[partition, image_name]. '
          'E.g., [["boot", "boot.img"], ["system", "system.img"]]. '
          'The images will be flashed in order of the list.'),
      Arg('expected_throughput', int, 'Expected throughput minimum when '
          'sending the image files, in unit of byte/sec. This can be used to '
          'cover USB device mode throughput testing.', default=0),
      Arg('command_to_fastboot', str, 'Command used to switch the device '
          'into fastboot mode.', default='adb reboot-bootloader'),
      Arg('command_to_check_device', str, 'Command to check device boot '
          'normally.', default='timeout 60 adb wait-for-device')
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()

  def IsDeviceInFastboot(self):
    """Check if the device is already in fastboot mode."""

    return bool(process_utils.SpawnOutput(['fastboot', 'devices'],
                                          check_call=True))

  def BootToFastboot(self):
    """Reboot device into fastboot mode if needed."""
    # Check if the device is in fastboot mode now.
    if self.IsDeviceInFastboot():
      return

    self.ui.SetState(_('Switching device into fastboot.'))

    process_utils.Spawn(self.args.command_to_fastboot,
                        shell=True, check_call=True, log=True)
    sync_utils.PollForCondition(
        poll_method=self.IsDeviceInFastboot,
        timeout_secs=60,
        condition_name='WaitForFastboot')

  def BootToNormal(self):
    """Reboot the device back to normal mode from fastboot mode."""
    self.ui.SetState(_('Switching device back to normal mode.'))

    process_utils.Spawn(['fastboot', 'reboot'], check_call=True, log=True)
    process_utils.Spawn(self.args.command_to_check_device, shell=True,
                        check_call=True, log=True)

  def FlashAll(self):
    def _CheckThroughput(fastboot_output):
      """Check throughput using the output of fastboot flash.

      An example of the typical output from fastboot flash:
      erasing 'system'...
      OKAY [  0.643s]
      sending sparse 'system' (524232 KB)...
      OKAY [ 15.303s]
      writing 'system'...
      OKAY [ 14.853s]
      sending sparse 'system' (418948 KB)...
      OKAY [ 12.181s]
      writing 'system'...
      OKAY [ 11.248s]
      finished. total time: 54.229s
      """
      data = _RE_SENDING_TIME.findall(fastboot_output)
      if not data:
        self.fail('Incorrect fastboot output. %s' % fastboot_output)

      for size_time in data:
        # Get the size in byte.
        size = int(size_time[0]) * 1024
        time = float(size_time[1])
        throughput = size / time

        # If the size is too small, ignore the checking.
        if size < 1024 * 1024:
          continue
        session.console.info(
            'Flash %d bytes in %.1f sec (%.1f bytes/s).',
            size, time, throughput)
        self.assertGreater(throughput, self.args.expected_throughput)

    def _FlashImage(partition, file_path):
      """Flash image to the given partition."""
      if not os.path.exists(file_path):
        self.fail('Not able to find required image file %s' % file_path)
      self.ui.SetState(
          _('Flashing {file} to {partition}.',
            file=file_path,
            partition=partition))

      msg = process_utils.SpawnOutput(
          ['fastboot', 'flash', partition, file_path],
          stderr=subprocess.STDOUT, check_call=True, log=True)
      _CheckThroughput(msg)

    for image in self.args.images:
      _FlashImage(image[0], os.path.join(self.args.image_dir, image[1]))

  def runTest(self):
    self.BootToFastboot()
    self.FlashAll()
    self.BootToNormal()
