#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility functions that are useful to factory tests."""

import array
import fcntl
import glob
import inspect
import logging
import multiprocessing
import os
import pipes
import Queue
import re
import signal
import subprocess
import sys
import threading
import time
import types
import traceback

from contextlib import contextmanager

from cros.factory.utils import process_utils


# For backward compatibility.
CheckOutput = process_utils.CheckOutput


def TimeString(unix_time=None, time_separator=':', milliseconds=True):
  """Returns a time (using UTC) as a string.

  The format is like ISO8601 but with milliseconds:

   2012-05-22T14:15:08.123Z

  Args:
    unix_time: Time in seconds since the epoch.
    time_separator: Separator for time components.
    milliseconds: Whether to include milliseconds.
  """

  t = unix_time or time.time()
  ret = time.strftime(
      "%Y-%m-%dT%H" + time_separator + "%M" + time_separator + "%S",
      time.gmtime(t))
  if milliseconds:
    ret += ".%03d" % int((t - int(t)) * 1000)
  ret += "Z"
  return ret


def in_chroot():
  """Returns True if currently in the chroot."""
  return 'CROS_WORKON_SRCROOT' in os.environ


def in_qemu():
  """Returns True if running within QEMU."""
  return 'QEMU' in open('/proc/cpuinfo').read()


def is_process_alive(pid):
  """Returns true if the named process is alive and not a zombie."""
  try:
    with open("/proc/%d/stat" % pid) as f:
      return f.readline().split()[2] != 'Z'
  except IOError:
    return False


def kill_process_tree(process, caption):
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
    ps_output = process_utils.Spawn(['ps', '--no-headers', '-eo', 'pid,ppid'],
                                    stdout=subprocess.PIPE)
    children = {}
    for line in ps_output.stdout:
      match = re.findall('\d+', line)
      children.setdefault(int(match[1]), []).append(int(match[0]))
    pids = []
    def add_children(pid):
      pids.append(pid)
      map(add_children, children.get(pid, []))
    add_children(root)
    # Reverse the list to first kill children then parents.
    # Note reversed(pids) will return an iterator instead of real list, so
    # we must explicitly call pids.reverse() here.
    pids.reverse()
    return pids

  pids = get_all_pids(process.pid)
  for sig in [signal.SIGTERM, signal.SIGKILL]:
    logging.info('Stopping %s (pid=%s)...', caption, sorted(pids))

    for _ in range(25): # Try 25 times (200 ms between tries)
      for pid in pids:
        try:
          logging.info("Sending signal %s to %d", sig, pid)
          os.kill(pid, sig)
        except OSError:
          pass
      pids = filter(is_process_alive, pids)
      if not pids:
        return
      time.sleep(0.2) # Sleep 200 ms and try again

  logging.warn('Failed to stop %s process. Ignoring.', caption)


def are_shift_keys_depressed():
  """Returns True if both shift keys are depressed."""
  # From #include <linux/input.h>
  KEY_LEFTSHIFT = 42
  KEY_RIGHTSHIFT = 54

  for kbd in glob.glob("/dev/input/by-path/*kbd"):
    try:
      f = os.open(kbd, os.O_RDONLY)
    except OSError:
      if in_chroot():
        # That's OK; we're just not root
        continue
      else:
        raise
    buf = array.array('b', [0] * 96)

    # EVIOCGKEY (from #include <linux/input.h>)
    fcntl.ioctl(f, 0x80604518, buf)

    def is_pressed(key):
      return (buf[key / 8] & (1 << (key % 8))) != 0

    if is_pressed(KEY_LEFTSHIFT) and is_pressed(KEY_RIGHTSHIFT):
      return True

  return False


def var_log_messages_before_reboot(lines=100,
                                   max_length=5*1024*1024,
                                   path='/var/log/messages'):
  """Returns the last few lines in /var/log/messages before the current boot.

  Args:
    lines: number of lines to return.
    max_length: maximum amount of data at end of file to read.
    path: path to /var/log/messages.

  Returns:
    An array of lines. Empty if the marker indicating kernel boot
    could not be found.
  """
  offset = max(0, os.path.getsize(path) - max_length)
  with open(path) as f:
    f.seek(offset)
    data = f.read()

  # Find the last element matching the RE signaling kernel start.
  matches = list(re.finditer(
      r'^(\S+)\s.*kernel:\s+\[\s+0\.\d+\] Linux version', data, re.MULTILINE))
  if not matches:
    return []

  match = matches[-1]
  tail_lines = data[:match.start()].split('\n')
  tail_lines.pop() # Remove incomplete line at end

  # Skip some common lines that may have been written before the Linux
  # version.
  while tail_lines and any(
    re.search(x, tail_lines[-1])
    for x in [r'0\.000000\]',
         r'rsyslogd.+\(re\)start',
         r'/proc/kmsg started']):
    tail_lines.pop()

  # Done! Return the last few lines.
  return tail_lines[-lines:] + [
      '<after reboot, kernel came up at %s>' % match.group(1)]


