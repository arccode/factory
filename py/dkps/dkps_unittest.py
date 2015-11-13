#!/usr/bin/python
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

import factory_common  # pylint: disable=W0611
from cros.factory.dkps import dkps


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

  SERVER_PORT = 5438

  def setUp(self):
    # Create a temp folder for SQLite3 and GnuPG.
    self.temp_dir = tempfile.mkdtemp()
    self.database_file_path = os.path.join(self.temp_dir, 'dkps.db')
    self.server_gnupg_homedir = os.path.join(self.temp_dir, 'gnupg', 'server')
    uploader_gnupg_homedir = os.path.join(self.temp_dir, 'gnupg', 'uploader')
    requester_gnupg_homedir = os.path.join(self.temp_dir, 'gnupg', 'requester')

    self.dkps = dkps.DRMKeysProvisioningServer(self.database_file_path,
                                               self.server_gnupg_homedir)
    self.dkps.Initialize({'key_length': 1024})  # use shorter key to speed up

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

    # Generate uploader key.
    uploader_key_input_data = self.uploader_gpg.gen_key_input(
        name_real='DKPS Uploader',
        name_email='chromeos-factory-dkps@google.com',
        name_comment='DKPS uploader key for unit tests',
        key_length=1024, passphrase=self.passphrase)
    self.uploader_key_fingerprint = self.uploader_gpg.gen_key(
        uploader_key_input_data).fingerprint
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

    # Generate requester key.
    requester_key_input_data = self.requester_gpg.gen_key_input(
        name_real='DKPS Requester',
        name_email='chromeos-factory-dkps@google.com',
        name_comment='DKPS requester key for unit tests',
        key_length=1024, passphrase=self.passphrase)
    self.requester_key_fingerprint = self.requester_gpg.gen_key(
        requester_key_input_data).fingerprint
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
        ['python', os.path.join(SCRIPT_DIR, 'dkps.py'),
         '--database_file_path', self.database_file_path,
         '--gnupg_homedir', self.server_gnupg_homedir,
         'listen', '--port', str(DRMKeysProvisioningServerTest.SERVER_PORT)],
        stdout=FNULL, stderr=FNULL)

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
      available_key_count = int(subprocess.check_output(
          ['python', os.path.join(SCRIPT_DIR, 'requester_helper.py'),
           '--server_ip', 'localhost',
           '--server_port', str(DRMKeysProvisioningServerTest.SERVER_PORT),
           '--requester_key_file_path', self.requester_private_key_file_path,
           '--server_key_file_path', self.server_key_file_path,
           '--passphrase_file_path', self.passphrase_file_path,
           'available']))
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
    return subprocess.check_output(
        ['python', os.path.join(SCRIPT_DIR, 'uploader_helper.py'),
         '--server_ip', 'localhost',
         '--server_port', str(DRMKeysProvisioningServerTest.SERVER_PORT),
         '--uploader_key_file_path', self.uploader_private_key_file_path,
         '--server_key_file_path', self.server_key_file_path,
         '--passphrase_file_path', self.passphrase_file_path,
         'upload', drm_keys_file_path],
        stderr=FNULL)

  def _Request(self, device_serial_number):
    return subprocess.check_output(
        ['python', os.path.join(SCRIPT_DIR, 'requester_helper.py'),
         '--server_ip', 'localhost',
         '--server_port', str(DRMKeysProvisioningServerTest.SERVER_PORT),
         '--requester_key_file_path', self.requester_private_key_file_path,
         '--server_key_file_path', self.server_key_file_path,
         '--passphrase_file_path', self.passphrase_file_path,
         'request', device_serial_number],
        stderr=FNULL)


if __name__ == '__main__':
  unittest.main()
