# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import os

from cros.factory.probe.lib import probe_function
from cros.factory.utils.arg_utils import Arg


DEFAULT_KEY = 'path'


class GlobPathFunction(probe_function.ProbeFunction):
  """Finds all the pathnames matching the pattern.

  Description
  -----------
  The output of this function is a dictionary with only one entry, whose key
  is specified by the argument ``key`` and the value is the matched path name
  (or the file name if ``filename_only=true``).

  Examples
  --------
  Let's assume that there are files::

    /tmp/aa/00.txt
    /tmp/aa/01.txt
    /tmp/aa/02.tgz
    /tmp/aa/03.tgz

  Then the probe statement ::

    {
      "eval": "glob_path:/tmp/aa/*.txt"
    }

  will have the corresponding probed results ::

    [
      {
        "path": "/tmp/aa/00.txt"
      },
      {
        "path": "/tmp/aa/01.txt"
      }
    ]

  And the probe statement ::

    {
      "eval": {
        "glob_path": {
          "pathname": "/tmp/aa/00.txt",
          "filename_only": true,
          "key": "filename"
        }
      }
    }

  will have the corresponding probed results ::

    [
      {
        "filename": "00.txt"
      }
    ]

  And the probe statement ::

    {
      "eval": "glob_path:/tmp/aa/no_such_file.txt"
    }

  will have the corresponding probed results ::

    [
    ]

  """
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
      paths = list(map(os.path.basename, paths))
    return [{self.args.key: path} for path in paths]
