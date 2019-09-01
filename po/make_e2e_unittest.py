#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import gettext
import glob
import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


SCRIPT_DIR = os.path.dirname(__file__)
DOMAIN = 'factory'

MOCK_PO_HEADER = r"""
msgid ""
msgstr ""
"Project-Id-Version: ChromeOS Factory Software\n"
"POT-Creation-Date: 2017-01-05 07:36+CST\n"
"PO-Revision-Date: 2017-01-05 07:36+CST\n"
"Last-Translator: ChromeOS Factory Team\n"
"Language-Team: ChromeOS Factory Team\n"
"Language: Some language\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Generated-By: pygettext.py 1.5\n"
"""
MOCK_MSGID = '__mocked_msgid_e2e_unittest'
MOCK_MSGSTR = '__mocked_msgstr_e2e_unittest'
NONEXIST_LOCALE = 'nonexist_locale'


class MakeTest(unittest.TestCase):
  """Integration test for Makefile of po file."""

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp(prefix='po_make_e2etest.')
    self.po_dir = os.path.join(self.temp_dir, 'po')
    self.build_dir = os.path.join(self.temp_dir, 'build')
    self.locale_dir = os.path.join(self.build_dir, 'locale')
    self.board_files_dir = os.path.join(self.temp_dir, 'board')
    self.board_po_dir = os.path.join(self.board_files_dir, 'po')

    po_files = glob.glob(os.path.join(SCRIPT_DIR, '*.po'))
    os.makedirs(self.po_dir)
    for po_file in po_files:
      shutil.copy(po_file, self.po_dir)
    self.locales = [os.path.splitext(os.path.basename(po_file))[0]
                    for po_file in po_files]

  def tearDown(self):
    if os.path.exists(self.temp_dir):
      shutil.rmtree(self.temp_dir)

  def RunMake(self, *args, **kwargs):
    kwargs.update({'PO_DIR': self.po_dir, 'BUILD_DIR': self.build_dir})
    return process_utils.Spawn(['make', '-C', SCRIPT_DIR] + list(args),
                               ignore_stdout=True, ignore_stderr=True,
                               env=kwargs, call=True).returncode

  def AssertMakeSuccess(self, *args, **kwargs):
    self.assertEqual(0, self.RunMake(*args, **kwargs))

  def testMakeInit(self):
    po_path = os.path.join(self.po_dir, NONEXIST_LOCALE + '.po')

    self.AssertMakeSuccess('init', LOCALE=NONEXIST_LOCALE)
    self.assertTrue(os.path.exists(po_path))
    self.assertIn('PO-Revision-Date: ', file_utils.ReadFile(po_path))

  def testMakeInitExistLocale(self):
    for locale in self.locales:
      self.assertNotEqual(0, self.RunMake('init', LOCALE=locale))

  def testMakeUpdate(self):
    self.AssertMakeSuccess('update')

  def testMakeBuild(self):
    self.AssertMakeSuccess('build')
    for locale in self.locales:
      translation = gettext.translation(DOMAIN, self.locale_dir, [locale])
      # Assert that metadata for po file can be read.
      self.assertIn('PO-Revision-Date: ', translation.ugettext(''))

  def testBoardMakeInit(self):
    po_path = os.path.join(self.board_po_dir, NONEXIST_LOCALE + '.po')

    self.AssertMakeSuccess(
        'init', LOCALE=NONEXIST_LOCALE, BOARD_FILES_DIR=self.board_files_dir)
    self.assertTrue(os.path.exists(po_path))
    self.assertIn('PO-Revision-Date: ', file_utils.ReadFile(po_path))

  def testBoardMakeInitExistLocale(self):
    for locale in self.locales:
      self.assertNotEqual(0, self.RunMake(
          'init', LOCALE=locale, BOARD_FILES_DIR=self.board_files_dir))

  def testBoardMakeUpdateExistLocale(self):
    for locale in self.locales:
      po_path = os.path.join(self.board_po_dir, locale + '.po')
      self.AssertMakeSuccess(
          'update', LOCALE=locale, BOARD_FILES_DIR=self.board_files_dir)
      self.assertTrue(os.path.exists(po_path))
      self.assertIn('PO-Revision-Date: ', file_utils.ReadFile(po_path))

  def PrepareBoardMockPoFiles(self):
    for locale in self.locales + [NONEXIST_LOCALE]:
      po_path = os.path.join(self.board_po_dir, locale + '.po')
      file_utils.TryMakeDirs(os.path.dirname(po_path))
      with open(po_path, 'a') as fp:
        fp.write('%s\n\nmsgid "%s"\nmsgstr "%s"\n' %
                 (MOCK_PO_HEADER, MOCK_MSGID, MOCK_MSGSTR))

  def testBoardMakeBuild(self):
    self.PrepareBoardMockPoFiles()
    self.AssertMakeSuccess('build', BOARD_FILES_DIR=self.board_files_dir)

    for locale in self.locales + [NONEXIST_LOCALE]:
      translation = gettext.translation(DOMAIN, self.locale_dir, [locale])
      # Assert that metadata for po file can be read and the mocked po file is
      # merged.
      self.assertIn('PO-Revision-Date: ', translation.ugettext(''))
      self.assertEqual(MOCK_MSGSTR, translation.ugettext(MOCK_MSGID))

if __name__ == '__main__':
  unittest.main()
