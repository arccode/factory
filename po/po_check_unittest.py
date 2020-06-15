#!/usr/bin/env python3
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import collections
import glob
import logging
import os
import re
import shutil
import string
import tempfile
import unittest

from cros.factory.test.i18n import translation
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


SCRIPT_DIR = os.path.dirname(__file__)


class _MockValue:
  """A mock value that accepts all format_spec for __format__."""
  def __format__(self, format_spec):
    del format_spec  # Unused.
    return ''


class PoBuildTest(unittest.TestCase):
  """Basic sanity check for po files."""

  @classmethod
  def setUpClass(cls):
    cls.temp_dir = tempfile.mkdtemp(prefix='po_check_test.')
    cls.po_dir = os.path.join(cls.temp_dir, 'po')
    cls.build_dir = os.path.join(cls.temp_dir, 'build')
    cls.locale_dir = os.path.join(cls.build_dir, 'locale')

    po_files = glob.glob(os.path.join(SCRIPT_DIR, '*.po'))
    os.makedirs(cls.po_dir)
    for po_file in po_files:
      shutil.copy(po_file, cls.po_dir)

    env = {'PO_DIR': cls.po_dir, 'BUILD_DIR': cls.build_dir}
    process_utils.Spawn(['make', '-C', SCRIPT_DIR, 'build'],
                        ignore_stdout=True, ignore_stderr=True,
                        env=env, check_call=True)

    translation.LOCALES = [translation.DEFAULT_LOCALE] + [
        os.path.splitext(os.path.basename(po_file))[0] for po_file in po_files]
    translation.LOCALE_DIR = cls.locale_dir

  @classmethod
  def tearDownClass(cls):
    if os.path.exists(cls.temp_dir):
      shutil.rmtree(cls.temp_dir)

  def setUp(self):
    self.formatter = string.Formatter()
    self.errors = []

  def tearDown(self):
    if self.errors:
      raise AssertionError('\n'.join(self.errors).encode('UTF-8'))

  def AddError(self, err):
    self.errors.append(err)

  def testFormatStringVariablesMatch(self):
    all_translations = translation.GetAllTranslations()

    for text in all_translations:
      default_text = text[translation.DEFAULT_LOCALE]
      default_vars = self._ExtractVariablesFromFormatString(
          default_text, translation.DEFAULT_LOCALE)
      for locale in translation.LOCALES:
        if locale == translation.DEFAULT_LOCALE:
          continue
        used_vars = self._ExtractVariablesFromFormatString(text[locale], locale)
        unknown_vars = used_vars - default_vars
        if unknown_vars:
          self.AddError(u'[%s] "%s": Unknown vars %r' %
                        (locale, text[locale], list(unknown_vars)))

        unused_vars = default_vars - used_vars
        if unused_vars:
          logging.warning('[%s] "%s": Unused vars %r', locale, text[locale],
                          list(unused_vars))

  def testFormatStringFormat(self):
    all_translations = translation.GetAllTranslations()

    kwargs = collections.defaultdict(_MockValue)
    for text in all_translations:
      for locale in translation.LOCALES:
        try:
          self.formatter.vformat(text[locale], [], kwargs)
        except Exception as e:
          self.AddError('[%s] "%s": %s' % (locale, text[locale], e))

  def _ExtractVariablesFromFormatString(self, format_str, locale):
    ret = set()
    for unused_text, field_name, unused_format_spec, unused_conversion in (
        self.formatter.parse(format_str)):
      if field_name is None:
        continue
      var_name = re.match('[a-zA-Z0-9_]*', field_name).group(0)
      if not var_name or re.match('[0-9]+$', var_name):
        self.AddError(u'[%s] "%s": Positional argument {%s} found' %
                      (locale, format_str, var_name))
      else:
        ret.add(var_name)
    return ret


class PoCheckTest(unittest.TestCase):
  """Check some formatting issue for po files."""
  def setUp(self):
    self.po_files = glob.glob(os.path.join(SCRIPT_DIR, '*.po'))

  def testNoFuzzy(self):
    err_files = []
    for po_file in self.po_files:
      po_lines = file_utils.ReadLines(po_file)
      if any(line.startswith('#, fuzzy') for line in po_lines):
        err_files.append(os.path.basename(po_file))

    self.assertFalse(
        err_files,
        "'#, fuzzy' lines found in files %r, please check the translation is "
        'correct and remove those lines.' % err_files)

  def testNoUnused(self):
    err_files = []
    for po_file in self.po_files:
      po_lines = file_utils.ReadLines(po_file)
      if any(line.startswith('#~') for line in po_lines):
        err_files.append(os.path.basename(po_file))

    self.assertFalse(
        err_files,
        "Lines started with '#~' found in files %r, please check if those lines"
        ' are unused and remove those lines.' % err_files)

  def testNoUnusedAgain(self):
    bad_lines = []
    for po_file in self.po_files:
      po_lines = file_utils.ReadLines(po_file)
      base_po_file = os.path.basename(po_file)
      last_line = ''
      is_first_msgid = True
      for line_number, line in enumerate(po_lines, 1):
        if line.startswith('msgid '):
          # Since po file always maps the first string to the header data and
          # the line before it can be any string, we skip the first msgid.
          # After the first msgid, every line before a msgid should start with
          # '#:' and contain the file reference it.
          if not is_first_msgid and not last_line.startswith('#:'):
            bad_lines.append((base_po_file, line_number))
          is_first_msgid = False
        last_line = line

    self.assertFalse(
        bad_lines,
        'Translations without file reference found in %s, please check if those'
        ' lines are unused and remove those lines.'
        % ', '.join('%s at line %d' % file_line for file_line in bad_lines))

class PoUpdateTest(unittest.TestCase):
  """Check that po update have been run."""
  def runTest(self):
    try:
      temp_dir = tempfile.mkdtemp(prefix='po_update_test.')
      po_dir = os.path.join(temp_dir, 'po')

      po_files = glob.glob(os.path.join(SCRIPT_DIR, '*.po'))
      os.makedirs(po_dir)
      for po_file in po_files:
        shutil.copy(po_file, po_dir)

      env = {'PO_DIR': po_dir}
      process_utils.Spawn(['make', '-C', SCRIPT_DIR, 'update'],
                          ignore_stdout=True, ignore_stderr=True,
                          env=env, check_call=True)

      err_files = []
      for po_file in po_files:
        new_po_file = os.path.join(po_dir, os.path.basename(po_file))

        # Compare two contents except the line of PO-Revision-Date
        old_content = file_utils.ReadLines(po_file)
        new_content = file_utils.ReadLines(new_po_file)

        if len(old_content) != len(new_content):
          err_files.append(os.path.basename(po_file))
          continue

        for old_line, new_line in zip(old_content, new_content):
          if old_line == new_line:
            continue

          # Ignore the line of PO-Revision-Date since the date
          # will be updated by `make update`
          if 'PO-Revision-Date' in old_line and \
             'PO-Revision-Date' in new_line:
            continue

          err_files.append(os.path.basename(po_file))
          break

      self.assertFalse(
          err_files,
          "Files %r are not updated, please run 'make -C po update' inside "
          'chroot and check the translations.' % err_files)

    finally:
      if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


if __name__ == '__main__':
  unittest.main()
