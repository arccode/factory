# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import subprocess

from cros.factory.probe import function
from cros.factory.probe.lib import probe_function
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


DEFAULT_KEY = 'shell_raw'


class ShellFunction(probe_function.ProbeFunction):
  """Execute the shell command and return the output.

  Description
  -----------
  This function executes the specific shell command and takes the standard
  output of that command as the probed results if the return code is zero.

  The output of a probe function is always in dictionary type.  The output of
  this function will contain only one entry, whose key is specified by the
  argument ``key`` and the value is the standard output of the command.

  Examples
  --------
  Let's assume that the output of the command ``ls`` is::

    aaa
    bbb
    ccc

  Then the probe statement ::

    {
      "eval": "shell:ls"
    }

  will have the corresponding probed result ::

    [
      {
        "shell_raw": "aaa\\nbbb\\nccc"
      }
    ]

  Another example is that the probe statement ::

    {
      "eval": {
        "shell": {
          "command": "ls",
          "split_line": true,   # Treat each line as different probe results.
          "key": "my_key_name"  # Use "my_key_name" as the key in the output
                                # dictionary
        }
      }
    }

  will have the corresponding probed results ::

    [
      {
        "my_key_name": "aaa"
      },
      {
        "my_key_name": "bbb"
      },
      {
        "my_key_name": "ccc"
      }
    ]

  The command can be even more complex like ::

    {
      "eval": "shell:ls | grep aaa"
    }

  In above case, the probed result will be empty if the output of ``ls``
  command doesn't contain ``aaa`` because ``grep aaa`` will have a non-zero
  return code when it cannot find ``aaa`` from its standard input.
  """

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
