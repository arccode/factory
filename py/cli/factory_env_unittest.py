#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import glob
import os
import unittest

from cros.factory.cli import factory_env
from cros.factory.utils import process_utils


FACTORY_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

FACTORY_ENV_TOOL = os.path.join(FACTORY_ROOT, "bin/factory_env")
FACTORY_ENV_SCRIPT = os.path.join(FACTORY_ROOT, "py/cli/factory_env.py")
DUMMY_SCRIPT = os.path.join(
    FACTORY_ROOT, "py/cli/testdata/scripts/dummy_script.py")
DUMMY_EXCUTABLE = os.path.join(
    FACTORY_ROOT, "py/cli/testdata/bin/dummy_script")


class FactoryEnvUnittest(unittest.TestCase):
  def testSymbolicLinkToFactoryEnv(self):
    self.assertEqual(0,
                     process_utils.LogAndCheckCall(DUMMY_EXCUTABLE).returncode)

  def testFactoryEnvWithSymbolicLinkToFactoryEnv(self):
    self.assertEqual(0, process_utils.LogAndCheckCall(
        [FACTORY_ENV_TOOL, DUMMY_EXCUTABLE]).returncode)

  def testMultipleFactoryEnv(self):
    self.assertEqual(0, process_utils.LogAndCheckCall(
        [FACTORY_ENV_TOOL, FACTORY_ENV_TOOL, DUMMY_EXCUTABLE]).returncode)

  def testFactoryEnvWithScript(self):
    self.assertEqual(0, process_utils.LogAndCheckCall(
        [FACTORY_ENV_TOOL, DUMMY_SCRIPT]).returncode)

  def testHelpMessage(self):
    process = process_utils.Spawn(
        [FACTORY_ENV_TOOL, '--help'], read_stdout=True)
    self.assertEqual(factory_env.HELP_MSG, process.stdout_data)
    self.assertEqual(1, process.returncode)

  def testScriptNotFound(self):
    process = process_utils.Spawn(
        [FACTORY_ENV_TOOL, 'script/not/found'], read_stdout=True)
    self.assertEqual(factory_env.HELP_MSG, process.stdout_data)
    self.assertEqual(1, process.returncode)

  def testPythonInterpreter(self):
    output = process_utils.CheckOutput(
        [FACTORY_ENV_TOOL, 'python', '-c', 'import sys; print(sys.path)'])
    self.assertIn('factory/py_pkg', output)


class SymlinkUnittest(unittest.TestCase):
  def testLegalityForSymlinkInBin(self):
    for path in glob.glob(os.path.join(FACTORY_ROOT, "bin/**")):
      if not os.path.islink(path):
        continue

      real_path = os.path.realpath(path)
      if not real_path.endswith('.py'):
        continue

      # Make sure bin/tool_name links to FACTORY_ENV_SCRIPT
      self.assertEqual(real_path, FACTORY_ENV_SCRIPT)

      # Make sure py/cli/tool_name.py exist
      self.assertTrue(os.path.exists(factory_env.GetRealScriptPath(path)))


if __name__ == '__main__':
  unittest.main()
