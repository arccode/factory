#!/usr/bin/env python2
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Ensures that factory documentation can be built properly."""


import os
import pprint
import re
import sys
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.utils.process_utils import Spawn


# Files allowed to have errors now.
BLACKLIST = []


"""Tests the overall documentation generation process."""


class DocTest(unittest.TestCase):

  def testMakeDoc(self):
    stderr_lines = Spawn(
        ['make', 'doc'], cwd=paths.FACTORY_DIR,
        check_output=True, read_stderr=True,
        log=True, log_stderr_on_error=True).stderr_lines()

    files_with_errors = set()

    for l in stderr_lines:
      match = re.match(r'^(([^:]+):)*(\d+): (ERROR|WARNING|SEVERE): (.+)',
                       l.strip())

      if match:
        basename = os.path.basename(match.group(1))
        blacklisted = basename in BLACKLIST
        sys.stderr.write('%s%s\n' % (
            l.strip(), ' (blacklisted)' if blacklisted else ''))
        files_with_errors.add(basename)

    if files_with_errors:
      # pprint for easy copy/paste to blacklist
      sys.stderr.write('Files with errors:\n')
      pprint.pprint(sorted(files_with_errors))

    failed_files = files_with_errors - set(BLACKLIST)
    if failed_files:
      self.fail('Found errors in non-blacklisted files %s; '
                'see stderr for details' % sorted(failed_files))


if __name__ == '__main__':
  unittest.main()
