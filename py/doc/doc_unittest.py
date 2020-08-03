#!/usr/bin/env python3
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

from cros.factory.test.env import paths
from cros.factory.utils.process_utils import Spawn


# Files allowed to have errors now.
BLOCKLIST = []
RSTS_BLOCKLIST = []


class DocTest(unittest.TestCase):
  """Tests the overall documentation generation process."""

  def testMakeDoc(self):
    stderr_lines = Spawn(
        ['make', 'doc'], cwd=paths.FACTORY_DIR,
        check_output=True, read_stderr=True,
        log=True, log_stderr_on_error=True).stderr_lines()

    files_with_errors = set()
    rsts_with_errors = set()

    for l in stderr_lines:
      match = re.match(r'^(([^:]+):)*(\d+): (ERROR|WARNING|SEVERE): (.+)',
                       l.strip())

      if match:
        basename = os.path.basename(match.group(1))
        blocklisted = basename in BLOCKLIST
        sys.stderr.write('%s%s\n' % (
            l.strip(), ' (blocklisted)' if blocklisted else ''))
        files_with_errors.add(basename)
        continue

      match = re.match(
          r'^ERROR:root:Failed to generate document for pytest (.+).$',
          l.strip())

      if match:
        blocklisted = match.group(1) in RSTS_BLOCKLIST
        sys.stderr.write(
            '%s%s\n' % (l.strip(), ' (blocklisted)' if blocklisted else ''))
        rsts_with_errors.add(match.group(1))

    if files_with_errors:
      # pprint for easy copy/paste to BLOCKLIST
      sys.stderr.write('Files with errors:\n')
      pprint.pprint(sorted(files_with_errors), sys.stderr)

    if rsts_with_errors:
      # pprint for easy copy/paste to RSTS_BLOCKLIST
      sys.stderr.write('generate_rsts with errors:\n')
      pprint.pprint(sorted(rsts_with_errors), sys.stderr)

    error_messages = []
    failed_files = files_with_errors - set(BLOCKLIST)
    if failed_files:
      error_messages.append('Found errors in non-blocklisted files %s; '
                            'see stderr for details' % sorted(failed_files))

    failed_rsts = rsts_with_errors - set(RSTS_BLOCKLIST)
    if failed_rsts:
      error_messages.append(
          'Found errors in non-blocklisted pytests %s; '
          'Run "bin/generate_rsts -o build/tmp/docsrc" for details' %
          sorted(failed_rsts))

    if error_messages:
      self.fail('\n'.join(error_messages))


if __name__ == '__main__':
  unittest.main()
