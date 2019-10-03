# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import contextlib
import getpass
import logging
import os
import pipes
import re
import select
import signal
from StringIO import StringIO
import subprocess
import sys
import threading
import time
import traceback

from six import iteritems
from six.moves import xrange


try:
  PIPE = subprocess.PIPE
  Popen = subprocess.Popen
except Exception:
  # Hack for HWID Service on AppEngine. The subprocess module on AppEngine
  # doesn't contain these attributes. HWID Service will not use all of these
  # attributes. This makes AppEngine won't complain we are using process_utils.
  PIPE = None
  Popen = object


# File descriptor for /dev/null.
dev_null = None


def GetLines(data, strip=False):
  """Returns a list of all lines in data.

  Args:
    strip: If True, each line is stripped.
  """
  ret = StringIO(data).readlines()
  if strip:
    ret = [x.strip() for x in ret]
  return ret


def OpenDevNull():
  """Opens and returns a readable/writable file pointing to /dev/null.

  The file object may be reused.
  """
  global dev_null  # pylint: disable=global-statement
  if not dev_null:
    # There is a possible race condition here, but it is extremely
    # unlikely and won't hurt anyway (we'll just have multiple files
    # pointing at /dev/null).
    dev_null = open(os.devnull, 'r+')

  return dev_null


def IsProcessAlive(pid, ppid=None):
  """Returns true if the named process is alive and not a zombie.

  A PPID (parent PID) can be provided to be more specific to which process you
  are watching.  If there is a process with the same PID running but the PPID is
  not the same, then this is unlikely to be the same process, but a newly
  started one.  The function will return False in this case.

  Args:
    pid: process PID for checking
    ppid: specified the PID of the parent of given process.  If the PPID does
      not match, we assume that the named process is done, and we are looking at
      another process, the function returns False in this case.
  """
  try:
    with open('/proc/%d/stat' % pid) as f:
      stat = f.readline().split()
      if ppid is not None and int(stat[3]) != ppid:
        return False
      return stat[2] != 'Z'
  except IOError:
    return False


def CheckOutput(*args, **kwargs):
  """Runs command and returns its output.

  It is like subprocess.check_output but with the extra flexibility of Spawn.

  Args:
    Refer Spawn.

  Returns:
    stdout

  Raises:
    subprocess.CalledProcessError if returncode != 0.
  """
  kwargs['check_output'] = True
  return Spawn(*args, **kwargs).stdout_data


def SpawnOutput(*args, **kwargs):
  """Runs command and returns its output.

  Like CheckOutput. But it won't raise exception unless you set
  check_output=True.

  Args:
    Refer Spawn.

  Returns:
    stdout
  """
  kwargs['read_stdout'] = True
  return Spawn(*args, **kwargs).stdout_data


def LogAndCheckCall(*args, **kwargs):
  """Logs a command and invokes subprocess.check_call."""
  logging.info('Running: %s', ' '.join(pipes.quote(arg) for arg in args[0]))
  return subprocess.check_call(*args, **kwargs)


def LogAndCheckOutput(*args, **kwargs):
  """Logs a command and invokes subprocess.check_output."""
  logging.info('Running: %s', ' '.join(pipes.quote(arg) for arg in args[0]))
  return CheckOutput(*args, **kwargs)


class _ExtendedPopen(Popen):
  """Popen subclass supported a few extra methods.

  Attributes:
    stdout_data, stderr_data: Data read by communicate().  These are set by
      the Spawn call if read_stdout/read_stderr are True.
  """
  stdout_data = None
  stderr_data = None

  def stdout_lines(self, strip=False):
    """Returns lines in stdout_data as a list.

    Args:
      strip: If True, each line is stripped.
    """
    return GetLines(self.stdout_data, strip)

  def stderr_lines(self, strip=False):
    """Returns lines in stderr_data as a list.

    Args:
      strip: If True, each line is stripped.
    """
    return GetLines(self.stderr_data, strip)

  def communicate(self, *args, **kwargs):
    if self.stdout_data is None and self.stderr_data is None:
      return super(_ExtendedPopen, self).communicate(*args, **kwargs)
    else:
      return self.stdout_data, self.stderr_data


