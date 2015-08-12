# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Helper script for the ODM (requester).

This helper helps the ODM to do the following things easily:
  1. Get the number of available key from the DKPS.
  2. Request an available DRM key from the DKPS.

This script also supports mock mode. When running in mock mode:
  1. For getting the number of available keys, it will always return 1.
  2. For requesting a new key, it will return a mock key.
"""

import argparse
import logging
import os
import shutil
import tempfile
import uuid
import xmlrpclib

import gnupg


class RequesterHelper(object):
  """The helper class for requester.

  Properties:
    server_ip: DKPS IP.
    server_port: DKPS port.
    gpg: the GnuPG instance.
    requester_key_fingerprint: fingerprint of the requester's private key.
    server_key_fingerprint: fingerprint of the server's public key.
    passphrase: passphrase of the requester's private key.
    dkps: the DKPS server server proxy instance.
  """

  MOCK_DRM_KEY = {
      'secure_boot_key': '0f0e0d0c0b0a09080706050403020100',
      'device_key': '0f0e0d0c',
      'enhanced_key_sequence': (
          'e0beadde00000000e1beadde00000000e2beadde00000000e3beadde00000000e4be'
          'adde00000000e5beaddeb00000006196d2c999e12cec543d872a0e73b166a19eff28'
          '16233fd68b75bd3557713c49ba3aa5b512dc5db3bff9fdcddf5dc9d4ab1d4cb550e1'
          '5b45c9fb30b467b4b1d6d9df3cd7de843bdfeed9fbb8bf19a037e84bb3eee2f9b8ac'
          'd7972fa833eb4bc5cd90eb0c0434a96a320d64391b2b581fd9ca8da37c03a142067d'
          '4843a2c0bd9e577fb71859ce4ea7811ea098f68315343e5e43c1db0b7430657a99e2'
          '18758003f2299e32f138c4b0af03927e2c5609d8e6beadde00000000e7beadde0000'
          '0000')}
  """Mock key for testing purpose, used by MockRequest()."""

  def __init__(self, server_ip, server_port, gpg, requester_key_fingerprint,
               server_key_fingerprint, passphrase):
    self.server_ip = server_ip
    self.server_port = server_port
    self.gpg = gpg
    self.requester_key_fingerprint = requester_key_fingerprint
    self.server_key_fingerprint = server_key_fingerprint
    self.passphrase = passphrase

    self.dkps = xmlrpclib.ServerProxy(
        'http://%s:%s' % (self.server_ip, self.server_port))

  def AvailableKeyCount(self):
    """Returns the number of remaining keys from the DKPS."""
    signed_obj = self.gpg.sign(
        uuid.uuid4().hex, keyid=self.requester_key_fingerprint,
        passphrase=self.passphrase)
    return self.dkps.AvailableKeyCount(signed_obj.data)

  def Request(self, device_serial_number):
    """Requests a DRM key by a device serial number from the DKPS.

    This function will:
      1. Sign and encrypt a device serial number.
      2. Pass the signed and encrypted serial number to DKPS Request() call.
      3. Decrypt and verify the returned DRM key.
      4. Output the DRM key in JSON format.

    Args:
      device_serial_number: the device serial number.

    Returns:
      An available DRM key from the DKPS.
    """
    encrypted_obj = self.gpg.encrypt(
        device_serial_number, self.server_key_fingerprint, always_trust=True,
        sign=self.requester_key_fingerprint, passphrase=self.passphrase)

    encrypted_drm_key = self.dkps.Request(encrypted_obj.data)

    decrypted_obj = self.gpg.decrypt(encrypted_drm_key,
                                     passphrase=self.passphrase)
    if decrypted_obj.fingerprint != self.server_key_fingerprint:
      raise ValueError('Failed to verify the server signature')

    return decrypted_obj.data

  def MockRequest(self, device_serial_number):
    """A mock Request() function for testing purpose.

    This function will still try to sign and encrypt the device serial number
    just like the normal one (to verify if GnuPG and python-gnupg are working),
    but won't try to contact the DKPS server. It will then return a mock DRM
    key, which allows the ODM to (partially) test their setup without really set
    up the DKPS server.

    Args:
      device_serial_number: the device serial number.

    Returns:
      A mock DRM key.
    """
    self.gpg.encrypt(
        device_serial_number, self.server_key_fingerprint, always_trust=True,
        sign=self.requester_key_fingerprint, passphrase=self.passphrase)

    return RequesterHelper.MOCK_DRM_KEY


def _ParseArguments():
  parser = argparse.ArgumentParser(description='DKPS helper for requester')
  parser.add_argument('--mock', action='store_true',
                      help='run in mock mode, the script will not contact the '
                           'DKPS server, useful for testing purpose')
  parser.add_argument('--server_ip', required=True,
                      help='the key server IP')
  parser.add_argument('--server_port', required=True, type=int,
                      help='the key server port')
  parser.add_argument('--server_key_file_path', required=True,
                      help="path to the DKPS's public key")
  parser.add_argument('--requester_key_file_path', required=True,
                      help="path to the requester's private key")
  parser.add_argument('--passphrase_file_path', default=None,
                      help="path to the passphrase file of the requester's "
                           'private key')
  subparsers = parser.add_subparsers(dest='command')

  subparsers.add_parser(
      'available', help='display the available key count that remains')

  parser_request = subparsers.add_parser('request', help='request a DRM key')
  parser_request.add_argument('serial_number', help='device serial number')

  return parser.parse_args()


def main():
  args = _ParseArguments()

  try:
    temp_dir = tempfile.mkdtemp()
    gnupg_homedir = os.path.join(temp_dir, 'gnupg')
    gpg = gnupg.GPG(gnupghome=gnupg_homedir)

    with open(args.server_key_file_path) as f:
      server_key_fingerprint = gpg.import_keys(f.read()).fingerprints[0]
    with open(args.requester_key_file_path) as f:
      requester_key_fingerprint = gpg.import_keys(f.read()).fingerprints[0]

    if args.passphrase_file_path is None:
      passphrase = None
    else:
      with open(args.passphrase_file_path) as f:
        passphrase = f.read()

    requester_helper = RequesterHelper(
        args.server_ip, args.server_port, gpg, requester_key_fingerprint,
        server_key_fingerprint, passphrase)
    if args.command == 'available':
      if args.mock:
        print 1
      else:
        print requester_helper.AvailableKeyCount()
    elif args.command == 'request':
      if args.mock:
        print requester_helper.MockRequest(args.serial_number)
      else:
        print requester_helper.Request(args.serial_number)
    else:
      raise ValueError('Unkonw command %s' % args.command)
  finally:
    try:
      shutil.rmtree(temp_dir)
    except BaseException as e:
      logging.exception(e)


if __name__ == '__main__':
  main()