def DrainQueue(queue):
  """Returns as many elements as can be obtained from a queue without blocking.

  (This may be no elements at all.)
  """
  ret = []
  while True:
    try:
      ret.append(queue.get_nowait())
    except Queue.Empty:
      break
  return ret


def TryMakeDirs(path):
  """Tries to create a directory and its parents.

  Doesn't ever raise an exception if it can't create the directory.
  """
  try:
    if not os.path.exists(path):
      os.makedirs(path)
  except Exception:
    pass


def LogAndCheckCall(*args, **kwargs):
  """Logs a command and invokes subprocess.check_call."""
  logging.info('Running: %s', ' '.join(pipes.quote(arg) for arg in args[0]))
  return subprocess.check_call(*args, **kwargs)


def LogAndCheckOutput(*args, **kwargs):
  """Logs a command and invokes subprocess.check_output."""
  logging.info('Running: %s', ' '.join(pipes.quote(arg) for arg in args[0]))
  return CheckOutput(*args, **kwargs)


class Enum(frozenset):
  """An enumeration type.

  Usage:
    To create a enum object:
      dummy_enum = utils.Enum(['A', 'B', 'C'])

    To access a enum object, use:
      dummy_enum.A
      dummy_enum.B
  """
  def __getattr__(self, name):
    if name in self:
      return name
    raise AttributeError


def ReadOneLine(filename):
  """Returns the first line as a string from the given file."""
  return open(filename, 'r').readline().rstrip('\n')


def FormatExceptionOnly():
  """Formats the current exception string.

  Must only be called from inside an exception handler.

  Returns:
    A string.
  """
  return '\n'.join(
    traceback.format_exception_only(*sys.exc_info()[:2])).strip()


def StartDaemonThread(*args, **kwargs):
  """Creates, starts, and returns a daemon thread.

  Args:
    See threading.Thread().
  """
  thread = threading.Thread(*args, **kwargs)
  thread.daemon = True
  thread.start()
  return thread


def FlattenList(lst):
  """Flattens a list, recursively including all items in contained arrays.

  For example:

    FlattenList([1,2,[3,4,[]],5,6]) == [1,2,3,4,5,6]
  """
  return sum((FlattenList(x) if isinstance(x, list) else [x]
              for x in lst),
             [])


class LoadManager(object):
  """A class to manage cpu load using stressapptest.
  This manager runs stressapptest with 20% memory and specified num_threads
  and duration.
  Usage:
    with LoadManager(num_threads, duration_secs):
      do_something_under_load
  Properties:
    _process: The process to run stressapptest
    _num_threads: The number of threads in running stressapptest.
    _memory_ratio: The memory ratio in running stressapptest.
  """
  def __init__(self, duration_secs, num_threads=None, memory_ratio=0.2, ):
    """Initialize LoadManager.

    Args:
      duration_secs: The duration of stressapptest.
      num_threads: Number of threads for stressapptest. Default value
        is number of cpus.
        If set, this should be less than or equal to number of cpus.
      memory_ratio: The ratio of memory used in stressapptest.
        Default value is 0.2.
        This should be less than or equal to 0.9.
    """
    self._process = None
    self._memory_ratio = None
    self._num_threads = None
    if num_threads is None:
      self._num_threads = multiprocessing.cpu_count()
    elif num_threads == 0:
      # No need to run stressapptest
      return
    else:
      self._num_threads = min(num_threads, multiprocessing.cpu_count())
    self._memory_ratio = min(0.9, memory_ratio)
    mem = open('/proc/meminfo').readline().split()[1]
    mem_usage = int(int(mem) * self._memory_ratio / 1024)
    self._process = process_utils.Spawn(
        ['stressapptest', '-m', '%d' % self._num_threads,
         '-M', '%d' %  mem_usage, '-s',  '%d' % duration_secs])
    logging.info('LoadManager: Start LoadManager with %d processes'
                 ' %d M memory %d seconds.',
                 self._num_threads, mem_usage, duration_secs)

  def __enter__(self):
    return self

  def __exit__(self, *args, **kwargs):
    self.Stop()

  def Stop(self):
    logging.info('LoadManager: Try to stop the process if there is one.')
    if self._process and self._process.poll() is None:
      logging.info('LoadManager: Terminating the process.')
      self._process.terminate()


