# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Helper script for OEMs and ODMs.

This helper helps the OEM or ODM to do the following things easily:
  1. Get the number of available key from the DKPS.
  2. Upload a list of DRM keys to the DKPS.
  3. Request an available DRM key from the DKPS.

This script also supports mock mode. When running in mock mode:
  1. For getting the number of available keys, it will always return 1.
  2. For uploading new keys, it will only try to sign and encrypt the keys.
  3. For requesting a new key, it will return a mock key.

To use the helper, the user can either:
  1. Execute this script from the command line.
  2. Import this module and use the APIs of UploaderHelper, RequesterHelper.
"""

import argparse
import os
import shutil
import tempfile
import uuid
import xmlrpc.client

import gnupg


class BaseHelper:
  """The base helper class for uploader and requester.

  This class provides only AvaiableKeyCount() to retrieve the current unpaired
  keys.

  Properties:
    server_ip: DKPS IP.
    server_port: DKPS port.
    gpg: the GnuPG instance.
    client_key_fingerprint: fingerprint of the client's private key.
    server_key_fingerprint: fingerprint of the server's public key.
    passphrase: passphrase of the client's private key.
    dkps: the DKPS server server proxy instance.
  """

  def __init__(self, server_ip, server_port, server_key_file_path,
               client_key_file_path, passphrase_file_path):
    # Create GnuPG object.
    self.temp_dir = tempfile.mkdtemp()  # should be removed in __del__
    os.mkdir(os.path.join(self.temp_dir, 'gnupg'))
    self.gpg = gnupg.GPG(gnupghome=os.path.join(self.temp_dir, 'gnupg'))

    # Get server and client keys' fingerprints.
    with open(server_key_file_path) as f:
      self.server_key_fingerprint = (
          self.gpg.import_keys(f.read()).fingerprints[0])
    with open(client_key_file_path) as f:
      self.client_key_fingerprint = (
          self.gpg.import_keys(f.read()).fingerprints[0])

    # Get passphrase for client's key if needed.
    self.passphrase = None
    if passphrase_file_path is not None:
      with open(passphrase_file_path) as f:
        # Read only the first line and remove the newline character at the end.
        # This complies with the behavior of GnuPG when reading passphrase from
        # a file. If the newline character is not removed, encryption and
        # decryption will still work, but the character will be prepended to the
        # data, which is not desired.
        self.passphrase = f.readline().strip('\n')

    # Create RPC server object.
    self.server_ip = server_ip
    self.server_port = server_port
    self.dkps = xmlrpc.client.ServerProxy(
        'http://%s:%s' % (self.server_ip, self.server_port))

  def __del__(self):
    # Remove temp dir.
    try:
      shutil.rmtree(self.temp_dir)
    except Exception:
      pass  # doesn't matter

  def AvailableKeyCount(self):
    """Return the number of remaining keys from the DKPS."""
    signed_obj = self.gpg.sign(
        uuid.uuid4().hex, keyid=self.client_key_fingerprint,
        passphrase=self.passphrase)
    return self.dkps.AvailableKeyCount(signed_obj.data)


class RequesterHelper(BaseHelper):
  """The helper class for requester."""

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

  def Request(self, device_serial_number):
    """Request a DRM key by a device serial number from the DKPS.

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
        sign=self.client_key_fingerprint, passphrase=self.passphrase)

    encrypted_drm_key = self.dkps.Request(encrypted_obj.data)

    decrypted_obj = self.gpg.decrypt(encrypted_drm_key.data,
                                     passphrase=self.passphrase)
    if decrypted_obj.fingerprint != self.server_key_fingerprint:
      raise ValueError('Failed to verify the server signature')

    return decrypted_obj.data.decode('utf-8')

  def MockRequest(self, device_serial_number):
    """A mock Request() function for testing purpose.

    This function will still try to sign and encrypt the device serial number
    just like the normal one (to verify if GnuPG and python-gnupg are working),
    but won't try to contact the DKPS server. It will then return a mock DRM
    key, which allows the ODM to (partially) test their setup without really set
    up the DKPS server.

    See Request() for argument specification.

    Returns:
      A mock DRM key.
    """
    self.gpg.encrypt(
        device_serial_number, self.server_key_fingerprint, always_trust=True,
        sign=self.client_key_fingerprint, passphrase=self.passphrase)

    return RequesterHelper.MOCK_DRM_KEY


