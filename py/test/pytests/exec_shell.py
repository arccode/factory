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

If argument ``attachment_name`` is specified, the log files specified from
argument ``attachment_path`` will be archived (using tar+gz) and uploaded as an
attachment via TestLog.

If ``attachment_path`` is empty, the archive is created by running the commands
in a temporary folder and then collecting all files created there. In other
words, we are doing something like this shell script:

.. code-block:: bash

   #!/bin/sh
   DIR="$(mktemp -d)"
   TARBALL="$(mktemp --suffix=.tar.gz)"
   ( cd "${DIR}"; "$@"; tar -zcf "${TARBALL}" ./ )
   echo "Log is generated in ${TARBALL}."

And ``$@`` will be replaced by the ``commands`` argument. To test if your logs
will be created properly, save the snippet above as ``test.sh``, then run it
with your commands, for example::

  ./test.sh /usr/local/factory/third_party/some_command some_arg

Test Procedure
--------------
This is an automated test without user interaction.

Start the test and it will run the shell commands specified, one by one; and
fail if any of the command returns false.

If ``attachment_name`` is specified, after all commands are finished (or if any
command failed), the results will be archived and saved to TestLog.

Dependency
----------
The test uses system shell to execute commands, which may be different per
platform. Also, the command may be not always available on target system.
You have to review each command to check if that's provided on DUT.

If ``attachment_name`` is specified, the DUT must support ``tar`` command with
``-zcf`` arguments.

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

Echo a message and dump into a temp folder as working directory then save the
files in TestLog attachment::

  {
    "pytest_name": "exec_shell",
    "args": {
      "commands": "echo test >some.output",
      "attachment_name": "logtest"
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
from cros.factory.testlog import testlog
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
          default=False),
      Arg('attachment_name', str,
          ('File base name for collecting and creating testlog attachment. '
           'None to skip creating attachments.'),
          None),
      Arg('attachment_path', str,
          ('Source path for collecting logs to create testlog attachment. '
           'None to run commands in a temporary folder and attach everything '
           'created, otherwise tar everything from given path.'),
          None)
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

  def SaveAttachments(self, name, path):
    assert self._dut.path.exists(path), 'Log path does not exist: %s' % path
    with self._dut.temp.TempFile() as temp_path:
      dirname = path
      filename = '.'
      if self._dut.path.isfile(path):
        dirname = self._dut.path.dirname(path)
        filename = self._dut.path.basename(path)
      command = 'tar -zcf %s -C %s %s' % (temp_path, dirname, filename)
      self._dut.CheckCall(command)
      # TODO(hungte) Use link.pull if link is not local.
      assert self._dut.link.IsLocal(), 'Remote DUT not supported.'
      testlog.AttachFile(
          path=temp_path,
          name=('%s.tar.gz' % name),
          mime_type='application/gzip')

  def RunCommand(self, command):
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
    return process.returncode

  def setUp(self):
    self._cwd = None
    self.ui.SetTitle(_('Running shell commands...'))
    self._dut = (device_utils.CreateStationInterface()
                 if self.args.is_station else
                 device_utils.CreateDUTInterface())

    assert not self.args.attachment_name or self._dut.link.IsLocal(), (
        'Argument attachment_name currently needs to run on local DUT.')

    if isinstance(self.args.commands, basestring):
      self._commands = [self.args.commands]
    else:
      self._commands = self.args.commands

  def tearDown(self):
    if self._cwd:
      self._dut.CheckCall(['rm', '-rf', self._cwd])

  def runTest(self):
    self.ui.DrawProgressBar(len(self._commands))
    result = 0
    command = ''

    if self.args.attachment_name and not self.args.attachment_path:
      # Create a temporary folder.
      self._cwd = self._dut.temp.mktemp(is_dir=True)

    for command in self._commands:
      if self._cwd:
        assert isinstance(command, basestring), (
            'Temporary attachment_path needs string type commands')
        command = 'cd %s; %s' % (self._cwd, command)

      result = self.RunCommand(command)
      if result != 0:
        testlog.AddFailure(code=result, details='failed command: %r' % command)
        break
      self.ui.AdvanceProgress()

    if self.args.attachment_name:
      self.SaveAttachments(
          self.args.attachment_name, self.args.attachment_path or self._cwd)

    if result != 0:
      # More chance so user can see the error.
      self.Sleep(3)
      self.FailTask('Shell command failed (%d): %s' % (result, command))
