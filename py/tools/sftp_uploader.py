#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Utility script for uploading files via SFTP.

Example Usage:
  ./sftp_uploader.py somefile.zip
  ./sftp_uploader.py -h localhost -p 22 -i private.key -u sftp-user somefile.zip

Run "./sftp_uploader.py -h" for a complete list of options.

Supports use of a private key for authentication to the remote server. The
private key must not require a password.

Requires the python-paramiko library be installed.
"""

import errno
import logging
import optparse
import os
import sys

try:
  import paramiko # pylint: disable=F0401
except ImportError:
  print ('Paramiko SSH2 library not found. Try something like: '
         'sudo apt-get install python-paramiko')
  sys.exit(1)

SFTP_SERVER = 'localhost'
SFTP_PORT = 22
SFTP_USER = 'sftp-user'
SFTP_IDENTITY_KEY = 'sftp-test-key'
REMOTE_DIR = ''


def ProgressCallback(bytes_transferred, bytes_total):
  """Periodically called by sftp.put() to display progress.

  Args:
    bytes_transferred: Int. Number of bytes already transferred.
    bytes_total: Int. Total number of bytes to copy.

  Returns:
    None
  """
  sys.stdout.write('%0.2f%% of %d bytes' %
                   (100 * (bytes_transferred / float(bytes_total)),
                    bytes_total))
  sys.stdout.write('\r')
  sys.stdout.flush()


def main():
  """Main entry point into script."""

  def AlreadyUploaded(local_file):
    """Checks that a file of the same name and size is on the server.

    Args:
      local_file: String. Path to the local file.

    Returns:
      True if there is a matching file on the server.
    """
    filename = os.path.basename(local_file)
    remote_file = os.path.join(options.remote_dir, filename)
    local_file_attr = os.stat(local_file)
    try:
      remote_file_attr = sftp.stat(remote_file)
    except IOError as e:
      if e.errno not in [errno.ENOENT, errno.EACCES]:
        raise
      remote_file_attr = None
    return (remote_file_attr is not None and
        local_file_attr.st_size == remote_file_attr.st_size)

  USAGE = 'usage: %prog [options] [file]...'
  parser = optparse.OptionParser(USAGE)
  parser.add_option('-d', '--delete_local', dest='delete_local',
                    default=False, action='store_true',
                    help='Delete local files after upload.')
  parser.add_option('-i', '--identity', dest='identity_key',
                    default=SFTP_IDENTITY_KEY,
                    help='Private key to authenticate to the server.')
  parser.add_option('-p', '--port', dest='port', default=SFTP_PORT,
                    help='Port on SFTP server to connect with.')
  parser.add_option('-r', '--remote_dir', dest='remote_dir', default=REMOTE_DIR,
                    help='Directory on the server to copy files to.')
  parser.add_option('-s', '--server', dest='server', default=SFTP_SERVER,
                    help='Hostname of SFTP server to connect to.')
  parser.add_option('-u', '--user', dest='user', default=SFTP_USER,
                    help='User name to connect to SFTP server with.')
  parser.add_option('-v', '--verbose', dest='verbose',
                    default=False, action='store_true',
                    help='Increase level of logging detail.')
  parser.set_usage(parser.format_help())
  (options, args) = parser.parse_args()

  log_level = logging.DEBUG if options.verbose else logging.INFO
  log_format = '%(asctime)s %(levelname)s: %(message)s'
  logging.basicConfig(level=log_level, format=log_format)

  transport = paramiko.Transport((options.server, options.port))
  key = paramiko.RSAKey.from_private_key_file(options.identity_key)
  transport.connect(username=options.user, pkey=key)
  sftp = paramiko.SFTPClient.from_transport(transport)

  for local_file in args:
    if not os.path.isfile(local_file):
      logging.warning('%s is not a file. Skipping.', local_file)
      continue
    filename = os.path.basename(local_file)
    if AlreadyUploaded(local_file):
      logging.info('%s: Remote server has matching file of the same '
                   'name and size. Skipping upload.', filename)
    else:
      logging.info('Uploading: %s', local_file)
      remote_file = os.path.join(options.remote_dir, filename)
      callback = ProgressCallback if sys.stdout.isatty() else None
      try:
        sftp.put(local_file, remote_file, callback=callback)
      except IOError:
        logging.exception('Error uploading file to server as %s', remote_file)
        continue
    if options.delete_local and AlreadyUploaded(local_file):
      try:
        os.remove(local_file)
        logging.info('Deleted local file: %s', local_file)
      except OSError:
        logging.exception('Unable to delete local file: %s', local_file)
        continue

  sftp.close()
  transport.close()

if __name__ == '__main__':
  main()
