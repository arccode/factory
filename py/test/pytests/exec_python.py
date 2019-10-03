# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A test to run arbitrary python scripts.

Description
-----------
This test executes the python script specified in `script` argument in an
empty context with only the current `test_info` object
(an instance of :py:class:`cros.factory.goofy.invocation.PytestInfo`) provided.

This is intended to be a dummy test for other unittests like
`goofy_unittest`, usual factory procedure should not use this test.

Test Procedure
--------------
This is an automated test without user interaction.

Runs the given script and fails if any exception raises during
execution.

Dependency
----------
None.

Examples
--------
A test that always pass::

  {
    "pytest_name": "exec_python",
    "args": {
      "script": "assert 1 == 1"
    }
  }

"""

import logging
import unittest

from cros.factory.utils.arg_utils import Arg


class ExecPythonTest(unittest.TestCase):
  """A simple test that just executes a Python script."""
  ARGS = [
      Arg('script', str, 'Python code to execute'),
  ]

  def runTest(self):
    logging.info("Executing Python script: '''%s'''", self.args.script)
    exec(self.args.script, {'test_info': self.test_info}, {})
    logging.info('Script succeeded')
