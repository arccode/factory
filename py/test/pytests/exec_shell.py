# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A test to invoke a list of shell commands.

Description
-----------
This test will execute the shell commands given from argument ``commands`` one
by one, and fail if any of the return value is non-zero.

By default the commands are executed on DUT (specified by Device API). If you
need to run on station (usually local), set argument ``is_station`` to True.

Test Procedure
--------------
This is an automated test without user interaction.

Start the test and it will run the shell commands specified, one by one; and
fail if any of the command returns false.

Dependency
----------
The test uses system shell to execute commands, which may be different per
platform. Also, the command may be not always available on target system.
You have to review each command to check if that's provided on DUT.

Examples
--------
To add multiple ports to iptables, add this in test list::

  {
    "pytest_name": "exec_shell",
    "args": {
      "commands": [
        "iptables -A input -p tcp --dport 4020",
        "iptables -A input -p tcp --dport 4021",
        "iptables -A input -p tcp --dport 4022"
      ]
    }
  }

To load module 'i2c-dev' (and never fails), add this in test list::

  {
    "pytest_name": "exec_shell",
    "args": {
      "commands": "modprobe i2c-dev || true"
    }
  }
"""

import logging
import os
import StringIO
import subprocess
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


class ExecShell(test_case.TestCase):
  """Runs a list of commands.

  Properties:
    _commands: A list of CheckItems.
  """
  ARGS = [
      Arg('commands', (list, str),
          'A list (or one simple string) of shell commands to execute.'),
      Arg('is_station', bool,
          ('Run the given commands on station (usually local host) instead of '
           'DUT, for example preparing connection configuration.'),
          default=False)
  ]

  @staticmethod
  def _DisplayedCommand(command, length=50):
    """Returns a possibly truncated command with max length to display."""
    return (command[:length] + ' ...') if len(command) > length else command

  def UpdateOutput(self, handle, name, output, interval_sec=0.1):
    """Updates output from file handle to given HTML node."""
    self.ui.SetHTML('', id=name)
    while True:
      c = os.read(handle.fileno(), 4096)
      if not c:
        break
      self.ui.SetHTML(
          test_ui.Escape(c, preserve_line_breaks=False), append=True, id=name,
          autoscroll=True)
      output[name].write(c)
      time.sleep(interval_sec)

  def setUp(self):
    self.ui.SetTitle(_('Running shell commands...'))
    self._dut = (device_utils.CreateStationInterface()
                 if self.args.is_station else
                 device_utils.CreateDUTInterface())

    if isinstance(self.args.commands, basestring):
      self._commands = [self.args.commands]
    else:
      self._commands = self.args.commands

  def runTest(self):
    self.ui.DrawProgressBar(len(self._commands))
    for command in self._commands:
      self.ui.SetInstruction(self._DisplayedCommand(command))

      process = self._dut.Popen(command,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
      handles = {
          'stdout': process.stdout,
          'stderr': process.stderr,
      }
      output = {name: StringIO.StringIO() for name in handles}
      threads = [
          process_utils.StartDaemonThread(
              target=self.UpdateOutput, args=(handle, name, output))
          for name, handle in handles.iteritems()
      ]

      process.wait()

      for thread in threads:
        thread.join()

      stdout = output['stdout'].getvalue()
      stderr = output['stderr'].getvalue()

      logging.info('Shell command: %r, result=%s, stdout=%r, stderr=%r',
                   command, process.returncode, stdout, stderr)
      if process.returncode != 0:
        # More chance so user can see the error.
        self.Sleep(3)
        self.FailTask('Shell command failed (%d): %s' % (process.returncode,
                                                         command))

      self.ui.AdvanceProgress()
