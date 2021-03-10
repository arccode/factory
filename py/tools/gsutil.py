# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A tool for gsutil."""

import argparse
from distutils import version as version_utils
import logging
import os
import re
import shutil

from cros.factory.utils import cros_board_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils


class GSUtilError(Exception):
  """GSUtil error."""


class NoSuchKey(GSUtilError):
  """Thrown when error message=NoSuchKey."""


class GSUtil:
  """A class that wraps gsutil."""
  CHANNELS = type_utils.Enum(['beta', 'canary', 'dev', 'stable'])
  IMAGE_TYPES = type_utils.Enum(['factory', 'firmware', 'recovery', 'test'])

  def __init__(self, board):
    self.board = cros_board_utils.BuildBoard(board)
    self.gs_output_cache = {}

  def _InvokeCommand(self, *args):
    process = process_utils.Spawn(['gsutil'] + list(args),
                                  read_stdout=True, read_stderr=True)
    if process.returncode == 0:
      return process.stdout_data

    stderr = process.stderr_data
    if ('CommandException: No URLs matched' in stderr or
        'NotFoundException:' in stderr or
        'One or more URLs matched no objects' in stderr):
      raise NoSuchKey(stderr)
    raise GSUtilError(stderr)

  def LS(self, pattern):
    return self._InvokeCommand('ls', pattern).strip().split('\n')

  def CP(self, src, dest):
    self._InvokeCommand('cp', src, dest)

  def GetVersion(self):
    output = self._InvokeCommand('version')
    return re.search(r'gsutil version: (\d+\.\d+)', output).group(1)

  def GetGSPrefix(self, channel):
    """Gets the common prefix of a Google storage URI for a given channel.

    Args:
      channel: The Google storage channel.  Must be one of:
        ['beta', 'canary', 'dev', 'stable'].

    Returns:
      The generated Google storage URI prefix.
    """
    if channel not in self.CHANNELS:
      raise GSUtilError('Invalid channel %r. Valid choices are: %r' % (
          channel, self.CHANNELS))
    return 'gs://chromeos-releases/%(channel)s-channel/%(board)s/' % dict(
        channel=channel, board=self.board.gsutil_name)

  def GetLatestBuildPath(self, channel, branch=None):
    """Gets the latest build version from Google storage.

    Args:
      channel: The channel to get build paths from.
      branch: If given, gets the latest version of the specific branch.

    Returns:
      The path to the latest build version on GS.
    """
    if branch:
      branch_re = r'\d+(.\d+){0,2}'
      if not re.match(branch_re, branch):
        raise GSUtilError('branch must be a string of format: %s' % branch_re)
    gs_url_pattern = self.GetGSPrefix(channel)
    if gs_url_pattern not in self.gs_output_cache:
      self.gs_output_cache[gs_url_pattern] = self.LS(gs_url_pattern)
    gs_path_list = self.gs_output_cache[gs_url_pattern]

    if branch:
      gs_url_pattern += branch

    def GetVersion(gs_path):
      version_str = gs_path.rstrip('/').rpartition('/')[2]
      try:
        return version_utils.StrictVersion(version_str)
      except ValueError:
        logging.warning('Bogus version string: %s', version_str)
        # Try to handle version number like 3674.0.2013_02_07_1033.
        version_str = version_str.replace('_', '')
        return version_utils.StrictVersion(version_str)

    return sorted([p for p in gs_path_list if p.startswith(gs_url_pattern)],
                  key=GetVersion)[-1]

  def GetBinaryURI(self, gs_dir, filetype, key=None):
    """Gets binary URI of a specific file type from a Google storage directory.

    Args:
      gs_dir: The base Google storage directory.
      filetype: The file type of the binary.  Must be one of:
        ['factory', 'firmware', 'recovery', 'test'].
      key: If given, tries to get the URI of signed binary instead.

    Returns:
      The Google storage URI of the specified binary object.
    """
    if filetype not in self.IMAGE_TYPES:
      raise GSUtilError('Invalid file type %r. Valid choices are: %r' % (
          filetype, self.IMAGE_TYPES))

    fileext = {
        self.IMAGE_TYPES.factory: 'zip',
        self.IMAGE_TYPES.firmware: 'tar.bz2',
        self.IMAGE_TYPES.recovery: 'tar.xz',
        self.IMAGE_TYPES.test: 'tar.xz',
    }

    if key:
      if filetype == self.IMAGE_TYPES.firmware:
        tag = self.board.short_name
      else:
        tag = r'\w*'
      filespec_re = re.compile(
          r'chromeos_\d+\.\d+\.\d+_'
          r'%(board)s_'
          r'%(filetype)s-?'
          r'%(tag)s_'
          r'\w+-channel_%(key)s.bin$' % dict(
              board=self.board.gsutil_name, filetype=filetype, tag=tag,
              key=key))
    else:
      filespec_re = re.compile(
          r'ChromeOS-%(filetype)s-'
          r'R\d+-\d+\.\d+\.\d+-'
          r'%(board)s.%(fileext)s$' % dict(
              filetype=filetype, board=self.board.gsutil_name,
              fileext=fileext[filetype]))

    gs_builds_output = self.LS(gs_dir)
    logging.debug('Output of `gsutil ls %s`\n: %s', gs_dir, gs_builds_output)

    logging.debug('Looking for filespec %s', filespec_re.pattern)
    result = [path for path in gs_builds_output if filespec_re.search(path)]

    if not result:
      raise NoSuchKey('Unable to get binary URI for %r from %r' % (
          filetype, gs_dir))

    if len(result) > 1:
      raise GSUtilError('Got more than one URI for %r from %r: %r' % (
          filetype, gs_dir, result))

    return result[0]

  @staticmethod
  def ParseURI(uri):
    """Parses a Google storage URI to extract various fields.

    This method parses out channel name, board name, image type and image
    version.

    Args:
      uri: The URI to parse.

    Returns:
      A ParsedObj instance with the following properties:
        channel: The channel of the URI.
        board: The board name.
        image_version: The image version
        image_type: The image type.
        key: The key that signed the image.
    """
    class ParsedObj:
      """An object to hold the parsed results."""

      def __init__(self, channel, board, image_version, image_type, key=None):
        self.channel = channel
        self.board = cros_board_utils.BuildBoard(board).full_name
        self.image_version = image_version
        self.image_type = image_type
        self.key = key

      def __repr__(self):
        return str(self.__dict__)

    UNSIGNED_IMAGE_RE = re.compile(
        r'^gs://chromeos-releases/(?P<channel>\w+)-channel/'
        r'(?P<board>[-\w]+)/'
        r'(?P<image_version>\d+\.\d+\.\d+)/'
        r'ChromeOS-(?P<image_type>\w+)-'
        r'R\d+-(?P=image_version)-'
        r'(?P=board)\.[.\w]+$')
    SIGNED_IMAGE_RE = re.compile(
        r'^gs://chromeos-releases/(?P<channel>\w+)-channel/'
        r'(?P<board>[-\w]+)/'
        r'(?P<image_version>\d+\.\d+\.\d+)/'
        r'chromeos_(?P=image_version)_'
        r'(?P=board)_'
        r'(?P<image_type>\w+)_'
        r'(?P=channel)-channel_'
        r'(?P<key>[-\w]+)\.[.\w]+$')

    for regexp in (UNSIGNED_IMAGE_RE, SIGNED_IMAGE_RE):
      match_obj = regexp.search(uri)
      if match_obj:
        return ParsedObj(*match_obj.groups())

    raise GSUtilError('Unable to parse URI: %r' % uri)

  def GSDownload(self, uri, cache_dir=None):
    """Downloads a file from Google storage, returning the path to the file.

    Downloads are cached in cache_dir.

    Args:
      uri: URI to download.
      cache_dir: Path to the cache directory.  Defaults to
        /usr/local/gsutil_cache on CROS DUT, or ${HOME}/gsutil_cache otherwise.

    Returns:
      Path to the downloaded file.  The returned path may have an arbitrary
      filename.
    """
    def GetDefaultGSUtilCacheDir():
      if sys_utils.InCrOSDevice():
        # On CROS DUT, set gsutil cache to stateful partition.
        base_cache_dir = '/usr/local'
      else:
        # Otherwise set it to user's home directory.
        base_cache_dir = os.environ.get('HOME')
      return os.path.join(base_cache_dir, 'gsutil_cache')

    if not cache_dir:
      cache_dir = GetDefaultGSUtilCacheDir()
    file_utils.TryMakeDirs(cache_dir)

    cached_path = os.path.join(cache_dir, uri.replace('/', '!'))
    if os.path.exists(cached_path):
      logging.info('Using cached %s (%.1f MiB)',
                   uri, os.path.getsize(cached_path) / (1024 * 1024))
      return cached_path

    in_progress_path = cached_path + '.INPROGRESS'
    self.CP(uri, 'file://' + in_progress_path)
    shutil.move(in_progress_path, cached_path)
    return cached_path


