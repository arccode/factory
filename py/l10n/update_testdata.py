#!/usr/bin/python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Updates some constants in regions_unittest_data.py based on data pulled
from Chromium sources."""


import argparse
import glob
import json
import logging
import os
import re
import sys
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import CheckOutput, Spawn


# URLs to SVN paths.
SRC_SVN_URL = 'svn://svn.chromium.org/chrome/trunk/src'
BROWSER_SVN_URL = SRC_SVN_URL + '/chrome/browser'

TESTDATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


def WriteTestData(name, value):
  if not value:
    sys.exit('No values found for %s' % name)

  path = os.path.join(TESTDATA_PATH, name + '.yaml')
  logging.info('%s: writing %r', path, value)
  with open(path, 'w') as f:
    f.write('# Automatically generated from ToT Chromium sources\n'
            '# by update_testdata.py. Do not edit manually.\n'
            '\n')
    yaml.dump(value, f, default_flow_style=False)


def UpdateLanguages():
  """Updates languages.

  Valid languages are entries of the kAcceptLanguageList array in
  l10n_util.cc <http://goo.gl/z8XsZJ>.
  """
  cpp_code = CheckOutput(
    ['svn', 'cat', SRC_SVN_URL + '/ui/base/l10n/l10n_util.cc'],
    log=True)
  match = re.search('static[^\n]+kAcceptLanguageList\[\] = \{(.+?)^\}',
                    cpp_code, re.DOTALL | re.MULTILINE)
  if not match:
    sys.exit('Unable to find language list')

  languages = re.findall(r'"(.+)"', match.group(1))
  if not languages:
    sys.exit('Unable to parse language list')

  WriteTestData('languages', sorted(languages))


def UpdateTimeZones():
  """Updates time zones.

  Valid time zones are values of the kTimeZones array in timezone_settings.cc
  <http://goo.gl/WSVUeE>.
  """
  cpp_code = CheckOutput(
    ['svn', 'cat', SRC_SVN_URL + '/chromeos/settings/timezone_settings.cc'],
    log=True)
  match = re.search('static[^\n]+kTimeZones\[\] = \{(.+?)^\}',
                         cpp_code, re.DOTALL | re.MULTILINE)
  if not match:
    sys.exit('Unable to find time zones')

  time_zones = re.findall(r'"(.+)"', match.group(1))
  if not time_zones:
    sys.exit('Unable to parse time zones')

  WriteTestData('time_zones', time_zones)


def UpdateMigrationMap():
  """Updates the input method migration map.

  The source is the kEngineIdMigrationMap array in input_method_util.cc
  <http://goo.gl/cDO53r>.
  """
  cpp_code = CheckOutput(
    ['svn', 'cat',
     BROWSER_SVN_URL + '/chromeos/input_method/input_method_util.cc'],
    log=True)
  match = re.search(r'kEngineIdMigrationMap\[\]\[2\] = \{(.+?)^\}',
                    cpp_code, re.DOTALL | re.MULTILINE)
  if not match:
    sys.exit('Unable to find kEngineIdMigrationMap')

  map_code = match.group(1)
  migration_map = re.findall(r'{"(.+?)", "(.+?)"}', map_code)
  if not migration_map:
    sys.exit('Unable to parse kEngineIdMigrationMap')

  WriteTestData('migration_map', migration_map)


def UpdateInputMethods():
  """Updates input method IDs.

  This is the union of all 'id' fields in input_method/*.json
  <http://goo.gl/z4JGvK>.
  """
  root_dir = BROWSER_SVN_URL + '/resources/chromeos/input_method'
  input_methods = set()

  with file_utils.TempDirectory(prefix='input_methods.') as tmpdir:
    Spawn(['svn', 'export', root_dir], log=True, cwd=tmpdir, check_call=True,
          ignore_stdout=True)

    for f in glob.glob(os.path.join(tmpdir, 'input_method', '*.json')):
      contents = json.loads(file_utils.ReadFile(f))
      for c in contents['input_components']:
        input_methods.add(str(c['id']))

  WriteTestData('input_methods', sorted(input_methods))


def main():
  parser = argparse.ArgumentParser(
      description=('Updates some constants in regions_unittest_data.py based '
                   'on data pulled from Chromium sources. This overwrites '
                   'files in testdata, which you must then submit.'))
  unused_args = parser.parse_args()
  logging.basicConfig(level=logging.INFO)

  logging.info('If prompted for a SVN password, you may retrieve it '
               'from <https://chromium-access.appspot.com/>.')

  UpdateLanguages()
  UpdateTimeZones()
  UpdateInputMethods()
  UpdateMigrationMap()

  logging.info('Run "git diff %s" to see changes (if any).', TESTDATA_PATH)
  logging.info('Make sure to submit any changes to %s!', TESTDATA_PATH)


if __name__ == '__main__':
  main()
