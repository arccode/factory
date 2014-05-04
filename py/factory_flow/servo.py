# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A wrapper of the servo module from autotest repo."""

import logging
import os
import re
import subprocess

import factory_common   # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.utils import process_utils


FLASHROM_LOCK_FILE = '/tmp/factory_flow_flashrom'
FLASHROM_LOCK_TIMEOUT = 600


class Servo(object):
  """A wrapper class for servo.Servo in autotest repo."""

  def __init__(self, board, host, port=9999, serial=None):
    self._InstallRequiredPackages()

    # Do autotest imports here to stop it from messing around with logging
    # settings.
    # pylint: disable=W0612, F0401
    import autotest_common
    from autotest_lib.server import hosts
    from autotest_lib.server.cros.servo import servo
    if host in ('localhost', '127.0.0.1'):
      self._servod = process_utils.Spawn(
          ['servod', '--board', board, '--port', str(port)] +
          (['--serialname', serial] if serial else []),
          sudo=True, log=True)
      def WaitForServod():
        REGEXP = re.compile(r'^tcp.*(127\.0\.0\.1|localhost):%d' % port,
                            re.MULTILINE)
        netstat = process_utils.CheckOutput(['netstat', '-l'])
        return bool(REGEXP.search(netstat))

      utils.WaitFor(WaitForServod, 10)

    self._servo = servo.Servo(hosts.ServoHost(servo_host=host, servo_port=port),
                              serial)

  def _InstallRequiredPackages(self):
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
