# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A wrapper of the servo module from autotest repo."""

import re

import factory_common   # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.utils import process_utils


FLASHROM_LOCK_FILE = '/tmp/factory_flow_flashrom'
FLASHROM_LOCK_TIMEOUT = 600


class Servo(object):
  """A wrapper class for servo.Servo in autotest repo."""

  def __init__(self, board, host, port=9999, serial=None):
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

  def __getattr__(self, name):
    """Delegates getter of all unknown attributes to servo.Servo object."""
    return self.__dict__.get(name) or getattr(self._servo, name)

  def TearDown(self):
    """Cleans up servod process if we started one."""
    if self._servod:
      process_utils.TerminateOrKillProcess(self._servod, sudo=True)
