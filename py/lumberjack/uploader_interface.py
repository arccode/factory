#!/usr/bin/python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Interfaces for FetchSource and UploadTarget."""

class CommonFunction(object):
  """Basics function that both FetchSource and UploadTarget should have."""
  def LoadConfiguration(self, config, config_name=None):
    """Loads a configuration from a dictionary.

    The config can be either passed during object instantiation or
    re-configure on the fly.

    Args:
      config: A dictionary parsed from YAML configuration.
      config_name: An additional annotation about this config.

    Raises:
      UploaderFieldError if any field is abnormal.
    """
    raise NotImplementedError('Need the implementation in sub-class')

  def CalculateDigest(self, relative_path):
    """Returns digest of path.

    The digest type can be one of md5, sha1, sha224, sha256, sha512. Based on
    the best availability on the protocol.

    Args:
      relative_path:
        The relative path starts from self.archive_path we want to calculate
        the digest.

    Returns:
      A tuple in format (digest type, digest in hex). If the file doesn't
      exist, None for both fields.
    """
    raise NotImplementedError('Need the implementation in sub-class')

  def MoveFile(self, from_path, to_path):
    """Moves a file.

    Usually called by recycling step after confirming an upload is success.

    Args:
      from_path:
          The path to the file we want to move from, relative to
          self.archive_path.
      to_path: Absolute path of file we want to move to.
          The path to the file we want to move to, relative to
          self.archive_path.

    Raises:
      IOError if failed.
    """
    raise NotImplementedError('Need the implementation in sub-class')

  def CheckDirectory(self, dir_path):
    """Checks if the directory exists.

    This serves for preventing us from misconfiguration in configuration.

    Args:
      dir_path: Absoulte path of the direcotry.

    Returns:
      True if directory exists, False otherwise.
    """
    raise NotImplementedError('Need the implementation in sub-class')

  def CreateDirectory(self, dir_path):
    """Creates the directory.

    Based on the need, the user might want to create the recycle directory
    automatically.

    Args:
      dir_path: Absolute oath of the direcotry.
    """
    raise NotImplementedError('Need the implementation in sub-class')


class FetchSourceInterface(CommonFunction):
  def ListFiles(self):
    """Returns a list of files exist in the source recursively.

    Returns:
      A list containing tuples of (relative path from monitored
      directory, file size, last modification timestamp - mtime)
    """
    raise NotImplementedError('Need the implementation in sub-class')

  def FetchFile(self, source_path, target_path,
                metadata_path=None, resume=True):
    """Fetches a file on remote's source_path into local target_path.

    This is a blocking function and progress will be updated in the
    metadata_path accordingly.

    Args:
      source_path:
        The path to the file we want to fetch on source side relative to
        self.archive_path.
      target_path:
        The path we want to save locally.
      metadata_path:
        The metadata path that information will be updated to. If None is
        given, the path will be automatically inferred.
      resume:
        Whether to resume the transmission if possible.

    Returns:
      True if fetching completed. False otherwise.
    """
    raise NotImplementedError('Need the implementation in sub-class')


class UploadTargetInterface(CommonFunction):
  def UploadFile(self, local_path, target_path,
                 metadata_path=None, resume=True):
    """Uploads a file to target.

    This is a blocking function and progress will be updated in the
    metadata_path accordingly.

    Args:
      local_path:
        The absolute path of the local file we want to upload.
      target_path:
        The path we want to save on target. It is relative to
        self.archive_path.
      metadata_path:
        The metadata path that information will be updated to. If None is
        given, the path will be automatically inferred.
      resume:
        Whether to resume the transmission if possible.

    Returns:
      True if uploading completed. False otherwise.
    """
    raise NotImplementedError('Need the implementation in sub-class')
