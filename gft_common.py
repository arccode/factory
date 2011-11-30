#!/usr/bin/env python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Google Factory Tools Common Library

This module includes several common utilities for Google Factory Tools
A detailed description of gft_common.
"""

import os
import re
import subprocess
import sys
import tempfile
import threading
import time


########################################################################
# Global Variables


_debug = False
_verbose = False
_log_path = None

DEFAULT_CONSOLE_LOG_PATH = '/var/log/factory.log'


########################################################################
# Common Utilities


class GFTError(Exception):
  """ Exception for unrecoverable errors for GFT related functions. """

  def __init__(self, value):
    self.value = value

  def __str__(self):
    return repr(self.value)


def SetDebugLevel(level):
  """ Sets the debugging level. """
  global _debug
  _debug = level


def SetVerboseLevel(level, log_path=None):
  """ Sets the verbosity level and log output path. """
  global _verbose, _log_path
  _verbose = level
  if log_path:
    DebugMsg("Set log path to: " + log_path, log=False)
    _log_path = log_path


def Log(msg):
  """ Writes a message to pre-configured log file. """
  if not _log_path:
    return
  try:
    with open(_log_path, "at") as log_handle:
      lines = ["(GFT) %s %s\n" % (time.strftime("%Y%m%d %H:%M:%S"), entry)
               for entry in msg.splitlines()]
      log_handle.writelines(lines)
  except:
    sys.stderr.write("FAILED TO WRITE TO LOG FILE %s.\n" % _log_path)


def WarningMsg(msg):
  """ Prints warning messages (to stderr) as-is. """
  sys.stderr.write("%s\n" % msg)
  Log(msg)


def VerboseMsg(msg):
  """ Prints verbose message, if SetVerboseLevel was called with True. """
  if _verbose:
    WarningMsg(msg)
  else:
    Log(msg)


def DebugMsg(msg, log=True):
  """ Prints message when debug is enabled. """
  for entry in msg.splitlines():
    if _debug:
      WarningMsg("(DEBUG) %s" % entry)
    elif log:
      Log("(DEBUG) %s" % entry)


def ErrorMsg(msg):
  """ Prints messages to stderr with prefix "ERROR". """
  for entry in msg.splitlines():
    WarningMsg("ERROR: %s" % entry)


def ErrorDie(msg):
  """ Raises a GFTError exception. """
  raise GFTError(msg)


def GFTConsole(f):
  """Decorator for all Google Factory Test Tools console programs.

  log path will be redirectd to DEFAULT_CONSOLE_LOG_PATH by default,
  and all GFTError will be catched, logged, and exit as failure.
  """
  def main_wrapper(*args, **kw):
    # override the default log path
    global _log_path
    _log_path = DEFAULT_CONSOLE_LOG_PATH
    try:
      return f(*args, **kw)
    except GFTError, e:
      ErrorMsg(e.value)
      sys.exit(1)
  return main_wrapper


def GetTemporaryFileName(prefix='gft', suffix=''):
  """ Gets a unique file name for temporary usage. """
  (fd, filename) = tempfile.mkstemp(prefix=prefix, suffix=suffix)
  os.close(fd)
  return filename


def ShellExecution(command,
                   ignore_status=False,
                   show_progress=False,
                   progress_message=None):
  """ Executes a shell command, and return the results.

  Args:
    ignore_status: False to raise exectopion when execution result is not zero
    show_progress: Shows progress by messages and dots
    progress_message: Messages printed before starting.

  Returns:
    (exit_code, stdout_messages, stderr_messages)
  """
  DebugMsg("ShellExecution: %s" % command, log=False)
  temp_stderr = tempfile.TemporaryFile()
  temp_stdout = tempfile.TemporaryFile()
  proc = subprocess.Popen(command,
                          stderr=temp_stderr,
                          stdout=temp_stdout,
                          shell=True)
  if show_progress:
    sys.stdout.flush()
    if progress_message:
      sys.stderr.write(progress_message)
    while proc.poll() is None:
      sys.stderr.write('.')
      time.sleep(1)
    if progress_message:
      sys.stderr.write('\n')
  else:
    proc.communicate()

  # collect output
  temp_stdout.seek(0)
  out = temp_stdout.read()
  temp_stdout.close()

  temp_stderr.seek(0)
  err = temp_stderr.read()
  temp_stderr.close()

  exit_code = proc.wait()
  if exit_code:
    # prepare to log the error message.
    message = ('Failed executing command: %s\n'
               'Output and Error Messages: %s\n%s' % (command, out, err))
    if ignore_status:
      DebugMsg(message)
    else:
      ErrorDie(message)
  return (exit_code, out, err)


def SystemOutput(command,
                 ignore_status=False,
                 show_progress=False,
                 progress_message=None):
  """ Returns the stdout results from a shell command execution. """
  return ShellExecution(command, ignore_status, show_progress,
                        progress_message)[1].rstrip('\n')


def System(command,
           ignore_status=False,
           show_progress=False,
           progress_message=None):
  """ Returns the exit code from a shell command execution. """
  return ShellExecution(command, ignore_status, show_progress,
                        progress_message)[0]


def ReadOneLine(filename):
  """ Reads one line from file. """
  with open(filename) as opened_file:
    return opened_file.readline().strip()


def ReadFile(filename):
  """ Reads whole file. """
  with open(filename) as opened_file:
    return opened_file.read().strip()


def ReadBinaryFile(filename):
  """ Reads whole binary file. """
  with open(filename, "rb") as opened_file:
    return opened_file.read()


def WriteFile(filename, data):
  """ Writes one file and exit. """
  with open(filename, "w") as opened_file:
    opened_file.write(data)

def WriteBinaryFile(filename, data):
  """ Writes one binary file and exit. """
  with open(filename, "wb") as opened_file:
    opened_file.write(data)


def ThreadSafe(f):
  """ Decorator for functions that need synchronoization. """
  lock = threading.Lock()
  def threadsafe_call(*args):
    try:
      lock.acquire()
      return f(*args)
    finally:
      lock.release()
  return threadsafe_call


def Memorize(f):
  """ Decorator for functions that need memorization. """
  memorize_data = {}
  def memorize_call(*args):
    index = repr(args)
    if index in memorize_data:
      value = memorize_data[index]
      # DebugMsg('Memorize: using cached value for: %s %s' % (repr(f), index))
      return value
    value = f(*args)
    memorize_data[index] = value
    return value
  return memorize_call


if __name__ == '__main__':
  print "Google Factory Tool Common Library."
