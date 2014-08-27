# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Independent general functions useful for most other code."""


import collections
import logging
import re
import time

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


def CheckDictKeys(dict_to_check, allowed_keys):
  """Makes sure that a dictionary's keys are valid.

  Args:
    dict_to_check: A dictionary.
    allowed_keys: The set of allowed keys in the dictionary.
  """
  if not isinstance(dict_to_check, dict):
    raise TypeError('Expected dict but found %s' % type(dict_to_check))

  extra_keys = set(dict_to_check) - set(allowed_keys)
  if extra_keys:
    raise ValueError('Found extra keys: %s' % list(extra_keys))


class AttrDict(dict):
  """Attribute dictionary.

  Use subclassed dict to store attributes. On __init__, the values inside
  initial iterable will be converted to AttrDict if its type is a builtin
  dict or builtin list.

  Example:
    foo = AttrDict()
    foo['xyz'] = 'abc'
    assertEqual(foo.xyz, 'abc')

    bar = AttrDict({'x': {'y': 'value_x_y'},
                    'z': [{'m': 'value_z_0_m'}]})
    assertEqual(bar.x.y, 'value_x_y')
    assertEqual(bar.z[0].m, 'value_z_0_m')
  """
  def _IsBuiltinDict(self, item):
    return (isinstance(item, dict) and
            item.__class__.__module__ == '__builtin__' and
            item.__class__.__name__ == 'dict')

  def _IsBuiltinList(self, item):
    return (isinstance(item, list) and
            item.__class__.__module__ == '__builtin__' and
            item.__class__.__name__ == 'list')

  def _ConvertList(self, itemlist):
    converted = []
    for item in itemlist:
      if self._IsBuiltinDict(item):
        converted.append(AttrDict(item))
      elif self._IsBuiltinList(item):
        converted.append(self._ConvertList(item))
      else:
        converted.append(item)
    return converted

  def __init__(self, *args, **kwargs):
    super(AttrDict, self).__init__(*args, **kwargs)
    for key, value in self.iteritems():
      if self._IsBuiltinDict(value):
        self[key] = AttrDict(value)
      elif self._IsBuiltinList(value):
        self[key] = self._ConvertList(value)
    self.__dict__ = self


class Singleton(type):
  """Singleton metaclass.

  Set __metaclass__ to Singleton to make it a singleton class. The instances
  are stored in:
    Singleton._instances[CLASSNAME]

  Example:
    class C(object):
      __metaclass__ = Singleton

    foo = C()
    bar = C()  # foo == bar
  """
  _instances = {}
  def __call__(mcs, *args, **kwargs):
    if mcs not in mcs._instances:
      mcs._instances[mcs] = super(Singleton, mcs).__call__(*args, **kwargs)
    return mcs._instances[mcs]
