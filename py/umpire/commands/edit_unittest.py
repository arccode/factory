#!/usr/bin/python
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from mox import In, Mox, StrContains
import os
import subprocess
import sys
import unittest
import xmlrpclib

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.commands.edit import ConfigEditor
from cros.factory.umpire.common import UmpireError
from cros.factory.utils import file_utils


TEST_DIR = os.path.dirname(sys.modules[__name__].__file__)
MINIMAL_UMPIRE_CONFIG = os.path.join(TEST_DIR, 'testdata',
                                     'minimal_empty_services_umpire.yaml')
EDITOR_PREPEND = '# edited'
MOCK_RES_HASH = '##12345678'


class ConfigEditorTest(unittest.TestCase):
  def setUp(self):
    self.mox = Mox()
    self.umpire_cli = self.mox.CreateMockAnything()

    self.editor = os.environ.get('EDITOR', 'vi').split()[0]
    self.config_to_edit = file_utils.ReadFile(MINIMAL_UMPIRE_CONFIG)

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def MockUmpireCLIGetStagingConfig(self):
    """Mocks Umpire daemon's GetStagingConfig."""
    self.umpire_cli.GetStagingConfig(True).AndReturn(self.config_to_edit)

  def MockEditorCalled(self):
    """Simulates edit action by prepending '# edited\n'."""
    self.mox.StubOutWithMock(subprocess, 'call')
    subprocess.call(In(self.editor)).WithSideEffects(
        lambda args: file_utils.PrependFile(args[-1], EDITOR_PREPEND  + '\n'))

  def MockUmpireCLIValidate(self, config_basename=None):
    self.umpire_cli.ValidateConfig(StrContains(EDITOR_PREPEND))
    if not config_basename:
      config_basename = 'umpire.yaml'
    res_name = config_basename + MOCK_RES_HASH
    self.umpire_cli.UploadConfig(
        StrContains(config_basename),
        StrContains(EDITOR_PREPEND)).AndReturn(res_name)
    self.umpire_cli.StageConfigFile(res_name, True)

  def testEdit(self):
    self.MockUmpireCLIGetStagingConfig()
    self.MockEditorCalled()
    self.MockUmpireCLIValidate()
    self.mox.ReplayAll()

    editor = ConfigEditor(self.umpire_cli)
    editor.Edit()

    new_config = file_utils.Read(editor.config_file)
    self.assertTrue(new_config.startswith(EDITOR_PREPEND))
    self.assertNotEqual(self.config_to_edit, new_config)

  def testEditRetryOk(self):
    self.MockUmpireCLIGetStagingConfig()
    self.MockEditorCalled()
    self.umpire_cli.ValidateConfig(StrContains(EDITOR_PREPEND)).AndRaise(
        xmlrpclib.Fault(1, 'mock resource not found'))
    # edit again.
    subprocess.call(In(self.editor)).WithSideEffects(
        lambda args: file_utils.PrependFile(args[-1], '# edit again\n'))
    self.MockUmpireCLIValidate()
    self.mox.ReplayAll()

    editor = ConfigEditor(self.umpire_cli, max_retry=2)
    editor.Edit()

    new_config = file_utils.Read(editor.config_file)
    self.assertTrue(new_config.startswith('# edit again'))
    self.assertIn('mock resource not found', new_config)

  def testEditSpecifyConfigFile(self):
    # Skip get staging file from Umpire daemon.
    self.MockEditorCalled()
    self.MockUmpireCLIValidate(
        config_basename=os.path.basename(MINIMAL_UMPIRE_CONFIG))
    self.mox.ReplayAll()

    editor = ConfigEditor(self.umpire_cli)
    editor.Edit(config_file=MINIMAL_UMPIRE_CONFIG)
    self.assertTrue(file_utils.Read(editor.config_file).startswith(
        EDITOR_PREPEND))

  def testEditSpecifyTempDir(self):
    self.MockUmpireCLIGetStagingConfig()
    self.MockEditorCalled()
    self.MockUmpireCLIValidate()
    self.mox.ReplayAll()

    with file_utils.TempDirectory() as temp_dir:
      editor = ConfigEditor(self.umpire_cli, temp_dir=temp_dir)
      editor.Edit()
      self.assertEqual(temp_dir, editor.temp_dir)
      self.assertTrue(file_utils.Read(editor.config_file).startswith(
          EDITOR_PREPEND))

  def testEditFailToEdit(self):
    self.MockUmpireCLIGetStagingConfig()
    self.mox.StubOutWithMock(subprocess, 'call')
    subprocess.call(In(self.editor)).AndRaise(IOError)
    self.mox.ReplayAll()

    editor = ConfigEditor(self.umpire_cli)
    self.assertRaisesRegexp(UmpireError, 'Unable to invoke editor',
                            editor.Edit)

  def testEditFailToValidateLocally(self):
    self.MockUmpireCLIGetStagingConfig()
    # Prepend a wrong content to make a ill-formed config.
    self.mox.StubOutWithMock(subprocess, 'call')
    subprocess.call(In(self.editor)).WithSideEffects(
        lambda args: file_utils.PrependFile(args[-1], '- - -'))
    self.mox.ReplayAll()

    editor = ConfigEditor(self.umpire_cli)
    self.assertRaisesRegexp(UmpireError, 'Failed to validate config',
                            editor.Edit)
    config_lines = file_utils.ReadLines(editor.config_file)
    self.assertTrue(config_lines[0].startswith(
        '# Failed to load Umpire config'))

  def testEditFailToValidateUmpireDaemon(self):
    self.MockUmpireCLIGetStagingConfig()
    self.MockEditorCalled()
    self.umpire_cli.ValidateConfig(StrContains(EDITOR_PREPEND)).AndRaise(
        xmlrpclib.Fault(1, 'resource not found'))

    self.mox.ReplayAll()

    editor = ConfigEditor(self.umpire_cli)
    self.assertRaisesRegexp(UmpireError, 'Failed to validate config',
                            editor.Edit)
    config_lines = file_utils.ReadLines(editor.config_file)
    self.assertTrue(config_lines[0].startswith(
        '# Failed to validate Umpire config'))
    self.assertRegexpMatches(config_lines[1], 'resource not found')



if __name__ == '__main__':
  unittest.main()
