# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import glob
import logging
import numbers
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test.test_lists import manager
from cros.factory.test.utils import pytest_utils
from cros.factory.utils import config_utils
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


_BASIC_ARG_TYPE = type_utils.Enum((
    'NONE', 'BOOL', 'INT', 'FLOAT', 'STR', 'LIST', 'DICT'
))


def _NormalizedArgType(t):
  if isinstance(t, type_utils.Enum):
    return sorted(t)
  if t is type(None):
    return _BASIC_ARG_TYPE.NONE
  if t is bool:
    return _BASIC_ARG_TYPE.BOOL
  if issubclass(t, numbers.Integral):
    return _BASIC_ARG_TYPE.INT
  if issubclass(t, numbers.Number):
    return _BASIC_ARG_TYPE.FLOAT
  if issubclass(t, basestring):
    return _BASIC_ARG_TYPE.STR
  if issubclass(t, collections.Sequence):
    return _BASIC_ARG_TYPE.LIST
  if issubclass(t, collections.Mapping):
    return _BASIC_ARG_TYPE.DICT
  raise ValueError('Unknown argument type %r.' % t)


class RPC(object):
  """The actual RPC request handler.

  Properties:
    dirs: List[Tuple[dirname: str, dirpath: str]].
      List of information of factory base folders.
      `dirname` is human-friendly folder name (e.g., 'factory', 'samus').
      `dirpath` is the absolute path, such as:
        '/.../src/platform/factory' and
        '/.../src/private-overlays/.../factory-board/files'.
  """

  def __init__(self, dirs):
    self.dirs = dirs

  @type_utils.LazyProperty
  def _test_list_schema(self):
    return file_utils.ReadFile(os.path.join(
        paths.FACTORY_DIR,
        manager.TEST_LISTS_RELPATH,
        manager.TEST_LIST_SCHEMA_NAME + config_utils.SCHEMA_FILE_EXT))

  def GetTestListSchema(self):
    """Returns the JSON schema of test list files (as a string)."""
    return self._test_list_schema

  def LoadFiles(self):
    """Load test list folders and files.

    Returns:
      {
        dirs: List[{name: str, path: str, filelist: List[basename: str]}],
        files: Dict[basename: str, content: str]
      }
    """
    dirs = []
    files = {}
    for dirname, dirpath in self.dirs:
      test_list_dir = os.path.join(dirpath, manager.TEST_LISTS_RELPATH)
      filelist = []
      filepaths = glob.glob(os.path.join(
          test_list_dir,
          '*' + manager.CONFIG_SUFFIX + config_utils.CONFIG_FILE_EXT))
      for filepath in filepaths:
        basename = os.path.basename(filepath)
        if basename in files:
          # Actually, files in private overlays will override the file with same
          # name in factory repository (if exists). We disallow this to make
          # things easier.
          raise RuntimeError('Multiple files with the same name %r' % basename)
        files[basename] = file_utils.ReadFile(filepath)
        filelist.append(basename)
      dirs.append(dict(name=dirname, path=test_list_dir, filelist=filelist))
    return dict(dirs=dirs, files=files)

  def SaveFiles(self, requests):
    """Write data into specified files.

    For safety purposes, both writing to anywhere other than test list folders
    and using different filename extension are prohibited.

    Args:
      requests: Dict[filepath: str, content: str].
    """

    def IsForbidden(path):
      if not path.endswith(
          manager.CONFIG_SUFFIX + config_utils.CONFIG_FILE_EXT):
        return True
      path_dir = os.path.dirname(path)
      for unused_dirname, dirpath in self.dirs:
        if path_dir == os.path.join(dirpath, manager.TEST_LISTS_RELPATH):
          return False
      return True

    for filepath, content in requests.iteritems():
      if IsForbidden(filepath):
        raise RuntimeError('Writing to %r is disallowed.' % filepath)
      file_utils.WriteFile(filepath, content)

  @type_utils.LazyProperty
  def _pytests(self):
    res = {}
    for unused_dirname, dirpath in self.dirs:
      for relpath in pytest_utils.GetPytestList(dirpath):
        pytest_name = pytest_utils.RelpathToPytestName(relpath)
        res[pytest_name] = os.path.join(
            dirpath, pytest_utils.PYTESTS_RELPATH, relpath)
    return res

  def ListPytests(self):
    """Returns a sorted list of pytest names."""
    return sorted(self._pytests.iterkeys())

  def GetPytestInfo(self, pytest_name):
    # TODO(youcheng): Provide HTML documents.
    res = {'src': file_utils.ReadFile(self._pytests[pytest_name])}
    try:
      # TODO(youcheng): Supports pytests from private overlays.
      # TODO(youcheng): Make LoadPytest work for all pytests outside DUT.
      pytest = pytest_utils.LoadPytest(pytest_name)
    except Exception:
      logging.warn('Failed to load pytest %r.', pytest_name)
      return res
    args = {}
    for arg in getattr(pytest, 'ARGS', []):
      typelist = []
      for t in arg.type:
        # TODO(youcheng): Support I18nArg.
        normalized_t = _NormalizedArgType(t)
        if normalized_t not in typelist:
          typelist.append(normalized_t)
      arg_info = {'type': typelist, 'help': arg.help}
      if arg.IsOptional():
        arg_info['default'] = arg.default
      args[arg.name] = arg_info
    res['args'] = args
    return res
