# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Google Cloud Storage utilities."""

from __future__ import print_function

import logging
import os
import sys

from six import reraise as raise_

from . import file_utils

try:
  # pylint: disable=import-error, no-name-in-module
  from google.cloud import storage
  from google.oauth2 import service_account
except ImportError:
  # These lines can be used in a requirements.txt file:
  #
  #   google-cloud-storage==1.6.0
  #   google-auth==1.0.2
  #
  # Then, to install them:
  #
  #  pip install -t external_dir -r requirements.txt
  _unused_exc_class, _unused_exc, tb = sys.exc_info()
  new_exc = ImportError(
      'Please install these Python libraries before proceeding: '
      'google-cloud-storage==1.4.0 google-auth==1.0.2')
  raise_(new_exc.__class__, new_exc, tb)


_GCS_SCOPE = 'https://www.googleapis.com/auth/devstorage.read_write'
_CHUNK_SIZE_MULTIPLE = 256 * 1024  # chunk_size must be a multiple of 256KB
_CHUNK_SIZE = 4 * 1024 * 1024  # 4MB


class CloudStorage(object):
  """Wrapper to access Google Cloud Storage."""

  def __init__(self, json_key_path, logger=logging, chunk_size=_CHUNK_SIZE):
    """Authenticates the connection to Cloud Storage.

    Args:
      json_key_path: Path to the private key (in JSON format) on disk.
      logger: A logging.logger object to record messages.
      chunk_size: Files uploaded to GCS are sent in chunks. Must be a multiple
                  of _CHUNK_SIZE_MULTIPLE.
    """
    assert chunk_size % _CHUNK_SIZE_MULTIPLE == 0, (
        'chunk_size must be a multiple of %d B' % _CHUNK_SIZE_MULTIPLE)
    self.chunk_size = chunk_size

    self.logger = logger

    credentials = service_account.Credentials.from_service_account_file(
        json_key_path, scopes=(_GCS_SCOPE,))
    # Google Cloud Storage is depend on bucket instead of project, so we don't
    # need to put project name to arguments. However, this client is general
    # Google Cloud client, so the project can't be None; instead it can be an
    # empty string.
    self.client = storage.Client(project='', credentials=credentials)

  def UploadFile(self, local_path, target_path, overwrite=False):
    """Attempts to upload a file to GCS, with resumability.

    Args:
      local_path: Path to the file on local disk.
      target_path: Target path with bucket ID in GCS.
                   (e.g. '/chromeos-factory/path/to/filename')
      overwrite: Whether or not to overwrite the file on target_path.

    Raises:
      google.cloud.exceptions.GoogleCloudError: if the upload response returns
                                                an error status.
      ValueError: if the bucket doesn't exist.
      IOError: the uploaded file on GCS doesn't exist or has different
               md5_hash/size.
    """
    try:
      target_path = target_path.strip('/')
      bucket_id, _unused_slash, path_in_bucket = target_path.partition('/')
      bucket = storage.Bucket(self.client, bucket_id)
      if not bucket.exists():
        self.logger.error('Bucket (%s) doesn\'t exist! Please create it before '
                          'you upload file', bucket_id)
        return False

      self.logger.info('Going to upload the file from %s to GCS: [/%s]/%s',
                       local_path, bucket_id, path_in_bucket)
      local_md5 = file_utils.MD5InBase64(local_path)
      local_size = os.path.getsize(local_path)

      blob = storage.Blob(path_in_bucket, bucket, chunk_size=self.chunk_size)
      if blob.exists():
        blob.reload()
        if blob.md5_hash == local_md5 and blob.size == local_size:
          self.logger.warning('File already exists on remote end with same '
                              'size (%d) and same MD5 hash (%s); skipping',
                              blob.size, blob.md5_hash)
          return True
        else:
          self.logger.error('File already exists on remote end, but size or '
                            'MD5 hash doesn\'t match; size on remote = %d, '
                            'size on local = %d; will overwrite',
                            blob.size, local_size)
          if not overwrite:
            return False

      # Upload requests will be automatically retried if a transient error
      # occurs. Therefore, we don't need to retry it ourselves.
      blob.upload_from_filename(local_path)

      blob.reload()
      if not blob.exists():
        self.logger.error('This should not happen! '
                          'File doesn\'t exist after uploading')
        return False
      if blob.md5_hash != local_md5 or blob.size != local_size:
        self.logger.error('This should not happen! Size or MD5 mismatch after '
                          'uploading; local_size = %d, confirmed_size = %d; '
                          'local_md5 = %s, confirmed_md5 = %s',
                          local_size, blob.size, local_md5, blob.md5_hash)
        return False
      return True
    except Exception:
      self.logger.exception('Upload failed')
      return False
