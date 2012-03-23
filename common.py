# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Independent general functions useful for most other code."""


import logging
import re
import time

from subprocess import Popen, PIPE


class Error(Exception):
  """Generic fatal error."""
  pass


class Obj(object):
  """Generic wrapper allowing dot-notation dict access."""

  def __init__(self, **field_dict):
    self.__dict__.update(field_dict)

  def __repr__(self):
    return repr(self.__dict__)


# TODO(tammo): Combine this with gft_common.ShellExecution.
def RunShellCmd(cmd):
  """Run cmd in a shell, return Obj containing stdout, stderr, and status.

  The cmd stdout and stderr output is debug-logged.

  Args:
    cmd: Full shell command line as a string, which can contain
      redirection (popes, etc).
  """
  process = Popen(cmd, stdout=PIPE, stderr=PIPE, shell=True)
  stdout, stderr = process.communicate()
  logging.debug('running %s' % repr(cmd) +
                (', stdout: %s' % repr(stdout.strip()) if stdout else '') +
                (', stderr: %s' % repr(stderr.strip()) if stderr else ''))
  return Obj(stdout=stdout, stderr=stderr, success=(not process.poll()))


def CompactStr(data):
  """Converts data to string with compressed white space.

  Args:
    data: Single string or a list/tuple of strings.

  Returns:
    If data is a string, compress all contained contiguous spaces to
    single spaces.  If data is a list or tuple, space-join and then
    treat like string input.
  """
  if isinstance(data, list) or isinstance(data, tuple):
    data = ' '.join(x for x in data if x != '')
  return re.sub('\s+', ' ', data).strip()


def SetupLogging(level=logging.WARNING, log_file_name=None):
  """Configure logging level, format, and target file/stream.

  Args:
    level: The logging.{DEBUG,INFO,etc} level of verbosity to show.
    log_file_name: File for appending log data.
  """
  logging.basicConfig(
      format='%(levelname)-8s %(asctime)-8s %(message)s',
      datefmt='%H:%M:%S',
      level=level,
      **({'filename': log_file_name} if log_file_name else {}))
  logging.Formatter.converter = time.gmtime
  logging.info(time.strftime('%Y.%m.%d %Z', time.gmtime()))
