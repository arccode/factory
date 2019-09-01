#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import sys
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.utils.pytest_utils import LoadPytestModule
from cros.factory.utils import file_utils


_PYTEST_MODULES = ['cros', 'factory', 'test', 'pytests']


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


  def ReloadPytestModules(self):
    module = sys.modules[_PYTEST_MODULES[0]]
    reload(module)
    for submodule in _PYTEST_MODULES[1:]:
      module = getattr(module, submodule)
      reload(module)


  def setUp(self):
    self.tmp_root = tempfile.mkdtemp(prefix='pytest_utils_unittest.')

    # Some hack for python modules to make sure that our test module in temp
    # directory is used.
    sys.path.insert(0, self.tmp_root)

    self.pytests_root = os.path.join(self.tmp_root, *_PYTEST_MODULES)
    os.makedirs(self.pytests_root)

    path = self.tmp_root
    for name in _PYTEST_MODULES:
      path = os.path.join(path, name)
      file_utils.TouchFile(os.path.join(path, '__init__.py'))

    # Make sure that the module is imported.
    __import__('.'.join(_PYTEST_MODULES))
    self.ReloadPytestModules()

    self.tmpdir = tempfile.mkdtemp(dir=self.pytests_root)

  def tearDown(self):
    shutil.rmtree(self.tmp_root)
    sys.path.pop(0)
    self.ReloadPytestModules()

  def testLoadX(self):
    with file_utils.UnopenedTemporaryFile(
        suffix='.py', dir=self.pytests_root) as script_file:
      (pytest_name, _) = os.path.splitext(os.path.basename(script_file))
      module = LoadPytestModule(pytest_name)
      self.assertEquals(module.__file__, script_file)
      # remove tmpXXXXXX.pyc
      file_utils.TryUnlink(script_file + 'c')

  def testLoadXYZ(self):
    LoadPytestModuleTest.CreateScript(self.tmpdir, 'x/y/z.py')

    basename = os.path.basename(self.tmpdir)
    pytest_name = basename + '.x.y.z'
    module = LoadPytestModule(pytest_name)
    self.assertEquals(module.__file__, os.path.join(self.tmpdir, 'x/y/z.py'))


if __name__ == '__main__':
  unittest.main()
