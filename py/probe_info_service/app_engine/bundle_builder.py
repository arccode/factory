# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import base64
import collections
import io
import os
import string
import tarfile

from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


_RESOURCE_PATH = os.path.join(os.path.realpath(os.path.dirname(__file__)),
                              'resources')


class _TwoExclamationTemplate(string.Template):
  """A customized template class.

  Our template string itself is an incomplete script, which contains the
  default delimiter "$" everywhere.  Therefore, we redefine our delimiter
  with a different symbol.
  """
  delimiter = '!!'


@type_utils.CachedGetter
def _GetBundleTemplate():
  return _TwoExclamationTemplate(file_utils.ReadFile(os.path.join(
      _RESOURCE_PATH, 'bundle.template.sh')))


_FileEntry = collections.namedtuple('_FileEntry', ['path', 'mode', 'data'])


class BundleBuilder:
  """A helper class to pack the resources into the probe config bundle file."""

  _REGULAR_MODE = 0o644
  _EXECUTABLE_MODE = 0o755

  FILE_NAME_EXT = '.sh'

  def __init__(self):
    self._file_entries = []
    self._runner_path = None

  def AddRegularFile(self, path, data: bytes):
    """Adds a regular file into the probe config bundle.

    Args:
      path: Path of the file in the archive.
      data: The data in the form of bytes to be put.
    """
    self._file_entries.append(_FileEntry(path, self._REGULAR_MODE, data))

  def AddExecutableFile(self, path, data: bytes):
    """Adds an executable file into the probe config bundle.

    Args:
      path: Path of the file in the archive.
      data: The data in the form of bytes to be put.
    """
    self._file_entries.append(_FileEntry(path, self._EXECUTABLE_MODE, data))

  def SetRunnerFilePath(self, path):
    """Specifies the executable file to invoke after unpack.

    Args:
      path: Path of the file in the archive.
    """
    self._runner_path = path

  def Build(self) -> bytes:
    """Archives all the resources and returns the result in bytes."""
    tarfile_buf = io.BytesIO()
    with tarfile.open(mode='w:gz', fileobj=tarfile_buf) as tarfile_obj:
      for file_entry in self._file_entries:
        buf = io.BytesIO(file_entry.data)
        tarinfo = tarfile.TarInfo(file_entry.path)
        tarinfo.mode = file_entry.mode
        tarinfo.size = len(buf.getvalue())
        tarfile_obj.addfile(tarinfo, fileobj=buf)
    payload_data = base64.b64encode(tarfile_buf.getvalue()).decode('utf-8')
    return _GetBundleTemplate().substitute(
        payload_data=payload_data,
        runner_relpath=self._runner_path).encode('utf-8')
