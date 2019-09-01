#!/usr/bin/env python2
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""An integration test for SSHLink"""

import argparse
import logging
import os
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device.links import local
from cros.factory.device.links import ssh
from cros.factory.test.env import paths

dut_options = dict(
    identity=os.path.join(paths.FACTORY_DIR, 'setup', 'sshkeys',
                          'testing_rsa'))

class SSHLinkUnittest(unittest.TestCase):
  def setUp(self):
    if dut_options.get('identity'):
      os.chmod(dut_options.get('identity'), 0o600)
    self.ssh = ssh.SSHLink(**dut_options)
    self.local = local.LocalLink()

  def _RunAndCompare(self, cmd):
    # get output of SSHLink
    ssh_output = tempfile.TemporaryFile()
    self.ssh.Shell(cmd, stdout=ssh_output)

    # get output of LocalLink
    local_output = tempfile.TemporaryFile()
    self.local.Shell(cmd, stdout=local_output)

    ssh_output.seek(0)
    local_output.seek(0)
    self.assertEqual(ssh_output.readlines(), local_output.readlines())

    local_output.seek(0)
    logging.info(local_output.readlines())
    ssh_output.close()
    local_output.close()

  def testListEchoQuote(self):
    cmd = ['echo', '\'']
    self._RunAndCompare(cmd)

  def testShellEchoQuote(self):
    cmd = 'echo "\'"'
    self._RunAndCompare(cmd)

  def testShellSemiColon(self):
    cmd = 'echo 123; echo 456; echo 789'
    self._RunAndCompare(cmd)

  def testListSemiColon(self):
    cmd = ['echo', '123', ';', 'echo', '456', ';', 'echo', '789']
    self._RunAndCompare(cmd)

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)

  parser = argparse.ArgumentParser(description='Integration test for SSHLink')
  parser.add_argument('host', help='hostname of ssh target')
  parser.add_argument('-i', '--identity', help='path to an identity file')
  parser.add_argument('-u', '--user', help='user name')
  parser.add_argument('-p', '--port', type=int, help='port')
  args = parser.parse_args()
  dut_options.update([x for x in vars(args).iteritems() if x[1] is not None])

  logging.info('dut_options: %s', dut_options)

  suite = unittest.TestLoader().loadTestsFromTestCase(SSHLinkUnittest)
  unittest.TextTestRunner().run(suite)
