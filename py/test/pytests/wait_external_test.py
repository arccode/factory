# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A stub test waiting for external fixture to finish testing.

Description
-----------
If you want to add a test driven by external fixture or instruments and still
want to track test results in Chrome OS Factory Software, this test provides an
easy way for test integration.

This test will check and wait for a file ``/run/factory/external/<NAME>`` to
be available. If the file content is ``PASS`` then the test item in test list
will be set as "passed", otherwise it will fail with the content from file.
Empty file is also considered as failure.

A script is included in factory software toolkit to help doing this:
``bin/factory_external_result``. It needs at least two parameters - ``NAME`` and
``RESULT``. For example, to pass a ``RF1`` test, do::

  /usr/local/factory/bin/factory_external_result RF1 PASS

To fail a ``VSWR`` test with message, do::

  /usr/local/factory/bin/factory_external_result RF1 "Failed to init instrument"

In summary, to design and implement a test item with external fixture:

1. Decide a test name, for example ``RF1``.
2. In Chrome OS Factory Software test list, add a test item with ``pytest_name``
   set to ``wait_external_test``, and ``run_factory_external_name`` argument set
   to the test name.
3. In the fixture side, detect if the DUT is connected. For Chromebooks, this
   is usually done by ethernet dongle. For Android devices, try ADB.
4. Fixture should drive the test and implement all logic and test procedure.
   To access Chromebooks, execute programs using SSH (you can find the private
   key for root in
   https://chromium.googlesource.com/chromiumos/platform/factory/+/HEAD/misc/sshkeys/testing_rsa
   ). For Android, use ``adb shell``.
5. When the test by fixture is finished, invoke the ``factory_external_result``
   to set result or manually create the files under ``/run/factory/external``.

Test Procedure
--------------
This is an automated test without user interaction.

When started, the test will wait for specified file to become available,
and pass or fail according to the file content.

The test procure will depend on remote fixture.

Dependency
----------
None.

Examples
--------
To add an entry for external fixture with name ``RF1``, add this in test list::

  {
    "pytest_name": "wait_external_test",
    "args": {
      "run_factory_external_name": "RF1"
    }
  }

To add a test for external fixture with name ``VSWR``, with customized message::

  {
    "pytest_name": "wait_external_test",
    "args": {
      "msg": "i18n! Move DUT to station {name}",
      "run_factory_external_name": "VSWR"
    }
  }

In the fixture side, it should do something like this:

.. code-block:: sh

  SSH_KEY=PATH_TO/testing_rsa
  TEST_NAME=VSWR
  SET_RESULT=/usr/local/factory/bin/factory_external_result
  chmod go-rwx "${SSH_KEY}"  # SSH needs private key to be restricted.
  ssh root@dut -i "${SSH_KEY}" "${SET_RESULT} ${TEST_NAME} PASS"
"""

import os

from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import sync_utils


_EXTERNAL_DIR = '/run/factory/external'

# Usually external tests will take a long time to run so check duration can be
# longer.
_CHECK_PERIOD_SECS = 1


class WaitExternalTest(test_case.TestCase):
  """Wait for a test by external fixture to finish."""
  ARGS = [
      Arg('run_factory_external_name', str,
          'File name to check in /run/factory/external.'),
      i18n_arg_utils.I18nArg(
          'msg', 'Instruction for running external test',
          default=_('Please run external test: {name}'))
  ]

  def setUp(self):
    self.ui.ToggleTemplateClass('font-large', True)
    self._name = self.args.run_factory_external_name
    self.ui.SetState(_(self.args.msg, name=self._name))
    self._file_path = os.path.join(
        _EXTERNAL_DIR, self.args.run_factory_external_name)
    self.RemoveFile(self._file_path)

  def FileExists(self):
    return os.path.exists(self._file_path)

  def runTest(self):
    sync_utils.PollForCondition(
        poll_method=self.FileExists,
        poll_interval_secs=_CHECK_PERIOD_SECS,
        timeout_secs=None,
        condition_name='WaitForExternalFile')

    # Ideally external hosts should do atomic write, but since it's probably
    # done by 3rd party vendors with arbitrary implementation, so a quick and
    # simple solution is to wait for one more check period so the file should be
    # flushed.
    self.Sleep(_CHECK_PERIOD_SECS)

    with open(self._file_path) as f:
      result = f.read().strip()

    self.assertEqual(result.lower(), 'pass',
                     'Test %s completed with failure: %s' %
                     (self._name, result or 'unknown'))

  def RemoveFile(self, file_path):
    try:
      file_dir = os.path.dirname(file_path)
      file_utils.TryMakeDirs(file_dir)
      os.remove(file_path)
    except OSError:
      if os.path.exists(file_path) or not os.path.exists(file_dir):
        raise
