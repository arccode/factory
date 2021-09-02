#!/usr/bin/env python3
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import textwrap
import unittest
from unittest import mock

from cros.factory.multicast import server
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


FAKE_UFTP_ARGS = server.UftpArgs('/path/to/resources/fake_file',
                                 '224.1.1.1:8093', '/path/to/log_dir',
                                 '192.168.1.1')


class DummyLogger:
  called = False

  def Log(self, unused_log):
    self.called = True


class UftpProcessTest(unittest.TestCase):

  def setUp(self):
    self.logger = DummyLogger()
    self.uftp_proc = server.UftpProcess(FAKE_UFTP_ARGS, self.logger)

  @mock.patch('cros.factory.utils.process_utils.Spawn')
  def testSpawn(self, mock_spawn):
    self.uftp_proc.Spawn()

    mock_spawn.assert_called_with([
        '/usr/bin/uftp', '-M', '224.1.1.1', '-P', '224.1.1.1', '-t', '10', '-u',
        '8093', '-p', '8093', '-x', '0', '-S', '/path/to/log_dir', '-C',
        'tfmcc', '-s', '50', '-I', '192.168.1.1', '/path/to/resources/fake_file'
    ], stderr=process_utils.PIPE)

  @mock.patch('cros.factory.utils.process_utils.Spawn')
  def testSpawnWithDefaultInterface(self, mock_spawn):
    uftp_args_empty_interface = server.UftpArgs('/path/to/resources/fake_file',
                                                '224.1.1.1:8093',
                                                '/path/to/log_dir', '')
    uftp_proc = server.UftpProcess(uftp_args_empty_interface, DummyLogger())

    uftp_proc.Spawn()

    mock_spawn.assert_called_with([
        '/usr/bin/uftp', '-M', '224.1.1.1', '-P', '224.1.1.1', '-t', '10', '-u',
        '8093', '-p', '8093', '-x', '0', '-S', '/path/to/log_dir', '-C',
        'tfmcc', '-s', '50', '/path/to/resources/fake_file'
    ], stderr=process_utils.PIPE)

  @mock.patch('cros.factory.multicast.server.UftpProcess.Spawn')
  def testRespawnIfDiedAnnounceTimedOut(self, mock_spawn):
    # pylint: disable=protected-access
    self.uftp_proc._process = mock.Mock(returncode=7)

    self.uftp_proc.RespawnIfDied()

    self.assertFalse(self.logger.called)
    mock_spawn.assert_called_once()

  @mock.patch('cros.factory.multicast.server.UftpProcess.Spawn')
  def testRespawnIfDiedUnexpectedError(self, mock_spawn):
    # pylint: disable=protected-access
    self.uftp_proc._process = mock.Mock(returncode=1)

    self.uftp_proc.RespawnIfDied()

    self.assertTrue(self.logger.called)
    mock_spawn.assert_called_once()

  def testKill(self):
    # pylint: disable=protected-access
    self.uftp_proc._process = mock.Mock()

    self.uftp_proc.Kill()

    self.uftp_proc._process.kill.assert_called_once()
    self.uftp_proc._process.wait.assert_called_once()


class GetLoggerTest(unittest.TestCase):

  def testGetLogger(self):
    LOG_FILENAME = 'test.log'
    with file_utils.TempDirectory() as log_dir:
      log_path = os.path.join(log_dir, LOG_FILENAME)
      # pylint: disable=protected-access
      logger = server.MulticastServer._GetLogger('fake_project', log_path)
      logger.Log('test logging')
      with open(log_path, 'r') as fp:
        log_content = fp.read()
      self.assertRegex(log_content, '.*:ERROR:fake_project:test logging$')


