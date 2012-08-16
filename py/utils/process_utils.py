# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import getpass
import logging
import os
import pipes
import subprocess
import types
from StringIO import StringIO


PIPE = subprocess.PIPE


# File descriptor for /dev/null.
dev_null = None


def WrapLines(data):
  '''Returns a function that returns a list of all lines in data.'''
  def Wrapper(strip=False):
    ret = StringIO(data).readlines()
    if strip:
      ret = [x.strip() for x in ret]
    return ret

  return Wrapper


def OpenDevNull():
  '''Opens and returns a readable/writable file pointing to /dev/null.

  The file object may be reused.
  '''
  global dev_null  # pylint: disable=W0603
  if not dev_null:
    # There is a possible race condition here, but it is extremely
    # unlikely and won't hurt anyway (we'll just have multiple files
    # pointing at /dev/null).
    dev_null = open(os.devnull, 'r+')

  return dev_null


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
    log: Do a logging.info before running the command, or to any
      logging object to call its info method.
    stdout: Same as subprocess.Popen, but may be set to DEV_NULL to discard
      all stdout.
    stderr: Same as subprocess.Popen, but may be set to DEV_NULL to discard
      all stderr.
    call: Wait for the command to complete.
    check_call: Wait for the command to complete, throwing an
      exception if it fails.  This implies call=True.  This may be either
      True to signify that any non-zero exit status is failure, or a function
      that takes a returncode and returns True if that returncode is
      considered OK (e.g., lambda returncode: returncode in [0,1]).
    check_output: Wait for the command to complete, throwing an
      exception if it fails, and saves the contents to the return
      object's stdout_data attribute.  Implies check_call=True and
      read_stdout=True.
    log_stderr_on_error: Log stderr only if the command fails.
      Implies read_stderr=True and call=True.
    read_stdout: Wait for the command to complete, saving the contents
      to the return object's stdout_data attribute.  This implies
      call=True and stdout=PIPE.
    ignore_stdout: Ignore stdout.
    read_stderr: Wait for the command to complete, saving the contents
      to the return object's stderr_data attribute.  This implies
      call=True and stderr=PIPE.
    ignore_stderr: Ignore stderr.
    sudo: Prepend sudo to arguments if user is not root.

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
  check_output = kwargs.pop('check_output', False)
  read_stdout = kwargs.pop('read_stdout', False)
  ignore_stdout = kwargs.pop('ignore_stdout', False)
  read_stderr = kwargs.pop('read_stderr', False)
  ignore_stderr = kwargs.pop('ignore_stderr', False)
  log_stderr_on_error = kwargs.pop('log_stderr_on_error', False)
  sudo = kwargs.pop('sudo', False)

  if sudo and getpass.getuser() != 'root':
    if kwargs.pop('shell', False):
      args = ['sudo', 'sh', '-c', args]
    else:
      args = ['sudo'] + args

  if ignore_stdout:
    assert not read_stdout
    assert not kwargs.get('stdout')
    kwargs['stdout'] = OpenDevNull()
  if ignore_stderr:
    assert not read_stderr
    assert not log_stderr_on_error
    assert not kwargs.get('stderr')
    kwargs['stderr'] = OpenDevNull()

  if check_output:
    check_call = check_call or True
    read_stdout = True
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
    assert kwargs.get('stderr') in [None, PIPE]
    kwargs['stderr'] = PIPE

  if call and (not read_stdout) and kwargs.get('stdout') == PIPE:
    raise ValueError('Cannot use call=True argument with stdout=PIPE, '
                     'since OS buffers may get filled up')
  if call and (not read_stderr) and kwargs.get('stderr') == PIPE:
    raise ValueError('Cannot use call=True argument with stderr=PIPE, '
                     'since OS buffers may get filled up')

  process = subprocess.Popen(args, **kwargs)
  process.stdout_data = None
  process.stdout_lines = None
  process.stderr_data = None
  process.stderr_lines = None

  if call:
    if read_stdout or read_stderr:
      stdout, stderr = process.communicate()
      if read_stdout:
        process.stdout_data = stdout
        process.stdout_lines = WrapLines(process.stdout_data)
      if read_stderr:
        process.stderr_data = stderr
        process.stderr_lines = WrapLines(process.stderr_data)
      process.communicate = (
          lambda: (process.stdout_data, process.stderr_data))
    else:
      # No need to communicate; just wait
      process.wait()

    if type(check_call) == types.FunctionType:
      failed = not check_call(process.returncode)
    else:
      failed = process.returncode != 0
    if failed:
      if log or log_stderr_on_error:
        message = 'Exit code %d from command: "%s"' % (
            process.returncode, args_to_log)
        if log_stderr_on_error:
          message += '; stderr: """\n%s\n"""' % process.stderr_data
        logger.error(message)

      if check_call:
        raise subprocess.CalledProcessError(process.returncode, args)

  return process
