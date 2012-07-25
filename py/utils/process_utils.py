# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import pipes
import subprocess


PIPE = subprocess.PIPE


def Spawn(args, **kwargs):
  '''
  Popen wrapper with extra functionality:

    - Sets close_fds to True by default.  (You may still set
      close_fds=False to leave all fds open.)

  Args:
    log: Set to True to do a logging.info before running the command,
      or to any logging object to call its info method.

    Also, all Popen args and kwargs are supported.

    TODO(jsalz): Add the following arguments:
      wait: Set to True to wait for the command to complete.
      check_call: Set to True to wait for the command to complete,
        throwing an exception if it fails.  This implies wait=True.
      read_stdout: Set to True to wait for the command to complete,
        saving the contents to the return object's stdout_data attribute.
        This implies wait=True and stdout=PIPE.
      read_stderr: Set to True to wait for the command to complete,
        saving the contents to the return object's stderr_data attribute.
        This implies wait=True and stderr=PIPE.
      check_output: Synonym for check_call=True, wait=True (equivalent to
        to Python 2.7's check_output).

  Returns/Raises:
    Same as Popen.
  '''
  kwargs.setdefault('close_fds', True)

  log = kwargs.pop('log', False)
  if log:
    logger = logging if (log == True) else log

    if kwargs.get('shell'):
      args_to_log = args
    else:
      args_to_log = ' '.join(pipes.quote(arg) for arg in args)
    logger.info('Running command: "%s"', args_to_log)

  process = subprocess.Popen(args, **kwargs)
  return process