class MulticastServerTest(unittest.TestCase):

  def setUp(self):
    with mock.patch('cros.factory.multicast.server.MulticastServer._GetLogger',
                    return_value=DummyLogger()):
      self.multicast_server = server.MulticastServer('fake_project',
                                                     '/path/to/log_dir')

  @mock.patch('cros.factory.utils.json_utils.LoadFile')
  def testGetUftpArgsFromUmpire(self, mock_load_file):
    mock_load_file.return_value = {
        "test_image": {
            "part1": "fake_image.part1",
            "part3": "fake_image.part3",
            "part4": "fake_image.part4"
        },
        "toolkit": {
            "file": "fake_file",
            "version": "Fake toolkit"
        },
        "multicast": {
            "server_ip": "192.168.1.1",
            "test_image": {
                "part1": "224.1.1.1:8094",
                "part3": "224.1.1.1:8095",
                "part4": "224.1.1.1:8096"
            },
            "toolkit": {
                "file": "224.1.1.1:8093"
            }
        }
    }
    _EXPECTED_UFTP_ARGS = [
        server.UftpArgs(
            '/var/db/factory/umpire/fake_project/resources/fake_file',
            '224.1.1.1:8093', '/path/to/log_dir/uftp_fake_file.log',
            '192.168.1.1'),
        server.UftpArgs(
            '/var/db/factory/umpire/fake_project/resources/fake_image.part1',
            '224.1.1.1:8094', '/path/to/log_dir/uftp_fake_image.part1.log',
            '192.168.1.1'),
        server.UftpArgs(
            '/var/db/factory/umpire/fake_project/resources/fake_image.part3',
            '224.1.1.1:8095', '/path/to/log_dir/uftp_fake_image.part3.log',
            '192.168.1.1'),
        server.UftpArgs(
            '/var/db/factory/umpire/fake_project/resources/fake_image.part4',
            '224.1.1.1:8096', '/path/to/log_dir/uftp_fake_image.part4.log',
            '192.168.1.1')
    ]

    scanned_args = self.multicast_server.GetUftpArgsFromUmpire()

    self.assertEqual(set(scanned_args), set(_EXPECTED_UFTP_ARGS))

  @mock.patch('cros.factory.utils.json_utils.LoadFile')
  def testGetUftpArgsFromUmpireError(self, mock_load_file):
    mock_load_file.side_effect = FileNotFoundError()

    scanned_args = self.multicast_server.GetUftpArgsFromUmpire()

    self.assertEqual(scanned_args, [])

  @mock.patch('cros.factory.multicast.server.UftpProcess.Spawn')
  def testStartAll(self, mock_spawn):
    self.multicast_server.uftp_args = [FAKE_UFTP_ARGS]

    self.multicast_server.StartAll()

    mock_spawn.assert_called()
    # pylint: disable=protected-access
    self.assertEqual(self.multicast_server._uftp_procs,
                     [server.UftpProcess(FAKE_UFTP_ARGS, DummyLogger())])

  def testStopAll(self):
    mock_uftp_process = mock.Mock()
    # pylint: disable=protected-access
    self.multicast_server._uftp_procs = [mock_uftp_process]

    self.multicast_server.StopAll()

    mock_uftp_process.Kill.assert_called()
    self.assertEqual(self.multicast_server._uftp_procs, [])

  def testRespawnDead(self):
    mock_uftp_process = mock.Mock()
    # pylint: disable=protected-access
    self.multicast_server._uftp_procs = [mock_uftp_process]

    self.multicast_server.RespawnDead()

    mock_uftp_process.RespawnIfDied.assert_called()


class IsServiceEnabledTest(unittest.TestCase):

  @mock.patch('cros.factory.utils.json_utils.LoadFile')
  def testEnabled(self, mock_load_file):
    mock_load_file.return_value = {
        'services': {
            'multicast': {
                'active': True
            }
        }
    }
    ret = server.IsServiceEnabled('fake_project')
    self.assertTrue(ret)

  @mock.patch('cros.factory.utils.json_utils.LoadFile')
  def testDisabled(self, mock_load_file):
    mock_load_file.return_value = {
        'services': {
            'multicast': {
                'active': False
            }
        }
    }
    ret = server.IsServiceEnabled('fake_project')
    self.assertFalse(ret)

  @mock.patch('cros.factory.utils.json_utils.LoadFile')
  def testReadFail(self, mock_load_file):
    mock_load_file.side_effect = FileNotFoundError()
    ret = server.IsServiceEnabled('fake_project')
    self.assertFalse(ret)


