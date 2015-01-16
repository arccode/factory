#!/usr/bin/python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Reports fetcher is a command line tool to fetch reports from remote server and upload it to Google Cloud Storage Server.

To run this tool, environment have to be setup as instructed in this URL:
https://developers.google.com/storage/docs/gspythonlibrary
"""

import logging
import optparse
import os
import shutil
import signal
import subprocess
import tempfile
import yaml

import boto

from boto.exception import InvalidUriError
# The oauth2_plugin is needed for operation. Please refer to gsutil.py
# for more detail.
from oauth2_plugin import oauth2_plugin  # pylint: disable=W0611, F0401

GOOGLE_STORAGE = 'gs'  # Prefix of Google Cloud Storage


def GetObjectSize(bucket, path):
  """Returns the size of an object in Google Cloud Storage under a bucket.

  Args:
    bucket: the bucket name
    path: path to the object

  Returns:
    Returns the size or None if object doesn't exist.
  """
  try:
    object_uri = boto.storage_uri(bucket + '/' + path, GOOGLE_STORAGE)
    key = object_uri.get_key()
    logging.info('Fetching metadata of %s', object_uri)
  except InvalidUriError:
    logging.info("%s doesn't exist", object_uri)
    return None
  return key.size


def ListLocalFile(dir_path):
  """Generates tuples of file name and file size."""
  for file_path in os.listdir(dir_path):
    full_path = os.path.join(dir_path, file_path)
    if not os.path.isfile(full_path):
      continue
    yield (file_path, os.path.getsize(full_path))


def ListRemoteFile(dir_path, ssh_portal):
  """Returns tuples of file name and file size from remote host."""
  def SshExecute(command):
    """Wrapper for executing command after ssh."""
    return subprocess.check_output(['ssh', ssh_portal] + command)

  # TODO(itspeter): Refactor the whole flow to a RPC call, so file listing
  # doesn't need separate interface.

  # Install the script that returns result in yaml string
  SCRIPT_NAME = 'list_dir_as_yaml.py'
  script_source = os.path.join(
      os.path.dirname(os.path.realpath(__file__)), SCRIPT_NAME)
  remote_path = os.path.join('/tmp', SCRIPT_NAME)
  subprocess.check_call(
      ['scp', script_source, '%s:%s' % (ssh_portal, remote_path)])
  yaml_str = SshExecute([remote_path, dir_path])
  # Remove the script
  SshExecute(['rm', remote_path])
  return yaml.safe_load(yaml_str).iteritems()


def UploadFile(source, target):
  """Wrapper to upload file via gsutil."""
  # We utilize the gsutil because it will resume the upload automatically.
  gsutil_cmd_args = ['gsutil', 'cp', source, target]
  subprocess.check_call(gsutil_cmd_args)


def CleanUp(directory):
  logging.info('Clean up temporary directory %s', directory)
  shutil.rmtree(directory, ignore_errors=True)


def Main():
  # TODO(itspeter): support fetching from remote server
  parser = optparse.OptionParser()
  parser.add_option('--ssh_portal', dest='ssh_portal', type='string',
                    help=('the login portal to remote host,'
                          ' ex: guest@192.168.7.7'))
  parser.add_option('--directory', dest='dir_to_monitor', type='string',
                    metavar='PATH', help='path of monitoring directory')
  parser.add_option('--bucket_name', dest='bucket_name', type='string',
                    help='the unique bucket name of Google Cloud Storage')
  parser.add_option('--obj_prefix', dest='obj_prefix', type='string',
                    help=('additional prefix for objects, this usually acts'
                          ' as a subdirectory name'))

  (options, args) = parser.parse_args()
  if args:
    parser.error('Invalid args: %s' % ' '.join(args))

  # Listing source
  source_on_remote = False
  if options.ssh_portal:
    source_on_remote = True
    # Check connection by not raising error for echo call
    subprocess.check_call(['ssh', options.ssh_portal, 'echo'])

  if source_on_remote:
    local_dir = tempfile.mkdtemp()
    logging.info('Temporary directory created %s', local_dir)
    source_files = ListRemoteFile(
        options.dir_to_monitor, options.ssh_portal)
    signal_handler = lambda _, __: CleanUp(local_dir)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
  else:
    source_files = ListLocalFile(options.dir_to_monitor)
    local_dir = options.dir_to_monitor

  for file_name, file_size in source_files:
    # Check if file is already on the cloud.
    if GetObjectSize(
        options.bucket_name,
        os.path.join(options.obj_prefix, file_name)) == file_size:
      logging.info('Skipping %s', file_name)
      continue

    if source_on_remote:
      # Copy files into local temp directory
      subprocess.check_call(
          ['rsync', '--progress', '-e', 'ssh',
           '%s:%s' % (options.ssh_portal, os.path.join(
               options.dir_to_monitor, file_name)),
           local_dir])

    local_full_path = os.path.join(local_dir, file_name)
    UploadFile(local_full_path, '%s://%s' % (
        GOOGLE_STORAGE,
        os.path.join(options.bucket_name, options.obj_prefix)))

    if source_on_remote:
      os.unlink(local_full_path)

  if source_on_remote:
    CleanUp(local_dir)


if __name__ == '__main__':
  LOG_FORMAT = '%(asctime)s %(levelname)s: %(message)s'
  logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
  Main()
