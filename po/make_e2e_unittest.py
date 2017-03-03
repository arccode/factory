#!/usr/bin/python
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


class MakeTest(unittest.TestCase):
  """Integration test for Makefile of po file."""

  # TODO(pihsun): Mock and test the argument BOARD.

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp(prefix='po_make_e2etest.')
    self.po_dir = os.path.join(self.temp_dir, 'po')
    self.build_dir = os.path.join(self.temp_dir, 'build')
    self.locale_dir = os.path.join(self.build_dir, 'locale')

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
    nonexist_locale = 'nonexist_locale'
    po_path = os.path.join(self.po_dir, nonexist_locale + '.po')

    self.AssertMakeSuccess('init', LOCALE=nonexist_locale)
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


if __name__ == '__main__':
  unittest.main()
