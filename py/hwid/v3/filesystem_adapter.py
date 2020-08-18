# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Facade for interfacing with various storage mechanisms."""

import abc
import contextlib
import os
import os.path

from cros.factory.utils import file_utils


class FileSystemAdapterException(Exception):
  pass


class FileSystemAdapter(metaclass=abc.ABCMeta):
  """Abstract class for file access adapters.

  It supports simple, generic operations on files and is meant to provide a
  unified interface to either local or cloud files and provide any necessary
  caching.
  """

  @classmethod
  @abc.abstractmethod
  def GetExceptionMapper(cls):
    # GetExceptionmapper is used to map different type of exceptions in derived
    # classes to FileSystemAdapterException for better abstraction needs.  This
    # method should return an instance of class which implements __enter__ and
    # __exit__ context methods.
    raise NotImplementedError('Abstract method not implemented.')

  def ReadFile(self, path):
    with self.GetExceptionMapper():
      return self._ReadFile(path)

  @abc.abstractmethod
  def _ReadFile(self, path):
    raise NotImplementedError('Abstract method not implemented.')

  def WriteFile(self, path, content):
    with self.GetExceptionMapper():
      return self._WriteFile(path, content)

  @abc.abstractmethod
  def _WriteFile(self, path, content):
    raise NotImplementedError('Abstract method not implemented.')

  def DeleteFile(self, path):
    with self.GetExceptionMapper():
      return self._DeleteFile(path)

  @abc.abstractmethod
  def _DeleteFile(self, path):
    raise NotImplementedError('Abstract method not implemented.')

  def ListFiles(self, prefix=None):
    with self.GetExceptionMapper():
      return self._ListFiles(prefix=prefix)

  @abc.abstractmethod
  def _ListFiles(self, prefix=None):
    raise NotImplementedError('Abstract method not implemented.')


class LocalFileSystemAdapter(FileSystemAdapter):

  class ExceptionMapper(contextlib.AbstractContextManager):
    def __exit__(self, value_type, value, traceback):
      if isinstance(value, (OSError, IOError)):
        raise FileSystemAdapterException(str(value))

  EXCEPTION_MAPPER = ExceptionMapper()

  @classmethod
  def GetExceptionMapper(cls):
    return cls.EXCEPTION_MAPPER

  def __init__(self, base):
    super(LocalFileSystemAdapter, self).__init__()
    self._base = base

  def _ReadFile(self, path):
    return file_utils.ReadFile(os.path.join(self._base, path))

  def _WriteFile(self, path, content):
    filepath = os.path.join(self._base, path)
    file_utils.WriteFile(filepath, content)

  def _DeleteFile(self, path):
    filepath = os.path.join(self._base, path)
    file_utils.TryUnlink(filepath)

  def _ListFiles(self, prefix=None):
    """Currently _ListFiles implementation only supports directory as prefix."""

    dirpath = self._base
    if prefix:
      dirpath = os.path.join(dirpath, prefix)
    if not os.path.isdir(dirpath):
      raise OSError("%s is not a folder" % dirpath)
    return os.listdir(dirpath)
