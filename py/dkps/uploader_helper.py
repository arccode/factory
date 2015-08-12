# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Helper script for the OEM (uploader).

This helper helps the OEM to do the following things easily:
  1. Get the number of available key from the DKPS.
  2. Upload a list of DRM keys to the DKPS.

This script also supports mock mode. When running in mock mode:
  1. For getting the number of available keys, it will always return 1.
  2. For uploading new keys, it will only try to sign and encrypt the keys.
"""

import argparse
import logging
import os
import shutil
import tempfile
import uuid
import xmlrpclib

import gnupg


class UploaderHelper(object):
  """The helper class for uploader.

  Properties:
    server_ip: DKPS IP.
    server_port: DKPS port.
    gpg: the GnuPG instance.
    uploader_key_fingerprint: fingerprint of the uploader's private key.
    server_key_fingerprint: fingerprint of the server's public key.
    passphrase: passphrase of the uploader's private key.
    dkps: the DKPS server server proxy instance.
  """

  def __init__(self, server_ip, server_port, gpg, uploader_key_fingerprint,
               server_key_fingerprint, passphrase):
    self.server_ip = server_ip
    self.server_port = server_port
    self.gpg = gpg
    self.uploader_key_fingerprint = uploader_key_fingerprint
    self.server_key_fingerprint = server_key_fingerprint
    self.passphrase = passphrase

    self.dkps = xmlrpclib.ServerProxy(
        'http://%s:%s' % (self.server_ip, self.server_port))

  def AvailableKeyCount(self):
    """Returns the number of remaining keys from the DKPS."""
    signed_obj = self.gpg.sign(
        uuid.uuid4().hex, keyid=self.uploader_key_fingerprint,
        passphrase=self.passphrase)
    return self.dkps.AvailableKeyCount(signed_obj.data)

  def Upload(self, serialized_drm_keys):
    """Uploads a list of serialized DRM keys to DKPS.

    This function will:
      1. Sign and encrypt the serialized DRM keys.
      2. Pass the signed and encrypted keys to DKPS Upload() call.

    Args:
      serialized_drm_keys: serialized DRM keys in a string.
    """
    encrypted_obj = self.gpg.encrypt(
        serialized_drm_keys, self.server_key_fingerprint, always_trust=True,
        sign=self.uploader_key_fingerprint, passphrase=self.passphrase)

    self.dkps.Upload(encrypted_obj.data)

  def MockUpload(self, serialized_drm_keys):
    """A mock Upload() function for testing purpose.

    This function will only try to sign and encrypt the serialized DRM keys just
    like the normal one (to verify if GnuPG and python-gnupg are working), but
    won't try to contact the DKPS server.

    Args:
      serialized_drm_keys: serialized DRM keys in a string.
    """
    self.gpg.encrypt(
        serialized_drm_keys, self.server_key_fingerprint, always_trust=True,
        sign=self.requester_key_fingerprint, passphrase=self.passphrase)


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
  parser.add_argument('--uploader_key_file_path', required=True,
                      help="path to the uploader's private key")
  parser.add_argument('--passphrase_file_path', default=None,
                      help="path to the passphrase file of the uploader's "
                           'private key')
  subparsers = parser.add_subparsers(dest='command')

  subparsers.add_parser(
      'available', help='display the available key count that remains')

  parser_upload = subparsers.add_parser('upload', help='upload DRM keys')
  parser_upload.add_argument('drm_keys_file_path',
                             help='path to the DRM keys file')

  return parser.parse_args()


def main():
  args = _ParseArguments()

  try:
    temp_dir = tempfile.mkdtemp()
    gnupg_homedir = os.path.join(temp_dir, 'gnupg')
    gpg = gnupg.GPG(gnupghome=gnupg_homedir)

    with open(args.server_key_file_path) as f:
      server_key_fingerprint = gpg.import_keys(f.read()).fingerprints[0]
    with open(args.uploader_key_file_path) as f:
      uploader_key_fingerprint = gpg.import_keys(f.read()).fingerprints[0]

    if args.passphrase_file_path is None:
      passphrase = None
    else:
      with open(args.passphrase_file_path) as f:
        passphrase = f.read()

    uploader_helper = UploaderHelper(
        args.server_ip, args.server_port, gpg, uploader_key_fingerprint,
        server_key_fingerprint, passphrase)
    if args.command == 'available':
      if args.mock:
        print 1
      else:
        print uploader_helper.AvailableKeyCount()
    elif args.command == 'upload':
      with open(args.drm_keys_file_path) as f:
        if args.mock:
          print uploader_helper.MockRequest(f.read())
        else:
          print uploader_helper.Upload(f.read())
    else:
      raise ValueError('Unkonw command %s' % args.command)
  finally:
    try:
      shutil.rmtree(temp_dir)
    except BaseException as e:
      logging.exception(e)


if __name__ == '__main__':
  main()
