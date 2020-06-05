# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import stat
import unittest

from cros.factory.probe_info_service.app_engine import bundle_builder
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


class ProbeConfigBundleBuilderTest(unittest.TestCase):
  def setUp(self):
    self._bundle_path = file_utils.CreateTemporaryFile()

    # Build-up a bundle file which is shared across different test cases.
    builder_inst = bundle_builder.BundleBuilder()
    builder_inst.AddRegularFile('reg_file', b'reg_content')
    builder_inst.AddExecutableFile('exec_file',
                                   b'#!/usr/bin/env sh\necho hi\n')
    builder_inst.AddExecutableFile(
        'runner',
        b'#!/usr/bin/env sh\n'
        b'echo "$@"\n'
        b'"$(dirname "$(realpath "$0")")/exec_file"\n'
        b'exit 123\n')
    builder_inst.SetRunnerFilePath('runner')
    file_utils.WriteFile(self._bundle_path, builder_inst.Build(), encoding=None)
    os.chmod(self._bundle_path, stat.S_IRUSR | stat.S_IXUSR)

  def testBadOptions(self):
    # `-z` is not a valid option
    retcode, unused_stdout, stderr = self._RunBundle(['-z'])
    self.assertNotEqual(retcode, 0)
    self.assertIn('usage', stderr.lower())

  def testPrintUsage(self):
    retcode, stdout, unused_stderr = self._RunBundle(['-h'])
    self.assertEqual(retcode, 0)
    self.assertIn('usage', stdout.lower())

  def testNoExecuteRunner(self):
    retcode, unused_stdout, unused_stderr = self._RunBundle(['-n'])
    self.assertEqual(retcode, 0)

  def testUnpackToSpecificFolder(self):
    for args in ([], ['-n']):
      with file_utils.TempDirectory() as path:
        self._RunBundle(args + ['-d', path])
        self.assertCountEqual(os.listdir(path),
                              ['reg_file', 'exec_file', 'runner'])

  def testRunTheRunner(self):
    retcode, stdout, unused_stderr = self._RunBundle(['--', '-a', 'arg', '-n'])
    self.assertEqual(retcode, 123)
    self.assertEqual(stdout, '-a arg -n\nhi\n')

  def _RunBundle(self, args):
    proc = process_utils.Spawn(
        [self._bundle_path] + args, read_stdout=True, read_stderr=True)
    return proc.returncode, proc.stdout_data, proc.stderr_data


if __name__ == '__main__':
  unittest.main()
