# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.functions import file as file_module
from cros.factory.utils.arg_utils import Arg


def ReadSysfs(dir_path, keys):
  """Reads the required files in the folder.

  Args:
    dir_path: the path of the target folder.

  Returns:
    a dict mapping from the file name to the content of the file.
    Return None if none of the required files are found.
  """
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
  return ret


class SysfsFunction(function.ProbeFunction):
  """Read the required files in a directory.

  Sysfs exports the information of device to a directory, and each attribute is
  stored in a separate file. This function is aimed to read the structure.
  """
  ARGS = [
      Arg('dir_path', str, 'The path of target sysfs folder.'),
      Arg('keys', list, 'The required file names in the sysfs folder.'),
  ]

  def Probe(self):
    ret = []
    for path in glob.glob(self.args.dir_path):
      result = ReadSysfs(path, self.args.keys)
      if result is not None:
        ret.append(result)
    return ret

