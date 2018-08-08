# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.test.test_lists import manager
from cros.factory.test_list_editor.backend import common
from cros.factory.utils import config_utils
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


class RPC(object):
  """The actual RPC request handler.

  Properties:
    dirs: List[Tuple[dirname: str, dirpath: str]].
      List of information of test list folders.
      `dirname` is human-friendly folder name (e.g., 'factory', 'samus').
      `dirpath` is the absolute path.
  """

  def __init__(self, dirs):
    self.dirs = dirs

  @type_utils.LazyProperty
  def _test_list_schema(self):
    return file_utils.ReadFile(os.path.join(
        common.PUBLIC_TEST_LISTS_DIR,
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
      filelist = []
      filepaths = glob.glob(os.path.join(
          dirpath, '*' + manager.CONFIG_SUFFIX + config_utils.CONFIG_FILE_EXT))
      for filepath in filepaths:
        basename = os.path.basename(filepath)
        if basename in files:
          # Actually, files in private overlays will override the file with same
          # name in factory repository (if exists). We disallow this to make
          # things easier.
          raise RuntimeError('Multiple files with the same name %r' % basename)
        files[basename] = file_utils.ReadFile(filepath)
        filelist.append(basename)
      dirs.append(dict(name=dirname, path=dirpath, filelist=filelist))
    return dict(dirs=dirs, files=files)

  def SaveFiles(self, requests):
    """Write data into specified files.

    For safety purposes, both writing to anywhere other than test list folders
    and using different filename extension are prohibited.

    Args:
      requests: Dict[filepath: str, content: str].
    """
    for filepath, content in requests.iteritems():
      if not (
          filepath.endswith(
              manager.CONFIG_SUFFIX + config_utils.CONFIG_FILE_EXT) and
          any(os.path.dirname(filepath) == d[1] for d in self.dirs)):
        raise RuntimeError('Writing to %r is disallowed.' % filepath)
      file_utils.WriteFile(filepath, content)
