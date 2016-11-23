# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import subprocess

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


DEFAULT_KEY = 'shell_raw'


class ShellFunction(function.ProbeFunction):
  """Execute the shell command and return the output."""

  ARGS = [
      Arg('command', str, 'The shell command.'),
      Arg('key', str, 'The key of the result.', default=DEFAULT_KEY),
      Arg('split_line', bool, 'True to split lines to multiple results.',
          default=False),
  ]

  def Probe(self):
    try:
      output = process_utils.CheckOutput(self.args.command,
                                         shell=True, log=True)
    except subprocess.CalledProcessError:
      return function.NOTHING

    results = output.splitlines() if self.args.split_line else [output]
    return [{self.args.key: result.strip()}
            for result in results if result.strip()]