class IsUmpireEnabledTest(unittest.TestCase):

  @mock.patch('cros.factory.utils.process_utils.CheckOutput')
  def testEnabled(self, mock_check_output):
    mock_check_output.return_value = textwrap.dedent("""\
        dome_mcast
        dome_nginx
        dome_uwsgi
        umpire_fake_project
        umpire_fake2""")

    ret = server.IsUmpireEnabled('fake_project')

    self.assertTrue(ret)

  @mock.patch('cros.factory.utils.process_utils.CheckOutput')
  def testDisabled(self, mock_check_output):
    mock_check_output.return_value = textwrap.dedent("""\
        dome_mcast
        dome_nginx
        dome_uwsgi
        umpire_fake2""")

    ret = server.IsUmpireEnabled('fake_project')

    self.assertFalse(ret)


class MockMulticastServer(mock.Mock):
  pass


class MulticastServerManagerTest(unittest.TestCase):

  def setUp(self):
    self.manager = server.MulticastServerManager('/path/to/log_dir')
    self.fake_args_a = [FAKE_UFTP_ARGS]
    self.fake_args_b = [
        server.UftpArgs('/path/to/resources/another_fake_file',
                        '224.1.2.3:8093', '/path/to/log_dir', '192.168.1.1')
    ]
    mock_server_a = MockMulticastServer()
    mock_server_b = MockMulticastServer()

    # Initialize both servers with `fake_args_a`.
    mock_server_a.uftp_args = self.fake_args_a
    mock_server_a.GetUftpArgsFromUmpire.return_value = self.fake_args_a
    mock_server_b.uftp_args = self.fake_args_a
    mock_server_b.GetUftpArgsFromUmpire.return_value = self.fake_args_a
    # pylint: disable=protected-access
    self.manager._servers = {
        'fake_project_a': mock_server_a,
        'fake_project_b': mock_server_b
    }

  @mock.patch('cros.factory.multicast.server.MulticastServer',
              return_value=MockMulticastServer())
  @mock.patch.object(server.MulticastServerManager, '_ScanActiveProjects',
                     return_value=['fake_project_b', 'fake_project_c'])
  def testCreateAndDeleteServers(self, unused_mock_scan, unused_mock_server):
    # pylint: disable=protected-access
    mock_server_a = self.manager._servers['fake_project_a']
    mock_server_b = self.manager._servers['fake_project_b']

    self.manager.CreateAndDeleteServers()

    mock_server_a.StopAll.assert_called_once()
    mock_server_b.StopAll.assert_not_called()
    self.assertEqual(
        sorted(self.manager._servers.keys()),
        ['fake_project_b', 'fake_project_c'])
    self.assertEqual(self.manager._servers['fake_project_b'], mock_server_b)
    self.assertIsInstance(self.manager._servers['fake_project_c'],
                          MockMulticastServer)

  def testUpdateServersArgs(self):
    """This test starts with both of the servers having fake_args_a, and tests
    the behavior when server_b changes."""
    # pylint: disable=protected-access
    mock_server_a = self.manager._servers['fake_project_a']
    mock_server_b = self.manager._servers['fake_project_b']

    mock_server_b.GetUftpArgsFromUmpire.return_value = self.fake_args_b

    self.manager.UpdateServerArgs()

    mock_server_a.RespawnDead.assert_called_once()
    mock_server_a.StopAll.assert_not_called()
    mock_server_a.StartAll.assert_not_called()

    mock_server_b.StopAll.assert_called_once()
    mock_server_b.StartAll.assert_called_once()

    self.assertEqual(mock_server_a.uftp_args, self.fake_args_a)
    self.assertEqual(mock_server_b.uftp_args, self.fake_args_b)


if __name__ == '__main__':
  unittest.main()
