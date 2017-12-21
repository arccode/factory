# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""JSON utilities.

This module provides utilities to serialize or deserialize Python objects
to/from JSON strings or JSON files.
"""

import json
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import type_utils


def LoadStr(s, convert_to_str=True):
  """Deserialize a JSON string to a Python object.

  Args:
    s: a JSON string.
    convert_to_str: Whether to convert the unicode type elements into str type.

  Returns:
    The deserialized Python object.
  """
  json_obj = json.loads(s)
  return (json_obj if not convert_to_str
          else type_utils.UnicodeToString(json_obj))


def LoadFile(file_path, convert_to_str=True):
  """Deserialize a file consists of a JSON string to a Python object.

  Args:
    file_path: The path of the file to be deserialize.
    convert_to_str: Whether to convert the unicode type elements into str type.

  Returns:
    The deserialized Python object.
  """
  with open(file_path) as f:
    return LoadStr(f.read(), convert_to_str=convert_to_str)


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

  def __init__(self, file_path, allow_create=False, convert_to_str=True):
    """Initialize and read the JSON file.

    Args:
      file_path: The path of the JSON file.
      allow_create: If True, the file will be automatically created if not
        exists.
    """
    super(JSONDatabase, self).__init__()
    self._file_path = file_path
    self._convert_to_str = convert_to_str
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
    self.update(LoadFile(file_path or self._file_path,
                         convert_to_str=self._convert_to_str))

  def Save(self, file_path=None):
    """Write the content to a JSON file.

    Args:
      file_path: The path of the JSON file, defaults to argument ``file_path``
        of initialization.
    """
    DumpFile(file_path or self._file_path, self)