def Retry(max_retry_times, interval, callback, target, *args, **kwargs):
  """Retries a function call with limited times until it returns True.

  Args:
    max_retry_times: The max retry times for target function to return True.
    interval: The sleep interval between each trial.
    callback: The callback after each retry iteration. Caller can use this
              callback to track progress. Callback should accept two arguments:
              callback(retry_time, max_retry_times).
    target: The target function for retry. *args and **kwargs will be passed to
            target.

  Returns:
    Within max_retry_times, if the return value of target function is
    neither None nor False, returns the value.
    If target function returns False or None or it throws
    any exception for max_retry_times, returns None.
  """
  result = None
  for retry_time in xrange(max_retry_times):
    try:
      result = target(*args, **kwargs)
    except Exception: # pylint: disable=W0703
      logging.exception('Retry...')
    if(callback):
      callback(retry_time, max_retry_times)
    if result:
      logging.info('Retry: Get result in retry_time: %d.', retry_time)
      break
    time.sleep(interval)
  return result


class TimeoutError(Exception):
  """Timeout error."""
  pass


@contextmanager
def Timeout(secs):
  """Timeout context manager. It will raise TimeoutError after timeout.
  It does not support nested "with Timeout" blocks.
  """
  def handler(signum, frame): # pylint: disable=W0613
    raise TimeoutError('Timeout')

  if secs:
    old_handler = signal.signal(signal.SIGALRM, handler)
    prev_secs = signal.alarm(secs)
    assert not prev_secs, 'Alarm was already set before.'

  try:
    yield
  finally:
    if secs:
      signal.alarm(0)
      signal.signal(signal.SIGALRM, old_handler)


def SendKey(key_sequence):
  """Send the given key sequence through X server.

  Args:
    key_sequence: This can be a list of keys to send or a string of key
        sequence.  For example:
          - list: ['f', 'o', 'o'] sends the string 'foo' through xdotool.
          - string: 'Alt+F4' sends the F4 key wth modifier Alt through xdotool.
        For more details, see the help of xdotool.
  """
  os.environ['DISPLAY'] = ':0'
  os.environ['XAUTHORITY'] = '/home/chronos/.Xauthority'
  if isinstance(key_sequence, list):
    process_utils.Spawn(['xdotool', 'key'] + key_sequence)
  elif isinstance(key_sequence, basestring):
    process_utils.Spawn(['xdotool', 'key', key_sequence])
  else:
    raise ValueError('key_sequence must be a list or a string')


def WaitFor(condition, timeout_secs, poll_interval=0.1):
  """Wait for the given condition for at most the specified time.

  Args:
    condition: A function object.
    timeout_secs: Timeout value in seconds.
    poll_interval: Interval to poll condition.

  Raises:
    ValueError: If condition is not a function.
    TimeoutError: If cond does not become True after timeout_secs seconds.
  """
  if not callable(condition):
    raise ValueError('condition must be a callable object')

  def _GetConditionString():
    condition_string = condition.__name__
    if condition.__name__ == '<lambda>':
      try:
        condition_string = inspect.getsource(condition).strip()
      except IOError:
        pass
    return condition_string

  end_time = time.time() + timeout_secs
  while True:
    if condition():
      break
    if time.time() > end_time:
      raise TimeoutError('Timeout waititng for %r' % _GetConditionString())
    time.sleep(poll_interval)


def SetTouchpadTwoFingerScrollingX(enabled):
  """Enables / disables two-finger scrolling.

  Currently this function only disables X-axis two-finger scrolling, as it can
  accidentally trigger 'last page'.

  Args:
    enabled: True or False indicating the state of two-finger scrolling to set.
  """
  TPSCONTROL_XINPUT = '/opt/google/touchpad/tpcontrol_xinput'
  def GetPropIdValue(prop_name):
    # Example 'xinput list-props <id>' output format:
    #        ...
    #        Scroll X Out Scale (379):       2.500000
    #        Scroll Y Out Scale (380):       2.500000
    #        ...
    prop_id_re = re.compile(
        r'^\s*(?:%s).*'       # Match property name.
        r'\((\d+)\):\s*'      # Get property ID.
        r'(.*)$' % prop_name, # Get property value.
        flags=re.M)
    xinput_list_props = CheckOutput([TPSCONTROL_XINPUT, 'status'])
    matched_obj = prop_id_re.search(xinput_list_props)
    if matched_obj:
      return matched_obj.groups()
    else:
      return (None, None)

  os.environ['DISPLAY'] = ':0'
  os.environ['XAUTHORITY'] = '/home/chronos/.Xauthority'
  property_name = 'Scroll X Out Scale'    # We only disable X-axis scrolling.
  default_scale = '2.5'

  prop_id = GetPropIdValue(property_name)[0]
  if not prop_id:
    # Cannot find the requested property ID.  This can happen during early
    # development stages if touchpad driver is not in place.
    return

  if bool(enabled):
    prop_value = default_scale
  else:
    prop_value = '0'
  process_utils.Spawn([TPSCONTROL_XINPUT, 'set', prop_id, prop_value])
