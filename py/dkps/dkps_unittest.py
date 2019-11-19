#!/usr/bin/env python2
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The DRM Keys Provisioning Server (DKPS) test module."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

import gnupg

import factory_common  # pylint: disable=unused-import
from cros.factory.dkps import dkps
from cros.factory.utils import net_utils
from cros.factory.utils import sync_utils


FNULL = open(os.devnull, 'w')  # for hiding unnecessary messages from subprocess

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

# Mock key list for testing.
MOCK_KEY_LIST = [
    {'Magic': 'magic001', 'DeviceID': '001', 'Key': 'key001', 'ID': 'id001'},
    {'Magic': 'magic002', 'DeviceID': '002', 'Key': 'key002', 'ID': 'id002'},
    {'Magic': 'magic003', 'DeviceID': '003', 'Key': 'key003', 'ID': 'id003'}]

# Mock encerypted VPD list for testing. This list must contain exactly the same
# number of elements as MOCK_KEY_LIST.
encrypted_vpd_list = [
    '0123456789',
    'qwertyuiop',
    'asdfghjkl;']


class DRMKeysProvisioningServerTest(unittest.TestCase):

  def setUp(self):
    # Create a temp folder for SQLite3 and GnuPG.
    self.temp_dir = tempfile.mkdtemp()
    self.log_file_path = os.path.join(self.temp_dir, 'dkps.log')
    self.database_file_path = os.path.join(self.temp_dir, 'dkps.db')
    self.server_gnupg_homedir = os.path.join(self.temp_dir, 'gnupg', 'server')
    uploader_gnupg_homedir = os.path.join(self.temp_dir, 'gnupg', 'uploader')
    requester_gnupg_homedir = os.path.join(self.temp_dir, 'gnupg', 'requester')

    self.dkps = dkps.DRMKeysProvisioningServer(self.database_file_path,
                                               self.server_gnupg_homedir)
    self.dkps.Initialize(
        server_key_file_path=os.path.join(SCRIPT_DIR, 'testdata', 'server.key'))

    self.db_connection, self.db_cursor = dkps.GetSQLite3Connection(
        self.database_file_path)

    # Retrieve the server key fingerprint.
    self.db_cursor.execute(
        "SELECT * FROM settings WHERE key = 'server_key_fingerprint'")
    self.server_key_fingerprint = self.db_cursor.fetchone()['value']

    # Create server, uploader, requester GPG instances. Export server's public
    # key to uploader and requester.
    self.server_gpg = gnupg.GPG(gnupghome=self.server_gnupg_homedir)
    exported_server_key = self.server_gpg.export_keys(
        self.server_key_fingerprint)
    self.server_key_file_path = os.path.join(self.temp_dir, 'server.pub')
    with open(self.server_key_file_path, 'w') as f:
      f.write(exported_server_key)
    self.uploader_gpg = gnupg.GPG(gnupghome=uploader_gnupg_homedir)
    self.uploader_gpg.import_keys(exported_server_key)
    self.requester_gpg = gnupg.GPG(gnupghome=requester_gnupg_homedir)
    self.requester_gpg.import_keys(exported_server_key)

    # Passphrase for uploader and requester private keys.
    self.passphrase = 'taiswanleba'
    self.passphrase_file_path = os.path.join(self.temp_dir, 'passphrase')
    with open(self.passphrase_file_path, 'w') as f:
      f.write(self.passphrase)

    # Import uploader key.
    with open(os.path.join(SCRIPT_DIR, 'testdata', 'uploader.key')) as f:
      self.uploader_key_fingerprint = (
          self.uploader_gpg.import_keys(f.read()).fingerprints[0])
    # Output uploader key to a file for DKPS.AddProject().
    self.uploader_public_key_file_path = os.path.join(self.temp_dir,
                                                      'uploader.pub')
    with open(self.uploader_public_key_file_path, 'w') as f:
      f.write(self.uploader_gpg.export_keys(self.uploader_key_fingerprint))
    self.uploader_private_key_file_path = os.path.join(self.temp_dir,
                                                       'uploader')
    with open(self.uploader_private_key_file_path, 'w') as f:
      f.write(self.uploader_gpg.export_keys(
          self.uploader_key_fingerprint, True))

    # Import requester key.
    with open(os.path.join(SCRIPT_DIR, 'testdata', 'requester.key')) as f:
      self.requester_key_fingerprint = (
          self.requester_gpg.import_keys(f.read()).fingerprints[0])
    # Output requester key to a file for DKPS.AddProject().
    self.requester_public_key_file_path = os.path.join(self.temp_dir,
                                                       'requester.pub')
    with open(self.requester_public_key_file_path, 'w') as f:
      f.write(self.requester_gpg.export_keys(self.requester_key_fingerprint))
    self.requester_private_key_file_path = os.path.join(self.temp_dir,
                                                        'requester')
    with open(self.requester_private_key_file_path, 'w') as f:
      f.write(self.requester_gpg.export_keys(
          self.requester_key_fingerprint, True))

    self.server_process = None
    self.port = net_utils.FindUnusedTCPPort()

  def runTest(self):
    self.dkps.AddProject(
        'TestProject', self.uploader_public_key_file_path,
        self.requester_public_key_file_path, 'sample_parser.py',
        'sample_filter.py')

    # Test add duplicate project.
    with self.assertRaisesRegexp(ValueError, 'already exists'):
      self.dkps.AddProject(
          'TestProject', self.uploader_public_key_file_path,
          self.requester_public_key_file_path, 'sample_parser.py',
          'sample_filter.py')

    # TODO(littlecvr): Test dkps.UpdateProject().

    # Start the server.
    self.server_process = subprocess.Popen(
        ['python2', os.path.join(SCRIPT_DIR, 'dkps.py'),
         '--log_file_path', self.log_file_path,
         '--database_file_path', self.database_file_path,
         '--gnupg_homedir', self.server_gnupg_homedir,
         'listen', '--port', str(self.port)],
        stdout=FNULL, stderr=FNULL)

    sync_utils.WaitFor(lambda: net_utils.ProbeTCPPort(net_utils.LOCALHOST,
                                                      self.port), 2)

    # Upload DRM keys.
    drm_keys_file_path = os.path.join(self.temp_dir, 'mock_drm_keys')
    with open(drm_keys_file_path, 'w') as f:
      f.write(json.dumps(MOCK_KEY_LIST))
    self._Upload(drm_keys_file_path)

    # Test upload duplicate DRM keys.
    with self.assertRaises(subprocess.CalledProcessError):
      self._Upload(drm_keys_file_path)

    # Request and finalize DRM keys.
    for i in xrange(len(MOCK_KEY_LIST)):
      # Check available key count.
      expected_available_key_count = len(MOCK_KEY_LIST) - i
      available_key_count = int(self._CallHelper(
          self.requester_private_key_file_path, 'available'))
      self.assertEqual(expected_available_key_count, available_key_count)

      # Request.
      device_serial_number = 'SN%.6d' % i
      serialized_key = self._Request(device_serial_number)
      self.assertEqual(MOCK_KEY_LIST[i], json.loads(serialized_key))

    # Test request but insufficient keys left.
    with self.assertRaises(subprocess.CalledProcessError):
      self._Request('INSUFFICIENT_KEY')

    self.dkps.RemoveProject('TestProject')

    # Test remove non-exist project.
    with self.assertRaises(dkps.ProjectNotFoundException):
      self.dkps.RemoveProject('NonExistProject')

    self.dkps.Destroy()

  def tearDown(self):
    if self.server_process:
      self.server_process.terminate()
      self.server_process.wait()

    self.db_connection.close()

    if os.path.exists(self.temp_dir):
      shutil.rmtree(self.temp_dir)

  def _Upload(self, drm_keys_file_path):
    return self._CallHelper(
        self.uploader_private_key_file_path, 'upload', [drm_keys_file_path])

  def _Request(self, device_serial_number):
    return self._CallHelper(
        self.requester_private_key_file_path, 'request', [device_serial_number])

  def _CallHelper(self, client_key_file_path, command, extra_args=None):
    extra_args = extra_args if extra_args else []
    return subprocess.check_output(
        ['python2', os.path.join(SCRIPT_DIR, 'helpers.py'),
         '--server_ip', 'localhost',
         '--server_port', str(self.port),
         '--client_key_file_path', client_key_file_path,
         '--server_key_file_path', self.server_key_file_path,
         '--passphrase_file_path', self.passphrase_file_path,
         command] + extra_args,
        stderr=FNULL)


if __name__ == '__main__':
  unittest.main()
