# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os

from cros.factory.probe.lib import probe_function
from cros.factory.utils.arg_utils import Arg


DEFAULT_FILE_KEY = 'file_raw'


def ReadFile(path, binary_mode=False, skip=0, size=-1):
  logging.debug('Read file: %s', path)
  if not os.path.isfile(path):
    return None
  mode = 'rb' if binary_mode else 'r'
  with open(path, mode) as f:
    f.seek(skip)
    data = f.read(size)
  if not binary_mode:
    ret = data.strip()
  else:
    binary_data = ['0x%02x' % char for char in data]
    ret = ' '.join(binary_data)
  if not ret:
    return None
  return ret


class FileFunction(probe_function.ProbeFunction):
  """Read the content of a file.

  Description
  -----------
  The content of the file is stripped and the empty content is filtered. If the
  ``split_lines`` argument is set, then the content will be splitted by line.
  The file path is allowed unix style to match multiple files.

  Examples
  --------
  Let's say if the file tree looks like:

  - ``/tmp/aaa/x`` contains::

      Hello, Google
      Hello, ChromiumOS

  - ``/tmp/aaa/y`` contains::

      Bye, Everyone

  And the probe statement is::

    {
      "eval": "file:/tmp/aaa/x"
    }

  Then the probed results will be::

    [
      {
        "file_row": "Hello, Google\\nHello, ChromiumOS"
      }
    ]

  If the probe statement is ::

    {
      "eval": {
        "file": {
          "file_path": "/tmp/aaa/*",
          "split_line": true,
          "key": "my_awesome_key"
        }
      }
    }

  , then the probed results will be::

    [
      {
        "my_awesome_key": "Hello, Google"
      },
      {
        "my_awesome_key": "Hello, ChromiumOS"
      },
      {
        "my_awesome_key": "Bye, Everyone"
      }
    ]

  In above example we use ``"split_line": true`` to let this function treat
  each line of the content of a file as different results.  And instead of
  just specifying a real path, we have ``/tmp/aaa/*`` to match both
  ``/tmp/aaa/x`` and ``/tmp/aaa/y``.
  """
  ARGS = [
      Arg('file_path', str, 'The file path of target file.'),
      Arg('key', str, 'The key of the result.',
          default=DEFAULT_FILE_KEY),
      Arg('split_line', bool, 'True to split lines to multiple results.',
          default=False),
  ]

  def Probe(self):
    ret = []
    for path in glob.glob(self.args.file_path):
      if os.path.isfile(path):
        data = ReadFile(path)
        if data is None:
          continue
        contents = data.splitlines() if self.args.split_line else [data]
        ret += [{self.args.key: content.strip()}
                for content in contents if content.strip()]
    return ret
