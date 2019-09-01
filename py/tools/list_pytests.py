#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""List all available pytests.

This script output all pytests in py/test/pytests in JSON format, with most
non-pytest items filtered (unittests, utils, ...)
"""

import argparse
import json
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test.test_lists import test_object
from cros.factory.test.utils import pytest_utils


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
      'base_dir', nargs='?', default=paths.FACTORY_DIR,
      help='The base directory of factory repository (or factory-board/files).')
  options = parser.parse_args()

  pytest_list = pytest_utils.GetPytestList(options.base_dir)

  if options.label:
    pytest_list = map(_ToI18nLabel, pytest_list)

  print json.dumps(pytest_list)


if __name__ == '__main__':
  main()
