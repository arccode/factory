# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils.arg_utils import Arg


class ExecPythonTest(unittest.TestCase):
  """A simple test that just executes a Python script."""
  ARGS = [
      Arg('script', str, 'Python code to execute'),
  ]

  def runTest(self):
    logging.info("Executing Python script: '''%s'''", self.args.script)
    exec self.args.script in {'test_info': self.test_info}, {}
    logging.info('Script succeeded')
