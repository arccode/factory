# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os

from cros.factory.probe.functions import file as file_module
from cros.factory.probe.lib import probe_function
from cros.factory.utils.arg_utils import Arg


def ReadSysfs(dir_path, keys, optional_keys=None):
  """Reads the required files in the folder.

  Args:
    dir_path: the path of the target folder.
    key: The required file names in the sysfs folder.
    optional_keys: The optional file names in the sysfs folder.

  Returns:
    a dict mapping from the file name to the content of the file.
    Return None if none of the required files are found.
  """
  if optional_keys is None:
    optional_keys = []
  if not os.path.isdir(dir_path):
    return None
  logging.debug('Read sysfs path: %s', dir_path)
  ret = {}
  for key in keys:
    file_path = os.path.join(dir_path, key)
    content = file_module.ReadFile(file_path)
    if content is None:
      return None
    ret[key] = content
  for key in optional_keys:
    file_path = os.path.join(dir_path, key)
    content = file_module.ReadFile(file_path)
    if content is not None:
      ret[key] = content
  return ret


class SysfsFunction(probe_function.ProbeFunction):
  """Read the required files in a directory.

  Description
  -----------
  Sysfs exports the information of device to a directory, and each attribute is
  stored in a separate file.  This function is aimed to read the structure.

  Examples
  --------
  Let's say we have the file tree:

  - ``/sys/bus/cool/devices/1/aa`` contains "A"
  - ``/sys/bus/cool/devices/2/aa`` contains "AA"
  - ``/sys/bus/cool/devices/2/bb`` contains "BB"
  - ``/sys/bus/cool/devices/3/xx`` contains "XX"

  And the probe statement is::

    {
      "eval": {
        "sysfs": {
          "dir_path": "/sys/bus/cool/devices/*",
          "keys": [
            "aa"
          ],
          "optional_keys": [
            "bb"
          ]
        }
      }
    }

  Then the probed results are::

    [
      {
        "aa": "A"
      },
      {
        "aa": "AA",
        "bb": "BB"
      }
    ]

  The probed results don't include the entry ``/sys/bus/cool/devices/3``
  because that entry doesn't contain the required field ``aa``.
  """

  ARGS = [
      Arg('dir_path', str, 'The path of target sysfs folder.'),
      Arg('keys', list, 'The required file names in the sysfs folder.'),
      Arg('optional_keys', list, 'The optional file names in the sysfs folder.',
          default=None),
  ]

  def Probe(self):
    ret = []
    for path in glob.glob(self.args.dir_path):
      result = ReadSysfs(path, self.args.keys, self.args.optional_keys)
      if result is not None:
        ret.append(result)
    return ret