def Spawn(args, **kwargs):
  """Popen wrapper with extra functionality:

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
    env: Same as subprocess.Popen, set-up environment parameters if needed.

  Returns/Raises:
    Same as Popen.
  """
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
    message = 'Running command: "%s"' % args_to_log
    if 'cwd' in kwargs:
      message += ' in %s' % kwargs['cwd']
    logger.info(message)

  call = kwargs.pop('call', False)
  check_call = kwargs.pop('check_call', False)
  check_output = kwargs.pop('check_output', False)
  read_stdout = kwargs.pop('read_stdout', False)
  ignore_stdin = kwargs.pop('ignore_stdin', False)
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

  if ignore_stdin:
    assert not kwargs.get('stdin')
    kwargs['stdin'] = OpenDevNull()
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

  process = _ExtendedPopen(args, **kwargs)

  if call:
    if read_stdout or read_stderr:
      stdout, stderr = process.communicate()
      if read_stdout:
        process.stdout_data = stdout
      if read_stderr:
        process.stderr_data = stderr
    else:
      # No need to communicate; just wait
      process.wait()

    if callable(check_call):
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


def TerminateOrKillProcess(process, wait_seconds=1, sudo=False):
  """Terminates a process and waits for it.

  The function sends SIGTERM to terminate the process, if it's not terminated
  in wait_seconds, then sends a SIGKILL.
  """
  pid = process.pid
  logging.info('Stopping process %d', pid)
  if sudo:
    Spawn(['kill', str(pid)], sudo=True, check_call=True, log=True)
    return
  else:
    process.terminate()

  reaped = threading.Event()

  def WaitAndKill():
    reaped.wait(wait_seconds)
    if not reaped.is_set():
      try:
        logging.info('Sending SIGKILL to process %d', pid)
        process.kill()
      except Exception:
        pass
  thread = threading.Thread(target=WaitAndKill)
  thread.start()
  process.wait()
  reaped.set()
  thread.join()
  logging.info('Process %d stopped', pid)


def KillProcessTree(process, caption):
  """Kills a process and all its subprocesses.

  Args:
    process: The process to kill (opened with the subprocess module).
    caption: A caption describing the process.
  """
  # os.kill does not kill child processes. os.killpg kills all processes
  # sharing same group (and is usually used for killing process tree). But in
  # our case, to preserve PGID for autotest and upstart service, we need to
  # iterate through each level until leaf of the tree.

  def get_all_pids(root):
    ps_output = Spawn(['ps', '--no-headers', '-eo', 'pid,ppid'],
                      stdout=subprocess.PIPE)
    children = {}
    for line in ps_output.stdout:
      match = re.findall(r'\d+', line)
      children.setdefault(int(match[1]), []).append(int(match[0]))
    pids = []

    def add_children(pid):
      pids.append(pid)
      list(map(add_children, children.get(pid, [])))
    add_children(root)
    # Reverse the list to first kill children then parents.
    # Note reversed(pids) will return an iterator instead of real list, so
    # we must explicitly call pids.reverse() here.
    pids.reverse()
    return pids

  pids = get_all_pids(process.pid)
  for sig in [signal.SIGTERM, signal.SIGKILL]:
    logging.info('Stopping %s (pid=%s)...', caption, sorted(pids))

    tries = 25
    logging.info('Sending signal %s to %r (tries at most %d)', sig, pids, tries)
    for _ in range(tries):  # 200 ms between tries
      for pid in pids:
        try:
          os.kill(pid, sig)
        except OSError:
          pass
      pids = list(filter(IsProcessAlive, pids))
      if not pids:
        return
      time.sleep(0.2)  # Sleep 200 ms and try again

  logging.warn('Failed to stop %s process %r. Ignoring.', caption, pids)


