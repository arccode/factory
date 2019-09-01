#!/usr/bin/env python2
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import re
import shutil
from StringIO import StringIO
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.tools import audit_source_hashes
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn


class AuditSourceHashesTest(unittest.TestCase):

  def setUp(self):
    self.tmpdir = tempfile.mkdtemp(prefix='audit_source_hashes_unittest.')

  def tearDown(self):
    shutil.rmtree(self.tmpdir)

  def testBadReport(self):
    """Tests a report file that doesn't contain any events."""
    out = StringIO()
    bad_report = os.path.join(self.tmpdir, 'bad_report.tar.xz')
    file_utils.TouchFile(bad_report)
    self.assertRaisesRegexp(
        SystemExit, '^1$',
        audit_source_hashes.main, [bad_report], out)
    self.assertRegexpMatches(
        out.getvalue(),
        r'(?s).+AuditException: Unable to read events from report.+'
        r'\(tar returned 2\).+'
        r'Found 0 mismatched hashes and 1 exceptions.\n'
        r'FAILED \(0/1 samples passed\).\n$')

  def testThisSourceTree(self):
    """Tests running on the present source tree.

    This is comparing the tree to itself, so it should succeed."""
    out = StringIO()
    self.assertRaisesRegexp(
        SystemExit, '^0$', audit_source_hashes.main,
        [os.path.join(paths.FACTORY_DIR, 'py')], out)
    self.assertEquals('PASSED (1/1 samples passed).\n', out.getvalue())

  def testGooftoolLogSourceHashes(self):
    """'End-to-end' test using 'gooftool log_source_hashes'."""
    # Use tempdir as state root, so we don't end up going through a bunch
    # of old event logs.
    os.environ['CROS_FACTORY_DATA_DIR'] = self.tmpdir

    # Log the source hashes for this source tree.
    Spawn([os.path.join(paths.FACTORY_DIR, 'bin', 'gooftool'),
           'log_source_hashes'], log=True, check_call=True)

    # We should find the event in this log.  Check that it works.
    event_log_path = os.path.join(self.tmpdir, 'state', 'events', 'events')
    out = StringIO()
    self.assertRaisesRegexp(
        SystemExit, '^0$',
        audit_source_hashes.main, [event_log_path], out)

    # Change the hash of this source file in the event log entry.  It
    # should fail now.
    data = file_utils.ReadFile(event_log_path)
    data = re.sub(r'^(\s+tools/audit_source_hashes_unittest\.py: ).+',
                  r'\1deadbeef', data, flags=re.MULTILINE)
    bad_log_path = os.path.join(self.tmpdir, 'events')
    file_utils.WriteFile(bad_log_path, data)

    def AssertMismatch(log_path):
      out = StringIO()
      self.assertRaisesRegexp(SystemExit, '^1$',
                              audit_source_hashes.main, [log_path], out)
      self.assertRegexpMatches(
          out.getvalue(),
          r'In sample .+:\n'
          r'- tools/audit_source_hashes_unittest\.py: hash mismatch '
          r'\(expected .+, found deadbeef\)\n\n'
          r'Found 1 mismatched hashes and 0 exceptions\.\n'
          r'FAILED \(0/1 samples passed\)\.\n')

    # First try with the event log file itself.
    AssertMismatch(bad_log_path)
    # Build a fake report containing the events.  It should fail in the
    # same way.
    report = os.path.join(self.tmpdir, 'report.tar.xz')
    Spawn(['tar', '-acf', report,
           '-C', os.path.join(self.tmpdir), 'events'],
          check_call=True)
    AssertMismatch(report)


class FakeSourceTreeTest(unittest.TestCase):
  """Creates and tests based on fake source trees."""

  def setUp(self):
    self.tmpdir = tempfile.mkdtemp(prefix='audit_source_hashes_unittest.')

    # Create a fake source tree and save the path in self.py.
    self.py = os.path.join(self.tmpdir, 'py')
    os.mkdir(self.py)
    file_utils.WriteFile(os.path.join(self.py, 'a.py'), 'A')
    file_utils.WriteFile(os.path.join(self.py, 'b.py'), 'B')
    file_utils.WriteFile(os.path.join(self.py, 'c.py'), 'C')

    # Replicate the source tree under a 'sample' directory.
    # Save the path in self.py2.
    sample = os.path.join(self.tmpdir, 'sample')
    os.mkdir(sample)
    self.py2 = os.path.join(sample, 'py')
    shutil.copytree(self.py, self.py2)

  def tearDown(self):
    shutil.rmtree(self.tmpdir)

  def _ModifyTree(self):
    """Modifies py2 to differ from py."""
    os.rename(os.path.join(self.py2, 'b.py'), os.path.join(self.py2, 'b2.py'))
    file_utils.WriteFile(os.path.join(self.py2, 'c.py'), 'C!')
    # Now there are mismatches that we should detect.

  def _AssertMismatches(self, golden_source):
    """Asserts that golden_source and py2 have the expected mismatches."""
    out = StringIO()
    self._ModifyTree()
    self.assertRaisesRegexp(
        SystemExit, '^1$', audit_source_hashes.main,
        ['-g', golden_source, self.py2], out)
    self.assertRegexpMatches(
        out.getvalue(),
        r'In sample .+:\n'
        r'- b\.py: missing from sample\n'
        r'- b2\.py: unexpected file encountered in sample\n'
        r'- c\.py: hash mismatch .+\n\n'
        r'Found 3 mismatched hashes and 0 exceptions\.\n'
        r'FAILED \(0/1 samples passed\)\.\n')

  def testMatches(self):
    """Tests that py matches py2."""
    out = StringIO()
    self.assertRaisesRegexp(
        SystemExit, '^0$', audit_source_hashes.main,
        ['-g', self.py, self.py2], out)
    self.assertEquals('PASSED (1/1 samples passed).\n', out.getvalue())

  def testMismatches(self):
    """Tests that comparing py and py2 yields the expected mismatches."""
    self._AssertMismatches(self.py)

  def testFactoryToolkit(self):
    """Tests with a fake factory toolkit as the golden."""
    # First, create toolkit_contents.tar.xz containing a tar file like
    # the one encoded into a real toolkit.
    factory_dir = os.path.join(self.tmpdir, 'usr', 'local', 'factory')
    os.makedirs(factory_dir)
    os.rename(self.py, os.path.join(factory_dir, 'py'))
    tar_file = os.path.join(self.tmpdir, 'toolkit_contents.tar.xz')
    Spawn(['tar', '-acf', tar_file, '-C', self.tmpdir, './usr'],
          call=True)

    # Build a fake factory toolkit that knows only how to process
    # "install_factory_toolkit.run --tar".  It will be called by
    # audit_source_hashes with args like "--tar -acf -C destdir".
    toolkit_path = os.path.join(self.tmpdir, 'install_factory_toolkit.run')
    file_utils.WriteFile(
        toolkit_path,
        '#!/bin/bash\n'
        '[ "$1" == "--tar" ] || exit 1\n'  # First arg must be '--tar'
        'shift\n'                          # Remove '--tar'
        'tar_flags="$1"\n'                 # Save tar flags
        'shift\n'                          # Remove tar flags
        'tar "$tar_flags" "%s" "$@"\n'     # Call tar on tar_file
        % tar_file)
    os.chmod(toolkit_path, 0o555)

    # Now we can use the fake toolkit as a golden source.
    self._AssertMismatches(toolkit_path)

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
