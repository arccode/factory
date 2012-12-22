#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''A test for make_par.py.

This also tests run_pytest.
'''


import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.tools import make_par
from cros.factory.utils.process_utils import Spawn


class MakePARTest(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.mkdtemp(prefix='make_par_unittest.')
    self.par = os.path.join(self.tmp, 'factory.par')
    self.assertTrue(make_par.main(['-o', self.par]))

  def tearDown(self):
    shutil.rmtree(self.tmp)

  def testPAR(self):
    link = os.path.join(self.tmp, 'run_pytest')
    os.symlink(self.par, link)

    for expected_retcode, script in ((0, 'pass'),
                                     (1, 'raise ValueError')):
      self.assertEquals(
        expected_retcode,
        Spawn([link, 'execpython', '--args', 'dict(script=%r)' % script],
              log=True, call=True, env={}, cwd='/',
              ignore_stdout=True, ignore_stderr=True).returncode)

  def testInvalidModule(self):
    link = os.path.join(self.tmp, 'invalid')
    os.symlink(self.par, link)

    process = Spawn([link], call=True, read_stderr=True, env={}, cwd='/')
    self.assertEqual(1, process.returncode)
    self.assertTrue('To run a file within this archive,' in process.stderr_data)


if __name__ == '__main__':
  unittest.main()