def WaitEvent(event):
  """Waits for an event without timeout, without blocking signals.

  event.wait() masks all signals until the event is set; this can be used
  instead to make sure that the signal is delivered within 100 ms.

  Returns:
    True if the event is set (i.e., always, since there is no timeout).  This
      return value is used so that this method behaves the same way as
      event.wait().
  """
  while not event.is_set():
    event.wait(0.1)
  return True


def StartDaemonThread(*args, **kwargs):
  """Creates, starts, and returns a daemon thread.

  Args:
    interrupt_when_crash: If true, the thread sends interrupt signal when
        exception uncaught.
    For other parameters see threading.Thread().
  """
  if kwargs.pop('interrupt_on_crash', False):
    # 'target' is the second parameter of threading.Thread()
    target = args[1] if len(args) > 1 else kwargs.get('target')

    def _target(*_args, **_kwargs):
      try:
        target(*_args, **_kwargs)
      except Exception:
        logging.error(traceback.format_exc())
        os.kill(os.getpid(), signal.SIGINT)

    if len(args) > 1:
      args[1] = _target
    else:
      kwargs['target'] = _target

  thread = threading.Thread(*args, **kwargs)
  thread.daemon = True
  thread.start()
  return thread


class DummyFile(object):
  def write(self, x):  # pylint: disable=unused-argument
    pass

  def read(self, x):  # pylint: disable=unused-argument
    return ''


@contextlib.contextmanager
def RedirectStandardStreams(stdin=None, stdout=None, stderr=None):
  """Redirect standard stream.

  Args:
    stdin: A file object to override standard input.
    stdout: A file object to override standard output.
    stderr: A file object to override standard error.
    If stdin, stdout, stderr is None, then the stream is not redirected.

  Raises:
    IOError: raise the exception if the standard streams is redirected again
             within the context.
  """
  args = {'stdin': stdin, 'stdout': stdout, 'stderr': stderr}
  redirect_streams = dict((k, v) for k, v in iteritems(args) if v is not None)
  old_streams = dict((k, sys.__dict__[k]) for k in redirect_streams)

  for k, v in iteritems(redirect_streams):
    sys.__dict__[k] = v

  yield

  changed = dict((k, sys.__dict__[k]) for k, v in iteritems(redirect_streams)
                 if v is not sys.__dict__[k])
  if changed:
    raise IOError('Unexpected standard stream redirections: %r' % changed)
  for k, v in iteritems(old_streams):
    sys.__dict__[k] = v


# TODO(pihsun): Implement another version of this function using reader thread
# for platform that doesn't have select on pipes. (For example, Windows.)
def PipeStdoutLines(process, callback, read_timeout=0.1):
  """Read a process stdout and call callback for each line of stdout.

  This blocks until the process ends, and ignore all stdout after that. It's
  guaranteed that process.wait() is called before return, so the
  process.returncode is set after this function.

  Args:
    process: The process created by Spawn.
    callback: Callback to be executed on each output line. The argument to
        the callback would be the line received.
    read_timeout: The timeout of each read. This function would block at most
        read_timeout seconds after the process is ended.
  """
  buf = ['']

  def _TryReadOutputLines(timeout):
    rlist, unused_wlist, unused_xlist = select.select([process.stdout],
                                                      [], [], timeout)
    if process.stdout not in rlist:
      return False

    # Read a chunk of the process output. This should not block because of the
    # above select, and can return chunk with size < 4096.
    data = os.read(process.stdout.fileno(), 4096)
    if not data:
      return False

    num_lines = data.count('\n')
    buf[0] += data
    for unused_i in xrange(num_lines):
      line, unused_sep, buf[0] = buf[0].partition('\n')
      callback(line)
    return True

  while process.poll() is None:
    _TryReadOutputLines(read_timeout)

  # Consume all buffered output just before the process end.
  while _TryReadOutputLines(0):
    pass

  process.wait()
