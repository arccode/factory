# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils.arg_utils import Arg


DEFAULT_KEY = 'path'


class GlobPathFunction(function.ProbeFunction):
  """Finds all the pathnames matching the pattern."""
  ARGS = [
      Arg('pathname', str, 'The file path of target file.'),
      Arg('key', str, 'The key of the result.',
          default=DEFAULT_KEY),
      Arg('filename_only', bool, 'True to return the file name instead of the '
          'whole path.',
          default=False),
  ]

  def Probe(self):
    paths = glob.glob(self.args.pathname)
    if self.args.filename_only:
      paths = map(os.path.basename, paths)
    return [{self.args.key: path} for path in paths]
