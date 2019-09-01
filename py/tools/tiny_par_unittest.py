#!/usr/bin/env python2
#
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


from __future__ import print_function

import os
import shutil
import subprocess
import tempfile
import unittest


class TinyParTest(unittest.TestCase):
  """End-2-end tests for tiny_par."""

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp(prefix='partest_')
    self.par_file = os.path.join(self.temp_dir, 'test.par')
    tinypar = __file__.replace('_unittest', '')
    pkg_dir = os.path.join(os.path.dirname(tinypar), '..', '..', 'py_pkg')
    subprocess.check_call([
        tinypar, '--pkg', pkg_dir, '-o', self.par_file,
        '-m', 'cros.factory.tools.testdata.par_test'])

    self.symlink = os.path.join(self.temp_dir, 'par_test')
    os.symlink('test.par', self.symlink)

    hard_link_dir = os.path.join(self.temp_dir, 'hardlink')
    os.mkdir(hard_link_dir)
    self.hard_link = os.path.join(hard_link_dir, 'par_test')
    os.link(self.par_file, self.hard_link)

  def tearDown(self):
    if os.path.exists(self.temp_dir):
      shutil.rmtree(self.temp_dir)

  def testCommandInAfg(self):
    self.assertEqual(0,
                     subprocess.check_call([self.par_file, 'par_test', '0']),
                     'PAR CMD invocation failed.')
    self.assertEqual(1,
                     subprocess.call([self.par_file, 'non-exist', '0']),
                     'PAR CMD invocation wrong.')
    self.assertEqual(2,
                     subprocess.call([self.par_file, 'par_test', '2']),
                     'PAR CMD ARG invocation failed.')
    self.assertEqual('correct result\n',
                     subprocess.check_output(
                         [self.par_file, 'par_test', '0', 'correct', 'result']),
                     'PAR CMD ARG output incorrect.')

  def testCommandAsSymlink(self):
    self.assertEqual(0,
                     subprocess.check_call([self.symlink, '0']),
                     'SYMLINK invocation failed.')
    self.assertEqual(1,
                     subprocess.call([self.symlink, '1']),
                     'SYMLINK CMD ARG invocation failed.')
    self.assertEqual('correct result\n',
                     subprocess.check_output(
                         [self.symlink, '0', 'correct', 'result']),
                     'SYMLINK CMD ARG output incorrect.')

  def testCommandAsHardLink(self):
    self.assertEqual(0,
                     subprocess.check_call([self.hard_link, '0']),
                     'HARDLINK invocation failed.')
    self.assertEqual(1,
                     subprocess.call([self.hard_link, '1']),
                     'HARDLINK CMD ARG invocation failed.')
    self.assertEqual('correct result\n',
                     subprocess.check_output(
                         [self.hard_link, '0', 'correct', 'result']),
                     'HARDLINK CMD ARG output incorrect.')


if __name__ == '__main__':
  unittest.main()
