# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module for running factory install on a DUT with a USB disk on a servo."""

from __future__ import print_function

import logging
import os
import re
import socket
import time

import factory_common   # pylint: disable=W0611
from cros.factory.factory_flow import servo
from cros.factory.factory_flow.common import (
    board_cmd_arg, bundle_dir_cmd_arg, dut_hostname_cmd_arg, FactoryFlowCommand)
from cros.factory.hacked_argparse import CmdArg
from cros.factory.test import utils
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import ssh_utils
from cros.factory.utils import sys_utils

# pylint: disable=W0612, F0401


INSTALL_METHOD = utils.Enum(['install_shim', 'usb_image'])


class USBInstallError(Exception):
  """USB install error."""
  pass


class USBInstall(FactoryFlowCommand):
  """Runs factory install on a DUT with a USB disk on a servo."""
  args = [
      board_cmd_arg,
      bundle_dir_cmd_arg,
      dut_hostname_cmd_arg,
      CmdArg('--method', choices=INSTALL_METHOD,
             default=INSTALL_METHOD.install_shim,
             help=('the install method to use with the USB disk '
                   '(default: %(default)s)')),
      CmdArg('--servo-host', default=net_utils.LOCALHOST,
             help='IP of the servo host (default: %(default)s)'),
      CmdArg('--servo-port', type=int, default=9999,
             help='port of servod (default: %(default)s)'),
      CmdArg('--servo-serial', help='serial number of the servo board'),
      CmdArg('--flash-ec', action='store_true', default=False,
             help=('also flashes EC using servo; note that this does not work '
                   'when multiple servo boards are attached to the servo host '
                   '(default: %(default)s)')),
      CmdArg('--no-wait', dest='wait', action='store_false',
             help='do not wait for factory install to complete'),
      CmdArg('--wait-timeout-secs', type=int, default=1200,
             help='the duration in seconds to wait before failing the command'),
  ]

  servo = None
  ec = None
  # Path to the image binary to load onto USB disk.
  usb_image_path = None

  def Init(self):
    # Do autotest imports here to stop it from messing around with logging
    # settings.
    import autotest_common
    from autotest_lib.server.cros.servo import chrome_ec
    self.servo = servo.Servo(
        self.options.board.short_name, self.options.servo_host,
        port=self.options.servo_port, serial=self.options.servo_serial)
    self.ec = chrome_ec.ChromeEC(self.servo)

  def TearDown(self):
    if self.servo:
      self.servo.TearDown()

  def Run(self):
    self.PrepareImage()
    self.FlashFirmware()
    self.InstallWithServo()
    if self.options.wait:
      self.WaitForInstallToFinish()

  def PrepareImage(self):
    """Prepares the image to load onto the USB disk on servo.

    Creates USB disk image with make_factory_package if --disk-image is
    specified.

    Raises:
      USBInstallError if any required files are missing.
    """
    # Search for factory shim.
    install_shim_path = self.LocateUniquePath(
        'factory instsall shim',
        [os.path.join(self.options.bundle, 'factory_shim', name)
         for name in ('factory_install_shim.bin', 'chromeos_*.bin')])

    if self.options.method == INSTALL_METHOD.install_shim:
      logging.info('\n'.join(['Found the following binaries for %s:'
                              'Factory install shim: %s']),
                    self.options.board.full_name, install_shim_path)
      self.usb_image_path = install_shim_path

    else:   # Using INSTALL_METHOD.usb_image.
      # Search for release image (FSI).
      release_image_path = self.LocateUniquePath(
          'release image',
          [os.path.join(self.options.bundle, 'release', '*.bin')])

      # Search for factory test image.
      factory_image_path = os.path.join(
          self.options.bundle, 'factory_test', 'chromiumos_factory_image.bin')
      if not os.path.exists(factory_image_path):
        raise USBInstallError('Unable to locate factory test image')

      # Search for HWID bundle shellball.
      hwid_bundle_path = os.path.join(
          self.options.bundle, 'hwid',
          'hwid_v3_bundle_%s.sh' % self.options.board.short_name.upper())
      if not os.path.exists(hwid_bundle_path):
        raise USBInstallError('Unable to locate HWID bundle')

      # The output USB disk image path.
      usb_image_path = os.path.join(
          self.options.bundle, 'usb_image.bin')

      make_factory_package = [
          os.path.join(self.options.bundle, 'factory_setup',
                       'make_factory_package.sh'),
          '--board', self.options.board.full_name,
          '--install_shim', install_shim_path,
          '--release', release_image_path,
          '--factory', factory_image_path,
          '--hwid_updater', hwid_bundle_path,
          '--usbimg', usb_image_path,
      ]

      # Use custom firmware updater if found.
      firmware_updater_path = os.path.join(
          self.options.bundle, 'firmware', 'chromeos-firmwareupdate')
      if os.path.exists(firmware_updater_path):
        make_factory_package += ['--firmware_updater', firmware_updater_path]
      else:
        firmware_updater_path = None

      logging.info('\n'.join(['Found the following binaries for %s:'
                              'Factory install shim: %s'
                              'Release image: %s'
                              'Factory test image: %s'
                              'HWID bundle: %s'
                              'Firmware updater: %s']),
                   self.options.board.full_name, install_shim_path,
                   release_image_path, factory_image_path, hwid_bundle_path,
                   firmware_updater_path)
      process_utils.Spawn(make_factory_package, check_call=True, log=True)
      self.usb_image_path = usb_image_path

  def FlashFirmware(self):
    """Flashes the firmware and EC extracted from release image onto DUT."""
    release_image_path = self.LocateUniquePath(
        'release image',
        [os.path.join(self.options.bundle, 'release', '*.bin')])
    firmware_extractor = os.path.join(
        self.options.bundle, 'factory_setup', 'extract_firmware_updater.sh')
    logging.info('Extracting firmware and EC from release image %s',
                 release_image_path)
    with file_utils.TempDirectory(prefix='firmware_updater') as temp_dir:
      # Extract firmware updater from release image.
      process_utils.Spawn([firmware_extractor, '-i', release_image_path,
                           '-o', temp_dir], log=True, check_call=True)
      # Extract bios.bin and ec.bin from the firmawre updater.
      firmware_updater = os.path.join(temp_dir, 'chromeos-firmwareupdate')
      process_utils.Spawn([firmware_updater, '--sb_extract', temp_dir],
                          log=True, check_call=True)
      # Flash the firmware and EC with servo.
      servo_version = self.servo.get_version()
      bios_path = os.path.join(temp_dir, 'bios.bin')
      logging.info('Flashing firmware %s on DUT %s with servo %s',
                   bios_path, self.options.dut, servo_version)
      with file_utils.FileLock(servo.FLASHROM_LOCK_FILE,
                               timeout_secs=servo.FLASHROM_LOCK_TIMEOUT):
        self.servo.program_bios(bios_path)
      if self.options.flash_ec:
        ec_path = os.path.join(temp_dir, 'ec.bin')
        logging.info('Flashing EC %s on DUT %s with servo %s',
                     ec_path, self.options.dut, servo_version)
        self.servo.program_ec(ec_path)

  def InstallWithServo(self):
    """Loads the image to USB disk and reboots the DUT into recovery mode."""
    logging.info('Loading image %s onto USB disk to run factory install '
                 'on DUT %s', self.usb_image_path, self.options.dut)
    # The API self.servo.install_recovery_image does not seem to work on all
    # boards; manually set EC recovery boot event here.
    import autotest_common
    from autotest_lib.server.cros.servo import chrome_ec
    self.servo.image_to_servo_usb(image_path=self.usb_image_path)
    self.servo.get_power_state_controller().cold_reset()
    self.ec.reboot('ap-off')
    # pylint: disable=W0212
    time.sleep(self.servo.get_power_state_controller()._EC_RESET_DELAY)
    self.ec.set_hostevent(chrome_ec.HOSTEVENT_KEYBOARD_RECOVERY)
    self.servo.power_short_press()
    self.servo.switch_usbkey('dut')

  def WaitForInstallToFinish(self):
    """Selects install action and waits for factory install to finish."""
    def CheckAndPressI():
      try:
        socket.create_connection((self.options.dut, 22)).close()
        return True
      except socket.error:
        self.ec.key_press('i')
        self.ec.key_press('<enter>')
        return False

    logging.info(('Waiting for factory install to complete on DUT %s '
                  'by trying to connect to port 22 on it'),
                 self.options.dut)
    utils.WaitFor(CheckAndPressI, timeout_secs=self.options.wait_timeout_secs,
                  poll_interval=5)
    logging.info('SSH port (22) on DUT %s is up', self.options.dut)

    def GetImageVersion(lsb_release, label):
      match = re.search(
          '^CHROMEOS_RELEASE_VERSION=(.+)$', lsb_release, re.MULTILINE)
      if not match:
        raise USBInstallError('Unable to get image veriosn from %s' % label)
      return match.group(1)

    factory_image_path = os.path.join(self.options.bundle, 'factory_test',
                                      'chromiumos_factory_image.bin')
    with sys_utils.MountPartition(factory_image_path, 3) as mount_point:
      image_version_in_bundle = GetImageVersion(
          open(os.path.join(mount_point, 'etc', 'lsb-release')).read(),
          'bundle')
    lsb_release_on_dut = ssh_utils.SpawnSSHToDUT(
        [self.options.dut, 'cat', '/etc/lsb-release'],
        log=True, check_output=True).stdout_data
    image_version_on_dut = GetImageVersion(lsb_release_on_dut, 'DUT')
    if image_version_on_dut != image_version_in_bundle:
      raise USBInstallError(
          'Expect image version to be %s on DUT but found %s' %
          (image_version_in_bundle, image_version_on_dut))
    else:
      print('USB install completed on DUT %s' % self.options.dut)
