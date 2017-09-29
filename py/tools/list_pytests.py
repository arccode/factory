#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""List all available pytests.

This script output all pytests in py/test/pytests in JSON format, with most
non-pytest items filtered (unittests, utils, ...)
"""


import argparse
import glob
import json
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test.test_lists import test_object

_BLACKLIST_SUFFIX = ['_unittest', '_automator', '_e2etest', '_utils', '_host']


def _GetPytestList(base_dir):
  pytest_dir = os.path.join(base_dir, 'test', 'pytests')
  files = glob.glob(os.path.join(pytest_dir, '*.py'))
  files.extend(glob.glob(os.path.join(pytest_dir, '*', '*.py')))
  files.sort()

  def _IsExtraFile(filename):
    name = os.path.splitext(os.path.basename(filename))[0]
    if name in ['__init__', 'factory_common']:
      return True
    if any(name.endswith(suffix) for suffix in _BLACKLIST_SUFFIX):
      return True
    return False

  return [f[len(pytest_dir)+1:] for f in files if not _IsExtraFile(f)]


def _ToI18nLabel(name):
  name = os.path.splitext(name)[0]
  return 'i18n! %s' % test_object.FactoryTest.PytestNameToLabel(
      name.replace('/', '.'))


def main():
  parser = argparse.ArgumentParser(
      description='List all pytests available and output a JSON.')
  parser.add_argument(
      '-l', '--i18n-label', dest='label', action='store_true',
      help='Output the I18n label generated from pytest filename.')
  parser.add_argument(
      'base_dir', nargs='?', default=paths.FACTORY_PYTHON_PACKAGE_DIR,
      help='The Python base directory of factory repository.')
  options = parser.parse_args()

  pytest_list = _GetPytestList(options.base_dir)

  if options.label:
    pytest_list = map(_ToI18nLabel, pytest_list)

  print json.dumps(pytest_list)


if __name__ == '__main__':
  main()
