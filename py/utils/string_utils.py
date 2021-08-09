# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This module provides utility functions for string processing."""


from collections import namedtuple
import logging


def DecodeUTF8(data):
  """Decodes data as UTF-8, replacing any bad characters.

  If data is not bytes type, returns as-is.
  """
  if isinstance(data, bytes):
    return data.decode('utf-8', errors='replace')
  return data


def _ParseDictRecursive(lines, delimiter=':'):
  """Equilavant to `ParseDict(lines, recursive=True)`"""

  def _IndentLevel(line):
    return len(line) - len(line.lstrip())

  Node = namedtuple('Node', ['line', 'childs', 'level'])
  stack = [Node('root' + delimiter, [], -1)]  # root node

  for line in lines:

    # Skip empty line
    if len(line.strip()) == 0:
      continue

    level = _IndentLevel(line)
    while level <= stack[-1].level:
      node = stack.pop()
      stack[-1].childs.append(node)
    stack.append(Node(line, [], level))

  while len(stack) > 1:
    node = stack.pop()
    stack[-1].childs.append(node)

  def _BuildDictRecursive(node):
    key, value = map(str.strip, node.line.split(delimiter, 1))

    if len(node.childs) == 0:
      return key, value

    output_dict = {}
    for child in node.childs:
      output_dict.update([_BuildDictRecursive(child)])

    return key, output_dict

  return _BuildDictRecursive(stack.pop())[-1]


def ParseDict(lines, delimiter=':', recursive=False):
  """Parses list of lines into a dict. Each line is a string containing
  key, value pair, where key and value are separated by delimiter, and are
  stripped. If key, value pair can not be found in the line, that line will be
  skipped.

  Args:
    lines: A list of strings.
    delimiter: The delimiter string to separate key and value in each line.
    recursive: Whether to parse the dict recursively.

  Returns:
    A dict, where both keys and values are string.
  """

  if recursive:
    return _ParseDictRecursive(lines, delimiter)

  ret = dict()
  for line in lines:
    try:
      key, value = line.split(delimiter, 1)
    except ValueError:
      logging.warning('Can not extract key, value pair in %s', line)
    else:
      ret[key.strip()] = value.strip()
  return ret


def ParseString(value):
  """Parses a string if it is actually a True/False/None/Int value.

  Args:
    value: A string.

  Returns:
    True if the string matches one of 'True' and 'true. False if the string
    matches one of 'False' and 'false'. None if the string matches 'None'.
    An int if the string can be casted to an integer. Returns a string if
    nothing matched.
  """
  if value in ['True', 'true']:
    value = True
  elif value in ['False', 'false']:
    value = False
  elif value == 'None':
    value = None
  else:
    try:
      value = int(value)
    except ValueError:
      pass  # No sweat
  return value


def ParseUrl(url):
  """Parses a URL string according to RFC 1738.
  Note: We allow '/' character in 'user', so we can specify workgroup of smb
  user.

  Args:
    url: An URL string.

  Returns:
    A dict with optional keys 'scheme', 'user', 'password', 'host', 'port', and
    'urlpath'.
  """
  result = {}

  scheme, delimiter, schemepart = url.partition('://')
  if not delimiter:
    return {}
  result['scheme'] = scheme

  userpass, unused_delimiter, hostpath = schemepart.rpartition('@')
  if userpass:
    user, delimiter, password = userpass.partition(':')
    result['user'] = user
    if delimiter:
      result['password'] = password

  hostport, delimiter, path = hostpath.partition('/')
  if delimiter:
    result['path'] = '/' + path

  host, unused_delimiter, port = hostport.partition(':')
  if host:
    result['host'] = host
  else:
    return {}
  if port:
    result['port'] = port

  return result
