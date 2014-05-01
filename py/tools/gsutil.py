# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A tool for gsutil."""

import logging
import os
import re
import shutil

from distutils import version

import factory_common   # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.tools import build_board
from cros.factory.utils import process_utils


class GSUtilError(Exception):
  """GSUtil error."""
  pass


class GSUtil(object):
  """A class that wraps gsutil."""
  DEFAULT_GSUTIL_CACHE_DIR = os.path.join(os.environ['HOME'], 'gsutil_cache')
  CHANNELS = utils.Enum(['beta', 'canary', 'dev', 'stable'])
  IMAGE_TYPES = utils.Enum(['factory', 'firmware', 'recovery', 'test'])

  def __init__(self, board):
    self.board = build_board.BuildBoard(board)
    self.gs_output_cache = {}

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
      self.gs_output_cache[gs_url_pattern] = process_utils.CheckOutput(
          ['gsutil', 'ls', gs_url_pattern]).splitlines()
    gs_path_list = self.gs_output_cache[gs_url_pattern]

    if branch:
      gs_url_pattern += branch

    def GetVersion(gs_path):
      version_str = gs_path.rstrip('/').rpartition('/')[2]
      try:
        return version.StrictVersion(version_str)
      except ValueError:
        logging.warn('Bogus version string: %s', version_str)
        # Try to handle version number like 3674.0.2013_02_07_1033.
        version_str = version_str.replace('_', '')
        return version.StrictVersion(version_str)

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

    gs_builds_output = process_utils.CheckOutput(
        ['gsutil', 'ls', gs_dir]).splitlines()
    logging.debug('Output of `gsutil ls %s`\n: %s', gs_dir, gs_builds_output)

    logging.debug('Looking for filespec %s', filespec_re.pattern)
    result = [path for path in gs_builds_output if filespec_re.search(path)]

    if not result:
      raise GSUtilError('Unable to get binary URI for %r from %r' % (
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
    class ParsedObj(object):
      """An object to hold the parsed results."""
      def __init__(self, channel, board, image_version, image_type, key=None):
        self.channel = channel
        self.board = build_board.BuildBoard(board).full_name
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

  @staticmethod
  def GSDownload(uri, cache_dir=DEFAULT_GSUTIL_CACHE_DIR):
    """Downloads a file from Google storage, returning the path to the file.

    Downloads are cached in cache_dir.

    Args:
      uri: URI to download.
      cache_dir: Path to the cache directory.  Defaults to
        DEFAULT_GSUTIL_CACHE_DIR.

    Returns:
      Path to the downloaded file.  The returned path may have an arbitrary
      filename.
    """
    utils.TryMakeDirs(os.path.dirname(cache_dir))

    cached_path = os.path.join(cache_dir, uri.replace('/', '!'))
    if os.path.exists(cached_path):
      logging.info('Using cached %s (%.1f MiB)',
                   uri, os.path.getsize(cached_path) / (1024.*1024.))
      return cached_path

    in_progress_path = cached_path + '.INPROGRESS'
    process_utils.Spawn(
        ['gsutil', '-m', 'cp', uri, 'file://' + in_progress_path],
        check_call=True, log=True)
    shutil.move(in_progress_path, cached_path)
    return cached_path
