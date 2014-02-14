# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module for running factory install on a DUT with a USB disk on a servo."""

import logging
import os
import socket
import time

import factory_common   # pylint: disable=W0611
from cros.factory.factory_flow.common import (
    board_cmd_arg, bundle_dir_cmd_arg, dut_hostname_cmd_arg, FactoryFlowCommand)
from cros.factory.hacked_argparse import CmdArg
from cros.factory.test import utils
from cros.factory.utils import process_utils

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
      CmdArg('--servo-host', default='localhost',
             help='IP of the servo host (default: %(default)s)'),
      CmdArg('--no-wait', dest='wait', action='store_false',
             help='do not wait for factory install to complete'),
      CmdArg('--wait-timeout-secs', type=int, default=600,
             help='the duration in seconds to wait before failing the command'),
  ]

  board = None
  servo = None
  ec = None
  # Path to the image binary to load onto USB disk.
  usb_image_path = None

  def Init(self):
    # Do autotest imports here to stop it from messing around with logging
    # settings.
    import autotest_common
    from autotest_lib.server import hosts
    from autotest_lib.server.cros.servo import chrome_ec
    from autotest_lib.server.cros.servo import servo
    self.servo = servo.Servo(
        hosts.ServoHost(servo_host=self.options.servo_host))
    self.ec = chrome_ec.ChromeEC(self.servo)

  def Run(self):
    self.PrepareImage()
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
