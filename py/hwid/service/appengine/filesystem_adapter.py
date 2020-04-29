# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Facade for interfacing with various storage mechanisms."""

import logging
import os

import cloudstorage  # pylint: disable=import-error


class FileSystemAdapterException(Exception):
  pass


class FileSystemAdapter(object):
  """Acts as a wrapper around the file storage system.

  It supports simple, generic operations on files and is meant to provide a
  unified interface to either local or cloud files and provide any necessary
  caching.
  """

  def ReadFile(self, path):
    with self.EXCEPTION_MAPPER:
      return self._ReadFile(path)

  def _ReadFile(self, path):
    raise NotImplementedError('Abstract method not implemented.')

  def WriteFile(self, path, content):
    with self.EXCEPTION_MAPPER:
      return self._WriteFile(path, content)

  def _WriteFile(self, path, content):
    raise NotImplementedError('Abstract method not implemented.')

  def DeleteFile(self, path):
    with self.EXCEPTION_MAPPER:
      return self._DeleteFile(path)

  def _DeleteFile(self, path):
    raise NotImplementedError('Abstract method not implemented.')

  def ListFiles(self, prefix=None):
    with self.EXCEPTION_MAPPER:
      return self._ListFiles(prefix=prefix)

  def _ListFiles(self, prefix=None):
    raise NotImplementedError('Abstract method not implemented.')


class CloudStorageAdapter(FileSystemAdapter):
  """Adapter for Google Cloud Storage."""

  class ExceptionMapper(object):

    def __enter__(self):
      pass

    def __exit__(self, value_type, value, traceback):
      if isinstance(value, cloudstorage.errors.NotFoundError):
        raise KeyError(value)
      if isinstance(value, cloudstorage.Error):
        raise FileSystemAdapterException(str(value))

  CHUNK_SIZE = 2 ** 20

  EXCEPTION_MAPPER = ExceptionMapper()

  def __init__(self, bucket, chunk_size=None):
    self._bucket = bucket
    self._chunk_size = chunk_size or CloudStorageAdapter.CHUNK_SIZE

  def _ReadFile(self, path):
    """Read a file from the backing storage system."""
    file_name = self._GsPath(path)

    with cloudstorage.open(file_name) as gcs_file:
      return gcs_file.read()

  def _WriteFile(self, path, content):
    """Create a file in the backing storage system."""
    file_name = self._GsPath(path)

    logging.debug('Writing file: %s', self._GsPath(path))

    with cloudstorage.open(file_name, 'w') as gcs_file:
      gcs_file.write(content)

  def _DeleteFile(self, path):
    """Create a file in the backing storage system."""
    logging.debug('Deleting file: %s', self._GsPath(path))

    cloudstorage.delete(self._GsPath(path))

  def _ListFiles(self, prefix=None):
    """List files in the backing storage system."""

    return cloudstorage.listbucket(self._GsPath(), prefix=prefix)

  def _GsPath(self, *pieces):
    return os.path.normpath('/'.join(['', self._bucket] + list(pieces)))
