#!/usr/bin/env python
#
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Google Factory Tools Common Library

This module includes several common utilities for Google Factory Tools
A detailed description of gft_common.
"""

import os
import subprocess
import sys
import tempfile
import time


########################################################################
# Global Variables


_debug = False
_verbose = True


########################################################################
# Common Utilities


def SetDebugLevel(level):
  """ Sets the debugging level. """
  global _debug
  _debug = level


def SetVerboseLevel(level):
  """ Sets the verbosity level. """
  global _verbose
  _verbose = level


def WarningMsg(msg):
  """ Prints warning messages (to stderr) as-is. """
  sys.stderr.write("%s\n" % msg)


def VerboseMsg(msg):
  """ Prints verbose message, if SetVerboseLevel was called with True. """
  if _verbose:
    WarningMsg(msg)


def DebugMsg(msg):
  """ Prints message when debug is enabled. """
  if _debug:
    for entry in msg.splitlines():
      WarningMsg("(DEBUG) %s" % entry)


def ErrorMsg(msg):
  """ Prints messages to stderr with prefix "ERROR". """
  for entry in msg.splitlines():
    WarningMsg("ERROR: %s" % entry)


def ErrorDie(msg, return_code=1):
  """ Prints an error message and exit program. """
  ErrorMsg(msg)
  sys.exit(return_code)


def GetTemporaryFileName(prefix='gft'):
  """ Gets a unique file name for temporary usage. """
  (fd, filename) = tempfile.mkstemp(prefix=prefix)
  os.close(fd)
  return filename


def SystemOutput(command,
                 ignore_status=False,
                 show_progress=False,
                 progress_messsage=None):
  """ Retrieves the output of a shell command.
  Returns the output string.

  Args:
    ignore_status: False to raise exectopion when execution result is not zero
    show_progress: Shows progress by messages and dots
    progress_messsage: Messages printed before starting.
  """
  DebugMsg("SystemOutput: %s" % command)
  temp_stderr = tempfile.TemporaryFile()
  temp_stdout = tempfile.TemporaryFile()
  proc = subprocess.Popen(command,
                          stderr=temp_stderr,
                          stdout=temp_stdout,
                          shell=True)
  if show_progress:
    sys.stdout.flush()
    if progress_messsage:
      sys.stderr.write(progress_messsage)
    while proc.poll() is None:
      sys.stderr.write('.')
      time.sleep(1)
    if progress_messsage:
      sys.stderr.write('\n')
  else:
    proc.communicate()
  temp_stdout.seek(0)
  out = temp_stdout.read()
  if proc.wait() and (not ignore_status):
    temp_stderr.seek(0)
    err = temp_stderr.read()
    raise Exception('Failed executing command: %s\n'
                    'Output and Error Messages: %s\n%s\n' % (command, out, err))
  if out[-1:] == '\n':
    out = out[:-1]
  return out


def ReadOneLine(filename):
  """ Reads one line from file. """
  with open(filename) as opened_file:
    return opened_file.readline().strip()


def ReadFile(filename):
  """ Reads whole file. """
  with open(filename) as opened_file:
    return opened_file.read().strip()


def WriteFile(filename, data):
  """ Writes one file and exit. """
  with open(filename, "w") as opened_file:
    opened_file.write(data)


########################################################################
# Components Databases


def LoadComponentsDatabaseFile(filename):
  """ Loads a components database file. """
  with open(filename) as database:
    return eval(database.read())


def GetComponentsDatabaseBase(database_file):
  """ Gets the base folder of a components database file.  """
  # Currently the database file is assuming properties sit in its parent folder.
  base = os.path.join(os.path.split(os.path.abspath(database_file))[0], '..')
  return os.path.abspath(base)


if __name__ == '__main__':
  print "Google Factory Tool Common Library."
