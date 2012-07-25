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
    - Provides a consistent interface to functionality like the call,
      check_call, and check_output functions in subprocess.

  To get a command's output, logging stderr if the process fails:

    # Doesn't check retcode
    Spawn(['cmd'], read_stdout=True, log_stderr_on_error=True).stdout_data
    # Throws CalledProcessError on error
    Spawn(['cmd'], read_stdout=True, log_stderr_on_error=True,
          check_call=True).stdout_data

  To get a command's stdout and stderr, without checking the retcode:

    stdout, stderr = Spawn(
        ['cmd'], read_stdout=True, read_stderr=True).communicate()

  Args:
    log: Set to True to do a logging.info before running the command,
      or to any logging object to call its info method.
    call: Set to True to wait for the command to complete.
    check_call: Set to True to wait for the command to complete,
      throwing an exception if it fails.  This implies call=True.
    log_stderr_on_error: Logs stderr only if the command fails.  Implies
      read_stderr=True and call=True.
    read_stdout: Set to True to wait for the command to complete,
      saving the contents to the return object's stdout_data attribute.
      This implies call=True and stdout=PIPE.
    read_stderr: Set to True to wait for the command to complete,
      saving the contents to the return object's stderr_data attribute.
      This implies call=True and stderr=PIPE.

  Returns/Raises:
    Same as Popen.
  '''
  kwargs.setdefault('close_fds', True)

  logger = logging
  log = kwargs.pop('log', False)
  if kwargs.get('shell'):
    args_to_log = args
  else:
    args_to_log = ' '.join(pipes.quote(arg) for arg in args)

  if log:
    if log != True:
      logger = log
    logger.info('Running command: "%s"', args_to_log)

  call = kwargs.pop('call', False)
  check_call = kwargs.pop('check_call', False)
  read_stdout = kwargs.pop('read_stdout', False)
  read_stderr = kwargs.pop('read_stderr', False)
  log_stderr_on_error = kwargs.pop('log_stderr_on_error', False)

  if check_call:
    call = True
  if log_stderr_on_error:
    read_stderr = True
  if read_stdout:
    call = True
    assert kwargs.get('stdout') in [None, PIPE]
    kwargs['stdout'] = PIPE
  if read_stderr:
    call = True
    assert kwargs.get('stdout') in [None, PIPE]
    kwargs['stderr'] = PIPE

  if call and (not read_stdout) and kwargs.get('stdout') == PIPE:
    raise ValueError('Cannot use call=True argument with stdout=PIPE, '
                     'since OS buffers may get filled up')
  if call and (not read_stderr) and kwargs.get('stderr') == PIPE:
    raise ValueError('Cannot use call=True argument with stderr=PIPE, '
                     'since OS buffers may get filled up')

  process = subprocess.Popen(args, **kwargs)
  process.stdout_data = None
  process.stderr_data = None

  if call:
    if read_stdout or read_stderr:
      stdout, stderr = process.communicate()
      if read_stdout:
        process.stdout_data = stdout
      if read_stderr:
        process.stderr_data = stderr
      process.communicate = (
          lambda: (process.stdout_data, process.stderr_data))
    else:
      # No need to communicate; just wait
      process.wait()

    if process.returncode != 0:
      if log or log_stderr_on_error:
        message = 'Exit code %d from command: "%s"' % (
            process.returncode, args_to_log)
        if log_stderr_on_error:
          message += '; stderr: """\n%s\n"""' % process.stderr_data
        logger.error(message)

      if check_call:
        raise subprocess.CalledProcessError(process.returncode, args)

  return process
