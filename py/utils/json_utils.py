# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""JSON utilities.

This module provides utilities to serialize or deserialize Python objects
to/from JSON strings or JSON files.
"""

import json
import os


LoadStr = json.loads


def LoadFile(file_path):
  """Deserialize a file consists of a JSON string to a Python object.

  Args:
    file_path: The path of the file to be deserialize.

  Returns:
    The deserialized Python object.
  """
  with open(file_path) as f:
    return LoadStr(f.read())


def DumpStr(obj, pretty=False, newline=None, **json_dumps_kwargs):
  """Serialize a Python object to a JSON string.

  Args:
    obj: a Python object to be serialized.
    pretty: True to output in human-friendly pretty format.
    newline: True to append a newline in the end of result, default to the
      previous argument ``pretty``.
    json_dumps_kwargs: Any allowable arguments to json.dumps.

  Returns:
    The serialized JSON string.
  """
  if newline is None:
    newline = pretty

  if pretty:
    kwargs = dict(indent=2, separators=(',', ': '), sort_keys=True)
  else:
    kwargs = {}
  kwargs.update(json_dumps_kwargs)
  result = json.dumps(obj, **kwargs)

  if newline:
    result += '\n'

  return result


def DumpFile(file_path, obj, pretty=True, newline=None, **json_dumps_kwargs):
  """Write serialized JSON string of a Python object to a given file.

  Args:
    file_path: The path of the file.
    obj: a Python object to be serialized.
    pretty: True to output in human-friendly pretty format.
    newline: True to append a newline in the end of output, default to the
      previous argument ``pretty``.
    json_dumps_kwargs: Any allowable arguments to json.dumps.
  """
  with open(file_path, 'w') as f:
    f.write(DumpStr(obj, pretty=pretty, newline=newline, **json_dumps_kwargs))


class JSONDatabase(dict):
  """A dict bound to a JSON file."""

  def __init__(self, file_path, allow_create=False):
    """Initialize and read the JSON file.

    Args:
      file_path: The path of the JSON file.
      allow_create: If True, the file will be automatically created if not
        exists.
    """
    super(JSONDatabase, self).__init__()
    self._file_path = file_path
    if not allow_create or os.path.exists(file_path):
      self.Load()
    else:
      self.Save()

  def Load(self, file_path=None):
    """Read a JSON file and replace the content of this object.

    Args:
      file_path: The path of the JSON file, defaults to argument ``file_path``
        of initialization.
    """
    self.clear()
    self.update(LoadFile(file_path or self._file_path))

  def Save(self, file_path=None):
    """Write the content to a JSON file.

    Args:
      file_path: The path of the JSON file, defaults to argument ``file_path``
        of initialization.
    """
    DumpFile(file_path or self._file_path, self)
