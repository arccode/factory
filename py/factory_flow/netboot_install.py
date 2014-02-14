# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module for running factory install on a DUT with netboot."""

import logging
import os
import re
import socket

import factory_common   # pylint: disable=W0611
from cros.factory.factory_flow.common import (
    board_cmd_arg, bundle_dir_cmd_arg, dut_hostname_cmd_arg, FactoryFlowCommand)
from cros.factory.hacked_argparse import CmdArg
from cros.factory.test import utils
from cros.factory.utils import ssh_utils


class NetbootInstallError(Exception):
  """Netboot install error."""
  pass


class NetbootInstall(FactoryFlowCommand):
  """Runs factory install on a DUT with netboot."""
  args = [
      board_cmd_arg,
      bundle_dir_cmd_arg,
      dut_hostname_cmd_arg,
      CmdArg('--flash-method', choices=['ssh', 'servo'], default='ssh',
             help=('how to flash netboot firmware and EC '
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
  netboot_firmware_path = None
  netboot_ec_path = None

  def Init(self):
    """Initializes servo and locates netboot firmware and EC.

    Raises:
      NetbootInstallError if netboot firmware or EC cannot be located.
    """
    if self.options.flash_method == 'servo':
      # Do autotest imports here to stop it from messing around with logging
      # settings.
      # pylint: disable=W0612, F0401
      import autotest_common
      from autotest_lib.server import hosts
      from autotest_lib.server.cros.servo import servo
      self.servo = servo.Servo(
          hosts.ServoHost(servo_host=self.options.servo_host))

    self.netboot_firmware_path = self.LocateUniquePath(
        'netboot firmware',
        [os.path.join(self.options.bundle, 'netboot_firmware', name)
         for name in ('nv_image-*.bin', 'image.net.bin')])

    self.netboot_ec_path = os.path.join(self.options.bundle, 'netboot_firmware',
                                        'ec.bin')
    if not os.path.exists(self.netboot_ec_path):
      raise NetbootInstallError('Unable to locate netboot EC')
    logging.info('\n'.join(['Found the following binaries for %s:'
                            'Netboot firmware: %s'
                            'Netboot EC: %s']),
                 self.options.board.full_name, self.netboot_firmware_path,
                 self.netboot_ec_path)

  def Run(self):
    if self.options.flash_method == 'ssh':
      self.FlashFirmwareWithSSH()
    else:
      self.FlashFirmwareWithServo()
    if self.options.wait:
      self.WaitForInstallToFinish()

  def FlashFirmwareWithServo(self):
    """Flashes netboot firmware and EC with servo board."""
    servo_version = self.servo.get_version()

    logging.info('Flashing netboot firmware %s on DUT %s with servo %s',
                 self.netboot_firmware_path, self.options.dut, servo_version)
    self.servo.program_bios(self.netboot_firmware_path)

    logging.info('Flashing EC %s on DUT %s with servo %s',
                 self.netboot_ec_path, self.options.dut, servo_version)
    self.servo.program_ec(self.netboot_ec_path)

  def _CheckSSHPort(self):
    """A helper method to check if the SSH port on DUT is alive.

    Returns:
      True if SSH port is up; False otherwise.
    """
    try:
      socket.create_connection((self.options.dut, 22)).close()
      return True
    except socket.error:
      return False

  def FlashFirmwareWithSSH(self):
    """Flashes netboot firmware and EC with SSH.

    Runs rsync to copy the netboot firmware and EC to DUT, and ssh into the DUT
    to run flashrom to flash the firmware and EC.

    Raises:
      NetbootInstallError if DUT board name does not match the one specified in
      the bundle.
    """
    # Make sure we are flashing the right board.
    dut_lsb_release = ssh_utils.SpawnSSHToDUT(
        [self.options.dut, 'cat', '/etc/lsb-release'], log=True,
        check_output=True).stdout_data
    dut_board = re.search(r'^CHROMEOS_RELEASE_BOARD=(.*)$', dut_lsb_release,
                          flags=re.MULTILINE)
    if not dut_board:
      raise NetbootInstallError('Cannot determine DUT board name')
    if dut_board.group(1) != self.options.board.full_name:
      raise NetbootInstallError(
          'The netboot firmware in the bundle is for %s but the DUT is %s' %
          (self.options.board.full_name, dut_board.group(1)))

    logging.info('Flashing netboot firmware %s on DUT %s with SSH',
                 self.netboot_firmware_path, self.options.dut)
    remote_fw_path = '/tmp/netboot_firmware.bin'
    ssh_utils.SpawnRsyncToDUT(['-aP', self.netboot_firmware_path,
                               '%s:%s' % (self.options.dut, remote_fw_path)],
                              log=True, check_output=True)
    ssh_utils.SpawnSSHToDUT([self.options.dut, 'flashrom', '-p', 'host', '-w',
                            remote_fw_path], log=True, check_output=True)

    logging.info('Flashing EC %s on DUT %s with SSH',
                 self.netboot_ec_path, self.options.dut)
    remote_ec_path = '/tmp/ec.bin'
    ssh_utils.SpawnRsyncToDUT(['-aP', self.netboot_ec_path,
                               '%s:%s' % (self.options.dut, remote_ec_path)],
                              log=True, check_output=True)
    ssh_utils.SpawnSSHToDUT([self.options.dut, 'flashrom', '-p', 'ec', '-w',
                        remote_ec_path], log=True, check_output=True)

    logging.info('Rebooting DUT %s', self.options.dut)
    ssh_utils.SpawnSSHToDUT(
        [self.options.dut, 'reboot'], log=True, check_call=True)
    utils.WaitFor(lambda: not self._CheckSSHPort(),
                  timeout_secs=30, poll_interval=1)
    logging.info('DUT %s rebooted', self.options.dut)

  def WaitForInstallToFinish(self):
    """Selects install action and waits for factory install to finish."""
    logging.info(('Waiting for factory install to complete on DUT %s '
                  'by trying to connect to SSH port (22) on it'),
                 self.options.dut)
    utils.WaitFor(self._CheckSSHPort,
                  timeout_secs=self.options.wait_timeout_secs,
                  poll_interval=5)
    logging.info('SSH port (22) on DUT %s is up', self.options.dut)
