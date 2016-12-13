#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import

from cros.factory.test import pytests
from cros.factory.test.utils.pytest_utils import LoadPytestModule
from cros.factory.utils import file_utils


class LoadPytestModuleTest(unittest.TestCase):

  @staticmethod
  def CreateScript(tmpdir, script_path):
    """Create an python script under `tmpdir` with path=`script_path`.

    The created script file will be empty, the `__init__.py`s will also be
    created to make this script file importable.

    Args:
      tmpdir: the root directory.
      script_path: path of script file relative to `tmpdir`.
    """

    # make sure there is no slash in the beginning.
    if script_path.startswith('/'):
      script_path = script_path.lstrip('/')

    # create directories
    if os.path.dirname(script_path):
      os.makedirs(os.path.dirname(os.path.join(tmpdir, script_path)))

    dirs = os.path.dirname(script_path).split('/')
    for idx in xrange(len(dirs) + 1):
      file_utils.TouchFile(
          os.path.join(os.path.join(tmpdir, *dirs[:idx]), '__init__.py'))

    # create python script
    file_utils.TouchFile(os.path.join(tmpdir, script_path))


  def setUp(self):
    self.pytests_root = os.path.dirname(pytests.__file__)
    self.tmpdir = tempfile.mkdtemp(dir=self.pytests_root)

  def tearDown(self):
    shutil.rmtree(self.tmpdir)

  def testLoadX(self):
    with file_utils.UnopenedTemporaryFile(
        suffix='.py', dir=self.pytests_root) as script_file:
      (pytest_name, _) = os.path.splitext(os.path.basename(script_file))
      module = LoadPytestModule(pytest_name)
      self.assertEquals(module.__file__, script_file)
      # remove tmpXXXXXX.pyc
      os.unlink(script_file + 'c')

  def testLoadXYZ(self):
    LoadPytestModuleTest.CreateScript(self.tmpdir, 'x/y/z.py')

    basename = os.path.basename(self.tmpdir)
    pytest_name = basename + '.x.y.z'
    module = LoadPytestModule(pytest_name)
    self.assertEquals(module.__file__, os.path.join(self.tmpdir, 'x/y/z.py'))

  def testBackwardCompatibility(self):
    basename = os.path.basename(self.tmpdir)

    for suffix in ['', '_automator', '_e2etest', '_automator_private']:
      LoadPytestModuleTest.CreateScript(
          self.tmpdir, basename + suffix + '.py')

    for suffix in ['', '_automator', '_e2etest', '_automator_private']:
      module = LoadPytestModule(basename + suffix)
      self.assertEquals(module.__file__,
                        os.path.join(self.tmpdir, basename + suffix + '.py'))


if __name__ == '__main__':
  unittest.main()
