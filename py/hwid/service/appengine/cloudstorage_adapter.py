# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Facade for interfacing with various storage mechanisms."""

import contextlib
import logging
import os.path

# pylint: disable=no-name-in-module, import-error
import google.cloud.exceptions
from google.cloud import storage
# pylint: enable=no-name-in-module, import-error

from cros.factory.hwid.v3 import filesystem_adapter
from cros.factory.utils import type_utils


class CloudStorageAdapter(filesystem_adapter.FileSystemAdapter):
  """Adapter for Google Cloud Storage."""

  class ExceptionMapper(contextlib.AbstractContextManager):

    def __exit__(self, value_type, value, traceback):
      if isinstance(value, google.cloud.exceptions.NotFound):
        raise KeyError(value)
      if isinstance(value, google.cloud.exceptions.GoogleCloudError):
        raise filesystem_adapter.FileSystemAdapterException(str(value))

  CHUNK_SIZE = 2 ** 20

  EXCEPTION_MAPPER = ExceptionMapper()

  @classmethod
  def GetExceptionMapper(cls):
    return cls.EXCEPTION_MAPPER

  def __init__(self, bucket, chunk_size=None):
    self._bucket_name = bucket
    self._chunk_size = chunk_size or self.CHUNK_SIZE

  @type_utils.LazyProperty
  def _storage_client(self):
    return storage.Client()

  @type_utils.LazyProperty
  def _storage_bucket(self):
    return self._storage_client.bucket(self._bucket_name)

  def _ReadFile(self, path):
    """Read a file from the backing storage system."""
    blob = self._storage_bucket.blob(path)
    return blob.download_as_string()

  def _WriteFile(self, path, content):
    """Create a file in the backing storage system."""
    blob = self._storage_bucket.blob(path)
    logging.debug('Writing file: %s', blob.path)
    blob.upload_from_string(content)

  def _DeleteFile(self, path):
    """Create a file in the backing storage system."""
    blob = self._storage_bucket.blob(path)
    logging.debug('Deleting file: %s', blob.path)
    blob.delete()

  def _ListFiles(self, prefix=None):
    """List files in the backing storage system."""

    if prefix is None:
      prefix = ''

    if prefix and not prefix.endswith('/'):
      prefix += '/'

    ret = []
    for blob in self._storage_client.list_blobs(
        self._bucket_name, prefix=prefix, delimiter='/'):
      ret.append(os.path.relpath(blob.name, prefix))
    return ret
