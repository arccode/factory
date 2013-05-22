#!/usr/bin/python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
Reports fetcher is a command line tool to fetch reports from remote server
and upload it to Google Cloud Storage Server.

To run this tool, environment have to be setup as instructed in this URL:
https://developers.google.com/storage/docs/gspythonlibrary
"""

import logging
import optparse
import os
import subprocess

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


def UploadFile(source, target):
  """Wrapper to upload file via gsutil."""
  # We utilize the gsutil because it will resume the upload automatically.
  gsutil_cmd_args = ['gsutil', 'cp', source, target]
  subprocess.check_call(gsutil_cmd_args)


def Main():
  # TODO(itspeter): support fetching from remote server
  parser = optparse.OptionParser()
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
  # TODO(itspeter): support listing from a remote server
  for file_name, file_size in ListLocalFile(options.dir_to_monitor):
    # Check if file is already on the cloud.
    if GetObjectSize(
        options.bucket_name,
        os.path.join(options.obj_prefix, file_name)) == file_size:
      logging.info('Skipping %s', file_name)
      continue
    local_full_path = os.path.join(options.dir_to_monitor, file_name)
    UploadFile(local_full_path, '%s://%s' % (
        GOOGLE_STORAGE,
        os.path.join(options.bucket_name, options.obj_prefix)))


if __name__ == '__main__':
  LOG_FORMAT = '%(asctime)s %(levelname)s: %(message)s'
  logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
  Main()