def BuildResourceBaseURL(channel, board, version):
  BASE_URL_FORMAT = 'gs://chromeos-releases/{channel}-channel/{board}/{version}'
  assert channel in GSUtil.CHANNELS
  assert isinstance(board, str)
  assert isinstance(version, str)

  return BASE_URL_FORMAT.format(channel=channel,
                                board=board,
                                version=version)


class _DownloadCommand:
  @classmethod
  def Register(cls, parser):
    subparser = parser.add_parser('download', description='Download an image.')
    subparser.set_defaults(subcommand=cls)
    subparser.add_argument('--board', type=str, required=True)
    subparser.add_argument('--channel', choices=GSUtil.CHANNELS,
                           default=GSUtil.CHANNELS.dev)
    subparser.add_argument('--version', type=str, help='e.g. "1234.56.78"')
    subparser.add_argument('--branch', type=str, help='e.g. "1234.56"')
    subparser.add_argument('--key', type=str, help='e.g. "premp", "mp-v2"')

    subparser.add_argument('--dest', type=str,
                           help='directory or file path of destination',
                           default='.')

    subparser.add_argument('--dry-run', action='store_true',
                           help='Print the URI to be downloaded and exit.')

    subparser.add_argument('type', choices=GSUtil.IMAGE_TYPES)

  @classmethod
  def Run(cls, args):
    gsutil = GSUtil(args.board)

    if args.version:
      base_url = BuildResourceBaseURL(args.channel, args.board, args.version)
    else:
      base_url = gsutil.GetLatestBuildPath(args.channel, args.branch)

    binary_uri = gsutil.GetBinaryURI(base_url, args.type, args.key)
    if args.dry_run:
      print(binary_uri)
      return

    gsutil.CP(binary_uri, args.dest)


def main():
  parser = argparse.ArgumentParser()
  subparsers = parser.add_subparsers(title='subcommands', dest='subcommand')
  subparsers.required = True
  _DownloadCommand.Register(subparsers)

  args = parser.parse_args()
  args.subcommand.Run(args)


if __name__ == '__main__':
  main()
