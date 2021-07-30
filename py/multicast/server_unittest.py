#!/usr/bin/env python3
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
from unittest import mock

from cros.factory.multicast import server
from cros.factory.utils import process_utils


FAKE_UFTP_ARGS = server.UftpArgs('/path/to/resources/fake_file',
                                 '224.1.1.1:8093', '/path/to/log_dir',
                                 '192.168.1.1')


class UftpProcessTest(unittest.TestCase):

  def setUp(self):
    self.uftp_proc = server.UftpProcess(FAKE_UFTP_ARGS)

  @mock.patch('cros.factory.utils.process_utils.Spawn')
  def testSpawn(self, mock_spawn):
    self.uftp_proc.Spawn()

    mock_spawn.assert_called_with([
        '/usr/bin/uftp', '-M', '224.1.1.1', '-t', '10', '-u', '8093', '-p',
        '8093', '-x', '0', '-S', '/path/to/log_dir', '-C', 'tfmcc', '-s', '50',
        '-I', '192.168.1.1', '/path/to/resources/fake_file'
    ], stderr=process_utils.PIPE)

  @mock.patch('cros.factory.utils.process_utils.Spawn')
  def testSpawnWithDefaultInterface(self, mock_spawn):
    uftp_args_empty_interface = server.UftpArgs('/path/to/resources/fake_file',
                                                '224.1.1.1:8093',
                                                '/path/to/log_dir', '')
    uftp_proc = server.UftpProcess(uftp_args_empty_interface)

    uftp_proc.Spawn()

    mock_spawn.assert_called_with([
        '/usr/bin/uftp', '-M', '224.1.1.1', '-t', '10', '-u', '8093', '-p',
        '8093', '-x', '0', '-S', '/path/to/log_dir', '-C', 'tfmcc', '-s', '50',
        '/path/to/resources/fake_file'
    ], stderr=process_utils.PIPE)

  @mock.patch('cros.factory.multicast.server.UftpProcess.Spawn')
  @mock.patch('logging.error')
  def testRespawnIfDiedAnnounceTimedOut(self, mock_logging, mock_spawn):
    # pylint: disable=protected-access
    self.uftp_proc._process = mock.Mock(returncode=7)

    self.uftp_proc.RespawnIfDied()

    mock_logging.assert_not_called()
    mock_spawn.assert_called_once()

  @mock.patch('cros.factory.multicast.server.UftpProcess.Spawn')
  @mock.patch('logging.error')
  def testRespawnIfDiedUnexpectedError(self, mock_logging, mock_spawn):
    # pylint: disable=protected-access
    self.uftp_proc._process = mock.Mock(returncode=1)

    self.uftp_proc.RespawnIfDied()

    mock_logging.assert_called_once()
    mock_spawn.assert_called_once()

  def testKill(self):
    # pylint: disable=protected-access
    self.uftp_proc._process = mock.Mock()

    self.uftp_proc.Kill()

    self.uftp_proc._process.kill.assert_called_once()
    self.uftp_proc._process.wait.assert_called_once()


if __name__ == '__main__':
  unittest.main()
