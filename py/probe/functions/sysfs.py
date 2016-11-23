# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils.arg_utils import Arg


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
      result = self._ReadSysfs(path)
      if result is not None:
        ret.append(result)
    return ret

  def _ReadSysfs(self, dir_path):
    """Read the required files in the folder.

    Args:
      dir_path: the path of the target folder.

    Returns:
      a dict mapping from the file name to the content ot the file.
      Return None if any required file is not found.
    """
    if not os.path.isdir(dir_path):
      return None
    logging.debug('Read path: %s', dir_path)
    ret = {}
    for key in self.args.keys:
      file_path = os.path.join(dir_path, key)
      if not os.path.isfile(file_path):
        return None
      with open(file_path, 'r') as f:
        content = f.read().strip()
      ret[key] = content
    return ret
