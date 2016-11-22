# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils.arg_utils import Arg


DEFAULT_FILE_KEY = 'file_raw'


class FileFunction(function.ProbeFunction):
  """Read the content of a file.

  The content of the file is stripped and the empty content is filtered. If the
  "split_line" argument is set, then the content will be splitted by line. The
  file path is allowed unix style to match multiple files.
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
        ret += self._ReadFile(path)
    return ret

  def _ReadFile(self, path):
    logging.info('Read file: %s', path)
    with open(path, 'r') as f:
      data = f.read()
    results = data.splitlines() if self.args.split_line else [data]
    return [{self.args.key: result.strip()}
            for result in results if result.strip()]