class UploaderHelper(BaseHelper):
  """The helper class for uploader."""

  def _GetSerializedDRMKeys(
      self, serialized_drm_keys=None, drm_keys_file_path=None):
    if ((serialized_drm_keys is None and drm_keys_file_path is None) or
        (serialized_drm_keys is not None and drm_keys_file_path is not None)):
      raise ValueError('Either serialized_drm_keys or drm_keys_file_path must '
                       'be given, but not both.')

    if drm_keys_file_path is not None:
      with open(drm_keys_file_path) as f:
        serialized_drm_keys = f.read()

    return serialized_drm_keys

  def Upload(self, serialized_drm_keys=None, drm_keys_file_path=None):
    """Upload a list of serialized DRM keys to DKPS.

    Either serialized_drm_keys or drm_keys_file_path must be given, but not
    both. If serialized_drm_keys is given, the function will use it directly. If
    drm_keys_file_path is given, the function will read its content and use it.

    This function will:
      1. Sign and encrypt the serialized DRM keys.
      2. Pass the signed and encrypted keys to DKPS Upload() call.

    Args:
      serialized_drm_keys: serialized DRM keys in a string.
      drm_keys_file_path: path to the DRM keys file.
    """
    serialized_drm_keys = self._GetSerializedDRMKeys(serialized_drm_keys,
                                                     drm_keys_file_path)

    encrypted_obj = self.gpg.encrypt(
        serialized_drm_keys, self.server_key_fingerprint, always_trust=True,
        sign=self.client_key_fingerprint, passphrase=self.passphrase)

    self.dkps.Upload(encrypted_obj.data)

  def MockUpload(self, serialized_drm_keys=None, drm_keys_file_path=None):
    """A mock Upload() function for testing purpose.

    This function will only try to sign and encrypt the serialized DRM keys just
    like the normal one (to verify if GnuPG and python-gnupg are working), but
    won't try to contact the DKPS server.

    See Upload() for argument specification.
    """
    serialized_drm_keys = self._GetSerializedDRMKeys(serialized_drm_keys,
                                                     drm_keys_file_path)

    self.gpg.encrypt(
        serialized_drm_keys, self.server_key_fingerprint, always_trust=True,
        sign=self.client_key_fingerprint, passphrase=self.passphrase)


def _ParseArguments():
  parser = argparse.ArgumentParser(description='DKPS helper')
  parser.add_argument('--mock', action='store_true',
                      help='run in mock mode, the script will not contact the '
                           'DKPS server, useful for testing purpose')
  parser.add_argument('--server_ip', required=True,
                      help='the key server IP')
  parser.add_argument('--server_port', required=True, type=int,
                      help='the key server port')
  parser.add_argument('--server_key_file_path', required=True,
                      help="path to the server's public key")
  parser.add_argument('--client_key_file_path', required=True,
                      help="path to the client's private key")
  parser.add_argument('--passphrase_file_path', default=None,
                      help="path to the passphrase file of the client's "
                           'private key')
  subparsers = parser.add_subparsers(dest='command')

  subparsers.add_parser(
      'available', help='display the available key count that remains')

  parser_upload = subparsers.add_parser('upload', help='upload DRM keys')
  parser_upload.add_argument('drm_keys_file_path',
                             help='path to the DRM keys file')

  parser_request = subparsers.add_parser('request', help='request a DRM key')
  parser_request.add_argument('serial_number', help='device serial number')

  return parser.parse_args()


def main():
  args = _ParseArguments()

  if args.command == 'available':
    if args.mock:
      print(1)
    else:
      helper = BaseHelper(
          args.server_ip, args.server_port, args.server_key_file_path,
          args.client_key_file_path, args.passphrase_file_path)
      print(helper.AvailableKeyCount())

  elif args.command == 'upload':
    helper = UploaderHelper(
        args.server_ip, args.server_port, args.server_key_file_path,
        args.client_key_file_path, args.passphrase_file_path)
    if args.mock:
      helper.MockUpload(drm_keys_file_path=args.drm_keys_file_path)
    else:
      helper.Upload(drm_keys_file_path=args.drm_keys_file_path)

  elif args.command == 'request':
    helper = RequesterHelper(
        args.server_ip, args.server_port, args.server_key_file_path,
        args.client_key_file_path, args.passphrase_file_path)
    if args.mock:
      print(helper.MockRequest(args.serial_number))
    else:
      print(helper.Request(args.serial_number))

  else:
    raise ValueError('Unknown command %s' % args.command)


if __name__ == '__main__':
  main()
