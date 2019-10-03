# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import glob
import os
import shutil
import tempfile
import unittest

from cros.factory.test.env import paths
from cros.factory.test.i18n import translation
from cros.factory.utils import process_utils


SCRIPT_DIR = os.path.dirname(__file__)
TESTDATA_DIR = os.path.join(SCRIPT_DIR, 'testdata')
PO_DIR = os.path.join(paths.FACTORY_DIR, 'po')


class I18nTestCase(unittest.TestCase):
  """Base class for unittests of i18n.

  This testcase would build .mo files from .po files inside testdata/ in
  setUpClass, put them in a temporary folder, and set variables in
  cros.factory.test.i18n.translation so the translation in testdata/ is used.
  """

  @classmethod
  def setUpClass(cls):
    cls.temp_dir = tempfile.mkdtemp(prefix='i18n_unittest.')
    cls.build_dir = os.path.join(cls.temp_dir, 'build')
    cls.locale_dir = os.path.join(cls.build_dir, 'locale')

    process_utils.Spawn(
        ['make', '-C', PO_DIR, 'build'],
        env={'PO_DIR': TESTDATA_DIR, 'BUILD_DIR': cls.build_dir},
        check_call=True, ignore_stdout=True, ignore_stderr=True)

    translation.LOCALE_DIR = cls.locale_dir
    translation.LOCALES = [translation.DEFAULT_LOCALE] + sorted([
        os.path.basename(p)
        for p in glob.glob(os.path.join(cls.locale_dir, '*'))])
    # Force reload translations
    translation._TRANSLATIONS_DICT = {}  # pylint: disable=protected-access

  @classmethod
  def tearDownClass(cls):
    if os.path.exists(cls.temp_dir):
      shutil.rmtree(cls.temp_dir)
