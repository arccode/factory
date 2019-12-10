#!/usr/bin/env python3
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''A test for make_par.py.

This also tests run_pytest.
'''


import os
import shutil
import tempfile
import unittest

from cros.factory.tools import make_par
from cros.factory.utils.process_utils import Spawn


class MakePARTest(unittest.TestCase):

  def setUp(self):
    self.tmp = tempfile.mkdtemp(prefix='make_par_unittest.')
    self.par = os.path.join(self.tmp, 'factory.par')
    self.assertTrue(make_par.main(['-o', self.par]))

  def tearDown(self):
    shutil.rmtree(self.tmp)

  def _RunPytest(self, command):
    """Runs a 'pytest' using the 'run_pytest' command.

    Args:
      command: A list of command-line args to use to launch run_pytest.
    """
    for expected_retcode, script in ((0, 'pass'),
                                     (1, 'raise ValueError')):
      self.assertEqual(
          expected_retcode,
          Spawn(command + ['exec_python', '--args', repr({'script': script})],
                log=True, call=True, env={}, cwd='/',
                ignore_stdout=True, ignore_stderr=True).returncode)

  def testPAR(self):
    # Launch via a symlink.
    link = os.path.join(self.tmp, 'run_pytest')
    os.symlink(self.par, link)
    self._RunPytest([link])

  def testPARWithoutSymlink(self):
    # Launch directly through the PAR file.
    self._RunPytest([self.par, 'run_pytest'])

  def testUnzippedPAR(self):
    # String from make_par usage, to make sure it's running properly.
    usage = 'Creates a self-extracting Python executable.'

    link = os.path.join(self.tmp, 'make_par')
    os.symlink(self.par, link)

    # First try it without unzipping.
    process = Spawn([link, '--help'], log=True,
                    read_stdout=True, read_stderr=True)
    self.assertEqual(0, process.returncode)
    self.assertTrue(usage in process.stdout_data)
    self.assertFalse('WARNING' in process.stderr_data, process.stderr_data)

    # Unzip it in place.  Don't check_call=True, since the extra bytes
    # in the header will cause unzip to return an exit code of 1.
    Spawn(['unzip', self.par, '-d', self.tmp], log=True,
          ignore_stdout=True, ignore_stderr=True, call=True)

    # Patch the usage string in the unzipped file.
    make_par_path = os.path.join(self.tmp, 'cros', 'factory', 'cli',
                                 'make_par.py')
    modified_usage = 'BOOYAH'
    with open(make_par_path, 'r') as f:
      data = f.read()
    with open(make_par_path, 'w') as f:
      f.write(data.replace(usage, modified_usage))

    # Run help again.
    process = Spawn([link, '--help'], log=True,
                    read_stdout=True, read_stderr=True)
    self.assertEqual(0, process.returncode)
    self.assertTrue(modified_usage in process.stdout_data)
    self.assertTrue(
        'WARNING: factory.par has been unzipped' in process.stderr_data)

  def testInvalidModule(self):
    link = os.path.join(self.tmp, 'invalid')
    os.symlink(self.par, link)

    process = Spawn([link], call=True, read_stderr=True, env={}, cwd='/')
    self.assertEqual(1, process.returncode)
    self.assertTrue('To run a file within this archive,' in process.stderr_data)


class PARSelfTest(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.mkdtemp(prefix='make_par_unittest.')
    self.par = os.path.join(self.tmp, 'factory.par')
    self.assertTrue(make_par.main(['-o', self.par, '--include-unittest']))

  def tearDown(self):
    shutil.rmtree(self.tmp)

  def _RunUnittestInPar(self, unittest_module_path):
    link = os.path.join(self.tmp, 'run_unittest_in_par')
    os.symlink(self.par, link)
    process = Spawn([link, unittest_module_path], call=True, env={}, cwd='/')
    self.assertEqual(0, process.returncode)

  def testCrosConfig(self):
    self._RunUnittestInPar('cros.factory.utils.config_utils_unittest')


if __name__ == '__main__':
  unittest.main()
