#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from mox import In, Mox
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.commands.edit import ConfigEditor
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire.umpire_env import UmpireEnv
from cros.factory.utils import file_utils


TEST_DIR = os.path.dirname(sys.modules[__name__].__file__)
MINIMAL_UMPIRE_CONFIG = os.path.join(TEST_DIR, 'testdata',
                                     'minimal_empty_services_umpire.yaml')


class ConfigEditorTest(unittest.TestCase):
  def setUp(self):
    self.mox = Mox()
    self.editor = os.environ.get('EDITOR', 'vi').split()[0]

    # Prepare environment: create base and resources dir, add a staging
    # config file.
    self.env = UmpireEnv()
    self.temp_dir = tempfile.mkdtemp()
    self.env.base_dir = self.temp_dir
    os.makedirs(self.env.resources_dir)
    config_in_resources = self.env.AddResource(MINIMAL_UMPIRE_CONFIG)
    self.env.StageConfigFile(config_in_resources)

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

    if os.path.isdir(self.temp_dir):
      shutil.rmtree(self.temp_dir)

  def testEdit(self):
    self.mox.StubOutWithMock(subprocess, 'call')
    subprocess.call(In(self.editor)).WithSideEffects(
        lambda args: file_utils.PrependFile(args[-1], '# edited\n'))
    self.mox.ReplayAll()

    original_config = file_utils.Read(self.env.staging_config_file)
    editor = ConfigEditor(self.env)
    editor.Edit()
    self.assertEqual(self.env.staging_config_file, editor.config_file)
    new_config = file_utils.Read(self.env.staging_config_file)
    self.assertTrue(new_config.startswith('# edited'))
    self.assertNotEqual(original_config, new_config)

  def testEditSpecifyConfigFile(self):
    self.mox.StubOutWithMock(subprocess, 'call')
    subprocess.call(In(self.editor)).WithSideEffects(
        lambda args: file_utils.PrependFile(args[-1], '# edited\n'))
    self.mox.ReplayAll()

    editor = ConfigEditor(self.env)
    editor.Edit(config_file=MINIMAL_UMPIRE_CONFIG)
    self.assertEqual(MINIMAL_UMPIRE_CONFIG, editor.config_file)
    self.assertTrue(file_utils.Read(self.env.staging_config_file).startswith(
        '# edited'))

  def testEditSpecifyTempDir(self):
    self.mox.StubOutWithMock(subprocess, 'call')
    subprocess.call(In(self.editor)).WithSideEffects(
        lambda args: file_utils.PrependFile(args[-1], '# edited\n'))
    self.mox.ReplayAll()

    editor = ConfigEditor(self.env)
    editor.Edit(temp_dir=self.temp_dir)
    self.assertEqual(self.temp_dir, editor.temp_dir)
    self.assertTrue(file_utils.Read(self.env.staging_config_file).startswith(
        '# edited'))


  def testEditFailToEdit(self):
    self.mox.StubOutWithMock(subprocess, 'call')
    subprocess.call(In(self.editor)).AndRaise(IOError)
    self.mox.ReplayAll()

    editor = ConfigEditor(self.env)
    self.assertRaisesRegexp(UmpireError, 'Unable to invoke editor',
                            editor.Edit)

  def testEditFailToValidate(self):
    self.mox.StubOutWithMock(subprocess, 'call')
    # Write a wrong config file.
    subprocess.call(In(self.editor)).WithSideEffects(
        lambda args: file_utils.PrependFile(args[-1], '- - -'))
    self.mox.ReplayAll()

    editor = ConfigEditor(self.env)
    editor.max_retry = 1
    self.assertRaisesRegexp(UmpireError, 'Failed to validate config',
                            editor.Edit)
    config_lines = file_utils.ReadLines(editor.config_file_to_edit)
    self.assertTrue(config_lines[0].startswith(
        '# Failed to validate Umpire config'))


if __name__ == '__main__':
  unittest.main()
