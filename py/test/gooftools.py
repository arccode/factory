# Copyright 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Wrapper for Google Factory Tools (gooftool).

This module provides fast access to "gooftool".
"""


import os
import subprocess
import tempfile

from cros.factory.test.env import paths
from cros.factory.test import session
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


GOOFTOOL_HOME = '/usr/local/factory'


def run(command, ignore_status=False):
  """Runs a gooftool command.

  Args:
    command: Shell command to execute.
    ignore_status: False to raise exception when execution result is not 0.

  Returns:
    (stdout, stderr, return_code) of the execution results.

  Raises:
    error.TestError: The error message in "ERROR:.*" form by command.
  """

  session.console.info('Running gooftool: %s', command)

  # We want the stderr goes to CONSOLE_LOG_PATH immediately, but tee only
  # works with stdout; so here's a tiny trick to swap the handles.
  swap_stdout_stderr = '3>&1 1>&2 2>&3'

  # When using pipes, return code is from the last command; so we need to use
  # a temporary file for the return code of first command.
  console_log_path = paths.CONSOLE_LOG_PATH
  file_utils.TryMakeDirs(os.path.dirname(console_log_path))
  return_code_file = tempfile.NamedTemporaryFile()
  system_cmd = ('(PATH=%s:$PATH %s %s || echo $? >"%s") | tee -a "%s"' %
                (GOOFTOOL_HOME, command, swap_stdout_stderr,
                 return_code_file.name, console_log_path))
  proc = subprocess.Popen(system_cmd,
                          stderr=subprocess.PIPE,
                          stdout=subprocess.PIPE,
                          shell=True,
                          encoding='utf-8')

  # The order of output is reversed because we swapped stdout and stderr.
  (err, out) = proc.communicate()

  # normalize output data
  out = out or ''
  err = err or ''
  if out.endswith('\n'):
    out = out[:-1]
  if err.endswith('\n'):
    err = err[:-1]

  # build return code and log results
  return_code_file.seek(0)
  return_code = int(return_code_file.read() or '0')
  return_code_file.close()
  return_code = proc.wait() or return_code
  message = ('gooftool result: %s (%s), message: %s' %
             (('FAILED' if return_code else 'SUCCESS'),
              return_code, '\n'.join([out, err]) or '(None)'))
  session.console.info(message)

  if return_code and (not ignore_status):
    # try to parse "ERROR.*" from err & out.
    exception_message = '\n'.join(
        [error_message for error_message in err.splitlines()
         if error_message.startswith('ERROR')]) or message
    raise type_utils.TestFailure(exception_message)

  return (out, err, return_code)
