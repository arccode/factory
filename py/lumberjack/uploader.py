#!/usr/bin/python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A reference demos uploading archives to Google."""

import argparse
import logging
import sys

from common import IsValidYAMLFile


class FetchSourceInterface(object):
  def LoadConfiguration(self, config):
    """Loads a configuration from a dictionary.

    The config can be either passed during object instantiation or
    re-configure on the fly.

    Args:
      config: A dictionary parsed from YAML configuration.
    """
    raise NotImplementedError('Need the implementation in sub-class')

  def ListFiles(self, file_pool):
    """Returns a list of files exist in the source recursively.

    Args:
      file_pool:
        A local path that we anticipate to store those files, usually
        provided by the uploader's main logic (the path should be
        assigned in uploader's configuration and created before
        calling this funtion).
        If assigned, this function will update the metadata of listed
        files as well.

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
        The path on the file we want to fetch on source side.
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

  def CalculateDigest(self, source_path):
    """Returns digest of source_path.

    The digest type can be one of md5, sha1, sha224, sha256, sha512. Based on
    the best availability on the support of source side.

    Args:
      source_path: The file we want to calculate the digest.

    Returns:
      A tuple in format (digest type, digest in hex). If the file doesn't
      exist, None for both fields.
    """
    raise NotImplementedError('Need the implementation in sub-class')

  def MoveFile(self, from_path, to_path):
    """Moves a file on the source side.

    Usually called by recycling step after confirming an upload is success.

    Args:
      from_path: Path on the source side.
      to_path: Path on the source side.

    Raises:
      IOError if failed.
    """
    raise NotImplementedError('Need the implementation in sub-class')

  def CheckDirectory(self, dir_path):
    """Checks if the directory exists in source side.

    This serves for preventing us from misconfiguration in configuration.

    Args:
      dir_path: Direcotry path on the source side.

    Returns:
      Whether that directory exists.
    """
    raise NotImplementedError('Need the implementation in sub-class')

  def CreateDirectory(self, dir_path):
    """Creates the directory on the source side.

    Based on the need, the user might want to create the recycle directory
    automatically.

    Args:
      dir_path: Direcotry path on the source side.
    """
    raise NotImplementedError('Need the implementation in sub-class')


class UploadTargetInterface(object):
  def LoadConfiguration(self, config):
    """Loads a configuration from a dictionary.

    The config can be either passed during object instantiation or
    re-configure on the fly.

    Args:
      config: A dictionary parsed from YAML configuration.
    """
    raise NotImplementedError('Need the implementation in sub-class')

  def UploadFile(self, local_path, target_path,
                 metadata_path=None, resume=True):
    """Uploads a file to Google's storage.

    This is a blocking function and progress will be updated in the
    metadata_path accordingly.

    Args:
      local_path:
        The path of the local file we want to upload.
      target_path:
        The path we want to save on the Google side.
      metadata_path:
        The metadata path that information will be updated to. If None is
        given, the path will be automatically inferred.
      resume:
        Whether to resume the transmission if possible.

    Returns:
      True if uploading completed. False otherwise.
    """
    raise NotImplementedError('Need the implementation in sub-class')

  def CalculateDigest(self, target_path):
    """Returns digest of target_path.

    The digest type can be one of md5, sha1, sha224, sha256, sha512. Based on
    the best availability on the support of target side.

    Args:
      target_path: The file we want to calculate the digest.

    Returns:
      A tuple in format (digest type, digest in hex). If the file doesn't
      exist, None for both fields.

    """
    raise NotImplementedError('Need the implementation in sub-class')


def main(argv):
  top_parser = argparse.ArgumentParser(description='Uploader')
  sub_parsers = top_parser.add_subparsers(
      dest='sub_command', help='available sub-actions')

  parser_start = sub_parsers.add_parser('start', help='start the uploader')
  parser_status = sub_parsers.add_parser(   # pylint: disable=W0612
      'status', help='Show all the activities')
  parser_clean = sub_parsers.add_parser(  # pylint: disable=W0612
      'clean', help='Clear completed history')
  # TODO(itspeter):
  #  Add arguments for status and clean which are running without
  #  an YAML configuration file.

  parser_start.add_argument(
      'yaml_config', action='store', type=IsValidYAMLFile,
      help='start uploader with the YAML configuration file')
  args = top_parser.parse_args(argv)

  # Check fields.
  if args.sub_command == 'start':
    # TODO(itspeter): Implement the logic as design in docs.
    pass
  elif args.sub_command == 'status':
    # TODO(itspeter): Implement the logic as design in docs.
    pass
  elif args.sub_command == 'clean':
    # TODO(itspeter): Implement the logic as design in docs.
    pass


if __name__ == '__main__':
  # TODO(itspeter): Consider expose the logging level as an argument.
  logging.basicConfig(
      format=('[%(levelname)s] %(filename)s:'
              '%(lineno)d %(asctime)s %(message)s'),
      level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')
  main(sys.argv[1:])
