#! /usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A wrapper of the servo module from autotest repo."""

import argparse
import logging
import os
import re
import subprocess

import factory_common   # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils


FLASHROM_LOCK_FILE = '/tmp/factory_flow_flashrom'
FLASHROM_LOCK_TIMEOUT = 600


class Servo(object):
  """A wrapper class for servo.Servo in autotest repo."""

  # A board name map to translate board variants to base board.
  BoardMap = {
      'expresso': 'rambi',
      'big': 'nyan_big',
      }

  def __init__(self, board, host, port=9999, serial=None):
    self._InstallRequiredPackages()

    # Do autotest imports here to stop it from messing around with logging
    # settings.
    # pylint: disable=W0612, F0401
    import autotest_common
    from autotest_lib.server import hosts
    from autotest_lib.server.cros.servo import servo
    if host in ('localhost', '127.0.0.1'):
      if board in self.BoardMap:
        board = self.BoardMap[board]
      self._servod = process_utils.Spawn(
          ['servod', '--board', board, '--port', str(port)] +
          (['--serialname', serial] if serial else []),
          sudo=True, log=True)
      def WaitForServod():
        REGEXP = re.compile(r'^tcp.*(127\.0\.0\.1|localhost):%d' % port,
                            re.MULTILINE)
        netstat = process_utils.CheckOutput(['netstat', '-nl'])
        return bool(REGEXP.search(netstat))

      sync_utils.WaitFor(WaitForServod, 10)

      if utils.in_cros_device():
        # Do not try to auto-update if we are running servo host directly on a
        # CrOS factory server.
        hosts.ServoHost._update_image = lambda _: True
        # Create a dummy servod config to make ServoHost happy.
        process_utils.Spawn(['touch', '/var/lib/servod/config'],
                            log=True, sudo=True, check_call=True)

    # ServoHost will try to repair itself if it finds itself in the test lab. It
    # does so by checking whether [hostname].cros.corp.google.com is a FQDN.
    # Unfortunately 'localhost.cros.corp.google.com' is actually a FQDN and thus
    # would make all localhost look like a host in the test lab, and is causing
    # problem to our factory flow testing. So we explictly set is_in_lab=False
    # here.
    self._servo = servo.Servo(
        hosts.ServoHost(servo_host=host, servo_port=port, is_in_lab=False),
        serial)

  def _InstallRequiredPackages(self):
    if utils.in_cros_device():
      # CrOS factory server has all the required packages.
      return

    # Check if flashrom is installed with ft2232_spi support.
    flashrom_equery = process_utils.CheckOutput(
        ['equery', '--no-color', '--no-pipe', 'uses', 'flashrom'])
    use_ft2232_spi = re.search(
        r'^\s*([+-])\s*([+-])\s*ft2232_spi', flashrom_equery, re.MULTILINE)
    if use_ft2232_spi.group(2) != '+':
      logging.info(
          'Your flashrom does not have ft2232_spi support. Re-building '
          'flashrom package with USE=ft223_spi...')
      process_utils.Spawn(
          ['sudo', '-E', 'emerge', 'flashrom'], env=dict(USE='ft2232_spi'),
          log=True, check_call=True, log_stderr_on_error=True,
          ignore_stdout=True)

    # Check if flash_ec is accessible to root.
    try:
      process_utils.Spawn(['which', 'flash_ec'], sudo=True, check_call=True)
    except subprocess.CalledProcessError:
      logging.info('Cannot locate flash_ec through sudo. Creating symbolic '
                   'link of flash_ec in /usr/local/bin...')
      process_utils.Spawn(
          ['ln', '-s', os.path.join(
              os.environ['CROS_WORKON_SRCROOT'], 'src', 'platform', 'ec',
              'util', 'flash_ec'),
           '/usr/local/bin'], sudo=True, log=True, check_call=True)

  def __getattr__(self, name):
    """Delegates getter of all unknown attributes to servo.Servo object."""
    return self.__dict__.get(name) or getattr(self._servo, name)

  def TearDown(self):
    """Cleans up servod process if we started one."""
    if self._servod:
      process_utils.TerminateOrKillProcess(self._servod, sudo=True)


def Main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--board', help='the board name used to start servod')
  parser.add_argument('--host', help='the servo host')
  parser.add_argument('--port', type=int, default=9999,
                      help='the port servod listens to')
  parser.add_argument('--serial', help='the serial number of the servo board')
  parser.add_argument('method_call', help='the method and its args to call')
  args = parser.parse_args()

  servo = None
  try:
    servo = Servo(args.board, args.host, port=args.port, serial=args.serial)
    print eval('servo.%s' % args.method_call, dict(servo=servo), {})
  finally:
    if servo:
      servo.TearDown()

if __name__ == '__main__':
  Main()
