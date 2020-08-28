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

The working directory for the commands is given by argument ``working_dir``,
which default is ``.``, i.e. the current working directory.  Set
``working_dir=None`` if you want this test to create a temporary working
directory and remove it after the test is finished.

If argument ``attachment_name`` is specified, the log files specified from
argument ``attachment_path`` will be archived (using tar+gz) and uploaded as an
attachment via TestLog.

If ``attachment_path`` is empty, the command working directory will be
used.  In other words, we are doing something like this shell script:

.. code-block:: bash

   #!/bin/sh
   DIR="${WORKING_DIR:-$(mktemp -d)}"
   TARBALL="$(mktemp --suffix=.tar.gz)"
   ( cd "${DIR}"; "$@"; tar -zcf "${TARBALL}" ./ )
   echo "Log is generated in ${TARBALL}."

And ``$@`` will be replaced by the ``commands`` argument. To test if your logs
will be created properly, save the snippet above as ``test.sh``, then run it
with your commands, for example::

  (WORKING_DIR=somewhere ./test.sh
   /usr/local/factory/third_party/some_command some_arg)

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
      "working_dir": None,
      "commands": "echo test >some.output",
      "attachment_name": "logtest"
    }
  }

Echo a message and dump into an existing folder then save the files in TestLog
attachment::

  {
    "pytest_name": "exec_shell",
    "args": {
      "working_dir": "/usr/local/factory/my_log",
      "commands": "echo test >some.output",
      "attachment_name": "logtest"
    }
  }
"""

from io import StringIO
import logging
import os
import subprocess
import time

from cros.factory.device import device_utils
from cros.factory.test.env import paths
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
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
      Arg('working_dir', (type(None), str),
          ('Path name of the working directory for running the commands. '
           'If set to ``None``, a temporary directory will be used.'),
          default='.'),
      Arg('attachment_name', str,
          ('File base name for collecting and creating testlog attachment. '
           'None to skip creating attachments.'), default=None),
      Arg('log_command_output', bool,
          ('Log the executed results of each commands, which includes stdout,'
           'stderr and the return code.'), default=True),
      Arg('attachment_path', str,
          ('Source path for collecting logs to create testlog attachment. '
           'None to run commands in a temporary folder and attach everything '
           'created, otherwise tar everything from given path.'), default=None),
      Arg('source_codes', (list, str),
          'A list (or single path) of source codes to log.', default=None)
  ]

  @staticmethod
  def _DisplayedCommand(command, length=50):
    """Returns a possibly truncated command with max length to display."""
    return (command[:length] + ' ...') if len(command) > length else command

  def UpdateOutput(self, handle, name, output, interval_sec=0.1):
    """Updates output from file handle to given HTML node."""
    self.ui.SetHTML('', id=name)
    while True:
      c = os.read(handle.fileno(), 4096).decode('utf-8')
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

  def RunCommand(self, cwd, command):
    self.ui.SetInstruction(self._DisplayedCommand(command))

    process = self._dut.Popen(
        command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    handles = {
        'stdout': process.stdout,
        'stderr': process.stderr,
    }
    output = {name: StringIO() for name in handles}
    threads = [
        process_utils.StartDaemonThread(
            target=self.UpdateOutput, args=(handle, name, output))
        for name, handle in handles.items()
    ]

    process.wait()

    for thread in threads:
      thread.join()

    stdout = output['stdout'].getvalue()
    stderr = output['stderr'].getvalue()
    returncode = process.returncode

    if self.args.log_command_output:
      logging.info('Shell command: %r, result=%s, stdout=%r, stderr=%r',
                   command, returncode, stdout, stderr)
      with self._group_checker:
        testlog.LogParam('stdout', stdout)
        testlog.LogParam('stderr', stderr)
        testlog.LogParam('returncode', returncode)
    else:
      logging.info('Shell command: %r, result=%s', command, returncode)

    return returncode

  def setUp(self):
    self.ui.SetTitle(_('Running shell commands...'))
    self._dut = (device_utils.CreateStationInterface()
                 if self.args.is_station else
                 device_utils.CreateDUTInterface())

    assert not self.args.attachment_name or self._dut.link.IsLocal(), (
        'Argument attachment_name currently needs to run on local DUT.')

    if isinstance(self.args.commands, str):
      self._commands = [self.args.commands]
    else:
      self._commands = self.args.commands

    if self.args.source_codes is None:
      source_codes = []
    elif isinstance(self.args.source_codes, str):
      source_codes = [self.args.source_codes]
    else:
      source_codes = self.args.source_codes

    log_dir = os.path.join(paths.DATA_TESTS_DIR, session.GetCurrentTestPath())
    for source_path in source_codes:
      file_name, extension = os.path.splitext(os.path.basename(source_path))
      hash_file_name = '%s_%s' % (file_name, file_utils.SHA1InHex(source_path))
      log_path = os.path.join(log_dir, hash_file_name + extension)
      file_utils.CopyFileSkipBytes(source_path, log_path, 0)

    testlog.UpdateParam(
        'stdout', description='standard output of the command')
    testlog.UpdateParam(
        'stderr', description='standard error of the command')
    testlog.UpdateParam(
        'returncode', description='return code of the command')
    self._group_checker = testlog.GroupParam(
        'command_output', ['stdout', 'stderr', 'returncode'])

  def runTest(self):
    self.ui.DrawProgressBar(len(self._commands))
    result = 0
    command = ''

    if self.args.working_dir is None:
      cwd = self._dut.temp.mktemp(is_dir=True)
    else:
      cwd = self.args.working_dir
      if not self._dut.path.exists(cwd):
        self._dut.CheckCall(['mkdir', '-p', cwd])

    for command in self._commands:
      assert isinstance(command, str), (
          'Temporary attachment_path needs string type commands')

      result = self.RunCommand(cwd, command)
      if result != 0:
        testlog.AddFailure(code=result, details='failed command: %r' % command)
        break
      self.ui.AdvanceProgress()

    if self.args.attachment_name:
      self.SaveAttachments(
          self.args.attachment_name, self.args.attachment_path or cwd)

    if self.args.working_dir is None:
      self._dut.CheckCall(['rm', '-rf', cwd])

    if result != 0:
      # More chance so user can see the error.
      self.Sleep(3)
      self.FailTask('Shell command failed (%d): %s' % (result, command))
