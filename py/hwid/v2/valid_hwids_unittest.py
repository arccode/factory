#!/usr/bin/env python2
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import glob
import logging
import os
import re
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.utils.process_utils import Spawn


def Indent(data):
  return re.sub('(?m)^', '    ', data)


class ValidHWIDsTest(unittest.TestCase):

  def runTest(self):
    hwid_dir = os.path.join(
        os.environ['CROS_WORKON_SRCROOT'],
        'src', 'platform', 'chromeos-hwid', 'v2')

    if not os.path.exists(hwid_dir):
      print 'ValidHWIDsTest: ignored, no %s in source tree.' % hwid_dir
      return

    # Create a temporary copy of the hwid directory
    tmp = tempfile.mkdtemp(prefix='hwid.')

    # Copy all files into that directory
    for f in glob.glob(os.path.join(hwid_dir, '*')):
      shutil.copyfile(f, os.path.join(tmp, os.path.basename(f)))

    # List all hwids
    Spawn([os.path.join(paths.FACTORY_DIR, 'py', 'hwid', 'v2', 'hwid_tool.py'),
           '-p', tmp,
           'hwid_list'],
          log=True, log_stderr_on_error=True, check_call=True, read_stdout=True)

    # Make sure that the directories are identical
    process = Spawn(['diff', '-u', '-r', hwid_dir, tmp],
                    log=True, call=True)
    self.assertFalse(process.returncode,
                     ('Running hwid_tool hwid_list causes changes in %s (see '
                      'diffs above); files in source tree are not canonical?')
                     % hwid_dir)

    # Passed!  Delete the temp directory (otherwise, leave it for inspection)
    shutil.rmtree(tmp)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
