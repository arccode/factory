# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Google Cloud Storage utilities."""

import logging
import os

from . import file_utils

try:
  # pylint: disable=import-error, no-name-in-module
  from google.cloud import storage
  from google.oauth2 import service_account
except ImportError as e:
  # These lines can be used in a requirements.txt file:
  #
  #   google-cloud-storage==1.31.0
  #   google-auth==1.21.1
  #
  # Then, to install them:
  #
  #  pip install -t external_dir -r requirements.txt
  new_exc = ImportError(
      'Please install these Python libraries before proceeding: '
      'google-cloud-storage==1.31.0 google-auth==1.21.1')
  raise new_exc from e


_GCS_SCOPE = 'https://www.googleapis.com/auth/devstorage.read_write'
_CHUNK_SIZE_MULTIPLE = 256 * 1024  # chunk_size must be a multiple of 256KB
_CHUNK_SIZE = 4 * 1024 * 1024  # 4MB


class CloudStorage:
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

  def _HandleTargetPath(self, target_path):
    """Split target_path to the storage bucket ID and the path in the bucket.

    Args:
      target_path: Target path with bucket ID in GCS.
                   (e.g. '/chromeos-factory/path/to/filename')

    Returns:
      bucket_id: The storage bucket ID.
      path_in_bucket: The path of the target object in the bucket.
    """
    target_path = target_path.strip('/')
    bucket_id, unused_slash, path_in_bucket = target_path.partition('/')
    return bucket_id, path_in_bucket

  def UploadFile(self, local_path, target_path, overwrite=False):
    """Attempts to upload a file to GCS.

    Args:
      local_path: Path to the file on local disk.
      target_path: Target path with bucket ID in GCS.
                   (e.g. '/chromeos-factory/path/to/filename')
      overwrite: Whether or not to overwrite the file on target_path.

    Returns:
      True if file is uploaded successfully.
    """
    try:
      bucket_id, path_in_bucket = self._HandleTargetPath(target_path)
      bucket = storage.Bucket(self.client, bucket_id)

      self.logger.info(
          'Going to upload the file from local (%s) to GCS ([/%s]/%s)',
          local_path, bucket_id, path_in_bucket)
      local_md5 = file_utils.MD5InBase64(local_path)
      local_size = os.path.getsize(local_path)

      blob = storage.Blob(path_in_bucket, bucket, chunk_size=self.chunk_size)
      if blob.exists():
        blob.reload()
        if blob.md5_hash == local_md5 and blob.size == local_size:
          self.logger.warning(
              'File already exists on remote end with same size (%d) and same '
              'MD5 hash (%s); skipping', blob.size, blob.md5_hash)
          return True
        self.logger.error(
            'File already exists on remote end, but size or MD5 hash doesn\'t '
            'match; remote file (%d, %s) != local file (%d, %s); overwrite=%s',
            blob.size, blob.md5_hash, local_size, local_md5, overwrite)
        if not overwrite:
          return False

      # Upload requests will be automatically retried if a transient error
      # occurs. Therefore, we don't need to retry it ourselves.
      blob.upload_from_filename(local_path)

      blob.reload()
      if not blob.exists():
        self.logger.error(
            'This should not happen! File doesn\'t exist after uploading')
        return False
      if blob.md5_hash != local_md5 or blob.size != local_size:
        self.logger.error(
            'This should not happen! Size or MD5 mismatch after uploading; '
            'local_size = %d, confirmed_size = %d; local_md5 = %s, '
            'confirmed_md5 = %s', local_size, blob.size, local_md5,
            blob.md5_hash)
        return False
      return True
    except Exception:
      self.logger.exception('Upload failed')
      return False

  def DownloadFile(self, target_path, local_path, overwrite=False):
    """Attempts to download a file from GCS.

    Args:
      target_path: Target path with bucket ID in GCS.
                   (e.g. '/chromeos-factory/path/to/filename')
      local_path: Path to the file on local disk.
      overwrite: Whether or not to overwrite the file on local_path.

    Returns:
      True if file is downloaded successfully.
    """
    try:
      bucket_id, path_in_bucket = self._HandleTargetPath(target_path)
      bucket = storage.Bucket(self.client, bucket_id)

      blob = storage.Blob(path_in_bucket, bucket)
      if not blob.exists():
        self.logger.error('File on GCS ([%s]/%s) doesn\'t exist!', bucket_id,
                          path_in_bucket)
        return False
      blob.reload()

      if os.path.exists(local_path):
        local_md5 = file_utils.MD5InBase64(local_path)
        local_size = os.path.getsize(local_path)
        if blob.md5_hash == local_md5 and blob.size == local_size:
          self.logger.warning(
              'File already exists on local end with same size (%d) and same '
              'MD5 hash (%s); skipping', local_size, local_md5)
          return True
        self.logger.error(
            'File already exists on loca end, but size or MD5 hash doesn\'t '
            'match; remote file (%d, %s) != local file (%d, %s); '
            'overwrite=%s', blob.size, blob.md5_hash, local_size, local_md5,
            overwrite)
        if not overwrite:
          return False

      self.logger.info(
          'Going to download the file from GCS ([/%s]/%s) to local (%s)',
          bucket_id, path_in_bucket, local_path)
      blob.download_to_filename(local_path)

      return True
    except Exception:
      self.logger.exception('Download failed')
      return False
