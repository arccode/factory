#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of cros.factory.test.dut.BaseTarget using ADB."""

import logging
import pipes
import subprocess
import uuid

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import base
from cros.factory.utils import file_utils


class AdbTarget(base.BaseTarget):
  """A DUT target that is connected via ADB interface."""

  def __init__(self):
    """Dummy constructor."""
    pass

  def Push(self, local, remote):
    """See BaseTarget.Push"""
    return subprocess.check_call(['adb', 'push', local, remote])

  def Pull(self, remote, local=None):
    """See BaseTarget.Pull"""
    if local is None:
      with file_utils.UnopenedTemporaryFile() as path:
        self.Pull(remote, path)
        with open(path) as f:
          return f.read()

    subprocess.check_call(['adb', 'pull', remote, local])

  def Shell(self, command, stdin=None, stdout=None, stderr=None):
    """See BaseTarget.Shell"""
    # ADB shell has a bug that exit code is not correctly returned (
    #  https://code.google.com/p/android/issues/detail?id=3254 ). Many public
    # implementations work around that by adding an echo and then parsing the
    # execution results. To avoid problems in redirection, we do this slightly
    # different by using the log service and "logcat" ADB feature.

    session_id = str(uuid.uuid1())

    # Convert list-style commands to single string because we need to run
    # multiple commands in same session (and needs shell=True).
    if not isinstance(command, basestring):
      command = ' '.join(pipes.quote(param) for param in command)

    command = ['adb', 'shell', '( %s ) ; log -t %s $?' % (command, session_id)]
    logging.debug('AdbTarget: Run %r', command)
    exit_code = subprocess.call(command, stdin=stdin, stdout=stdout,
                                stderr=stderr)
    if exit_code == 0:
      # Try to get real exit code.
      result = subprocess.check_output('adb logcat -d -b main -s %s' %
                                       session_id, shell=True).strip()
      logging.debug('AdbTarget: Exit Results = %s', result)
      # Format: I/session_id(PID): EXITCODE
      # Example: I/64eeb606-fdcf-11e4-b63f-80c16efb89a5( 3439): 0
      exit_code = int(result.rpartition(':')[2].strip())
    return exit_code

  def IsReady(self):
    """See BaseTarget.IsReady"""
    return subprocess.check_output(['adb', 'get-state']).strip() == 'device'
