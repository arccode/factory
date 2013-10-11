# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Independent general functions useful for most other code."""


import collections
import logging
import re
import time
import yaml

from subprocess import Popen, PIPE


class Error(Exception):
  """Generic fatal error."""
  pass


class TimeoutError(Error):
  """Timeout error."""
  pass


class Obj(object):
  """Generic wrapper allowing dot-notation dict access."""

  def __init__(self, **field_dict):
    self.__dict__.update(field_dict)

  def __repr__(self):
    return repr(self.__dict__)


def Shell(cmd, stdin=None, log=True):
  """Run cmd in a shell, return Obj containing stdout, stderr, and status.

  The cmd stdout and stderr output is debug-logged.

  Args:
    cmd: Full shell command line as a string, which can contain
      redirection (popes, etc).
    stdin: String that will be passed as stdin to the command.
    log: log command and result.
  """
  process = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=True)
  stdout, stderr = process.communicate(input=stdin)  # pylint: disable=E1123
  if log:
    logging.debug('running %s' % repr(cmd) +
                  (', stdout: %s' % repr(stdout.strip()) if stdout else '') +
                  (', stderr: %s' % repr(stderr.strip()) if stderr else ''))
  status = process.poll()
  return Obj(stdout=stdout, stderr=stderr, status=status, success=(status == 0))


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
    data = ' '.join(x for x in data if x)
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


def YamlWrite(structured_data):
  """Wrap yaml.dump to make calling convention consistent."""
  return yaml.dump(structured_data, default_flow_style=False)


def YamlRead(serialized_data):
  """Wrap yaml.load to make calling convention consistent."""
  return yaml.safe_load(serialized_data)


def ParseKeyValueData(pattern, data):
  """Converts structured text into a {(key, value)} dict.

  Args:
    pattern: A regex pattern to decode key/value pairs
    data: The text to be parsed.

  Returns:
    A { key: value, ... } dict.

  Raises:
    ValueError: When the input is invalid.
  """
  parsed_list = {}
  for line in data.splitlines():
    matched = re.match(pattern, line.strip())
    if not matched:
      raise ValueError('Invalid data: %s' % line)
    (name, value) = (matched.group(1), matched.group(2))
    if name in parsed_list:
      raise ValueError('Duplicate key: %s' % name)
    parsed_list[name] = value
  return parsed_list


def MakeList(value):
  """Converts the given value to a list.

  Returns:
    A list of elements from "value" if it is iterable (except string);
    otherwise, a list contains only one element.
  """
  if (isinstance(value, collections.Iterable) and
      not isinstance(value, basestring)):
    return list(value)
  return [value]


def MakeSet(value):
  """Converts the given value to a set.

  Returns:
    A set of elements from "value" if it is iterable (except string);
    otherwise, a set contains only one element.
  """
  if (isinstance(value, collections.Iterable) and
      not isinstance(value, basestring)):
    return set(value)
  return set([value])
