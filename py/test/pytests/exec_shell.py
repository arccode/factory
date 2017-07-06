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

  OperatorTest(pytest_name='exec_shell',
               dargs={'commands': ['iptables -A input -p tcp --dport 4020',
                                   'iptables -A input -p tcp --dport 4021',
                                   'iptables -A input -p tcp --dport 4022']})

To load module 'i2c-dev' (and never fails), add this in test list::

  OperatorTest(pytest_name='exec_shell',
               dargs={'commands': 'modprobe i2c-dev || true'})
"""

import logging
import subprocess
import threading
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import i18n
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg

# UI Elements
_TEST_TITLE = i18n_test_ui.MakeI18nLabel(
    'Running shell commands...')


class ExecShell(unittest.TestCase):
  """Runs a list of commands.

  Properties:
    _ui: test ui.
    _template: test ui template.
    _commands: A list of CheckItems.
  """
  ARGS = [
      Arg('commands', (list, tuple, str),
          'A list (or one simple string) of shell commands to execute.',
          optional=False),
      Arg('is_station', bool,
          ('Run the given commands on station (usually local host) instead of '
           'DUT, for example preparing connection configuration.'),
          default=False),
      Arg('has_ui', bool, 'True if this test runs with goofy UI enabled.',
          default=True)
  ]

  @staticmethod
  def _CommandToLabel(command, length=50):
    """Returns a label (with max length) to display given command."""
    text = (command[:length] + ' ...') if len(command) > length else command
    return i18n_test_ui.MakeI18nLabel(i18n.NoTranslation(text))

  def UpdateOutput(self, handle, name, output):
    """Updates output from file handle to given HTML node."""
    while True:
      c = handle.read(1)
      if not c:
        break
      self._ui.SetHTML(c, append=True, id=name)
      output[name] += c

  def setUp(self):
    if self.args.has_ui:
      self._ui = test_ui.UI()
      self._template = ui_templates.TwoSections(self._ui)
    else:
      self._ui = test_ui.DummyUI(self)
      self._template = ui_templates.DummyTemplate()

    self._template.SetTitle(_TEST_TITLE)
    self._template.DrawProgressBar()
    self._dut = (device_utils.CreateStationInterface()
                 if self.args.is_station else
                 device_utils.CreateDUTInterface())

    if isinstance(self.args.commands, basestring):
      self._commands = [self.args.commands]
    else:
      self._commands = self.args.commands

  def _runTest(self):
    for i, command in enumerate(self._commands):
      self._template.SetProgressBarValue((i + 1) * 100.0 / len(self._commands))
      self._template.SetInstruction(self._CommandToLabel(command))
      self._template.SetState(
          '<b>stdout:</b><br>'
          '<textarea cols=80 rows=12 readonly id="stdout"></textarea>'
          '<br><b>stderr:</b><br>'
          '<textarea cols=80 rows=12 readonly id="stderr"></textarea>'
      )

      process = self._dut.Popen(command,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
      if self.args.has_ui:
        handles = {
            'stdout': process.stdout,
            'stderr': process.stderr,
        }
        output = dict((name, '') for name in handles)
        threads = [threading.Thread(target=self.UpdateOutput,
                                    args=(handle, name, output))
                   for name, handle in handles.iteritems()]
        for thread in threads:
          thread.start()

        process.wait()

        for thread in threads:
          thread.join()
        stdout = output['stdout']
        stderr = output['stderr']
      else:
        stdout, stderr = process.communicate()

      logging.info('Shell command: %r, result=%s, stdout=%r, stderr=%r',
                   command, process.returncode, stdout, stderr)
      if process.returncode != 0:
        # More chance so user can see the error.
        time.sleep(3)
        self._ui.Fail('Shell command failed (%d): %s' %
                      (process.returncode, command))

  def runTest(self):
    """Main entrance of the test."""
    self._ui.RunInBackground(self._runTest)
    self._ui.Run()
