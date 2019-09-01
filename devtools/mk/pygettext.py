#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Originally written by Barry Warsaw <barry@zope.com>
#
# Minimally patched to make it even more xgettext compatible
# by Peter Funk <pf@artcom-gmbh.de>
#
# 2002-11-22 Jürgen Hermann <jh@web.de>
# Added checks that _() only contains string literals, and
# command line args are resolved to module lists, i.e. you
# can now pass a filename, a module or package name, or a
# directory (including globbing chars, important for Win32).
# Made docstring fit in 80 chars wide displays using pydoc.

# This file was modified to support Python, HTML and Javascript strings in
# Chrome OS factory software.
# The original version is from Python source repository:
# https://hg.python.org/cpython/file/2.7/Tools/i18n/pygettext.py


import argparse
import ast
import cgi
import collections
import HTMLParser
import json
import os
import re
import subprocess
import sys
import tempfile


POT_HEADER = r"""# SOME DESCRIPTIVE TITLE.
# Copyright (C) YEAR ORGANIZATION
# FIRST AUTHOR <EMAIL@ADDRESS>, YEAR.
#
msgid ""
msgstr ""
"Project-Id-Version: PACKAGE VERSION\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
"Language-Team: LANGUAGE <LL@li.org>\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=CHARSET\n"
"Content-Transfer-Encoding: ENCODING\n"

"""


ESCAPE_CHAR_MAP = {
    '\\': r'\\', '\t': r'\t', '\r': r'\r', '\n': r'\n', '\"': r'\"'
}


def Escape(s):
  def EscapeChar(c):
    if 32 <= ord(c) <= 126:
      return ESCAPE_CHAR_MAP.get(c, c)
    return '\\%03o' % ord(c)
  return ''.join(EscapeChar(c) for c in s)


def Unescape(s):
  def UnescapeChar(match):
    escape_char = next((k for k, v in ESCAPE_CHAR_MAP.iteritems()
                        if v == match.group(0)), None)
    return escape_char or chr(int(match.group(1), 8))
  return re.sub(r'\\([\\trn"]|[0-7]{3})', UnescapeChar, s)


def Normalize(s):
  # This converts the various Python string types into a format that is
  # appropriate for .po files, namely much closer to C style.
  lines = s.splitlines(True)
  if len(lines) != 1:
    lines.insert(0, '')
  return '\n'.join('"%s"' % Escape(l) for l in lines)


def WritePot(fp, messages, width):
  print >> fp, POT_HEADER

  # Collect files with same text together.
  message_dict = {}
  for fileloc, text in messages:
    message_dict.setdefault(text, set()).add(fileloc)

  messages = []
  for text, files in message_dict.iteritems():
    files = sorted(files)
    messages.append((files, text))
  messages.sort()

  for files, text in messages:
    locline = '#:'
    filenames = set(filename for filename, unused_index in files)
    for filename in sorted(list(filenames)):
      s = ' ' + filename
      if len(locline) + len(s) <= width:
        locline = locline + s
      else:
        print >> fp, locline
        locline = "#:" + s
    if len(locline) > 2:
      print >> fp, locline
    print >> fp, 'msgid', Normalize(text)
    print >> fp, 'msgstr ""\n'


class PyAstVisitor(ast.NodeVisitor):
  def __init__(self, keywords):
    super(PyAstVisitor, self).__init__()
    self.messages = []
    self.keywords = keywords

  def visit_Call(self, node):
    # The function should either be the form of Keyword (ast.Name) or
    # module.Keyword (ast.Attribute).
    func_name = None
    if isinstance(node.func, ast.Name):
      func_name = node.func.id
    elif isinstance(node.func, ast.Attribute):
      func_name = node.func.attr

    if func_name is not None and func_name in self.keywords and node.args:
      first_arg = node.args[0]
      if isinstance(first_arg, ast.Str):
        self.messages.append(first_arg.s)

    # Continue visit in all case.
    super(PyAstVisitor, self).generic_visit(node)

  @classmethod
  def ParseFile(cls, filename, options):
    visitor = cls(options.py_keywords)
    with open(filename) as fp:
      source = fp.read()
    try:
      node = ast.parse(source, filename)
    except SyntaxError as e:
      raise RuntimeError('line %d, column %d: %s' %
                         (e.lineno, e.offset, e.text))
    visitor.visit(node)
    return visitor.messages


VOID_ELEMENTS = ['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                 'keygen', 'link', 'menuitem', 'meta', 'param', 'source',
                 'track', 'wbr']


class HTMLMessageParser(HTMLParser.HTMLParser, object):
  # pylint: disable=abstract-method
  def __init__(self, html_tags):
    super(HTMLMessageParser, self).__init__()
    self.messages = []
    self.html_tags = set(html_tags)
    self.tags = []
    self.data = []
    self.in_keyword_tag = False

  def _MakeStartTag(self, tag, attrs, self_closing=False):
    attrs_str = ''.join(' %s="%s"' % (key, cgi.escape(value, quote=True))
                        for key, value in attrs)
    return '<%s%s%s>' % (tag, attrs_str, '/' if self_closing else '')

  def handle_starttag(self, tag, attrs):
    if self.in_keyword_tag:
      self.data.append(self._MakeStartTag(tag, attrs))

    if tag not in VOID_ELEMENTS:
      if self.in_keyword_tag:
        self.tags.append((tag, False))
      else:
        is_keyword = tag in self.html_tags
        self.tags.append((tag, is_keyword))
        if is_keyword:
          self.in_keyword_tag = True

  def handle_endtag(self, tag):
    if tag not in VOID_ELEMENTS:
      open_tag, is_keyword = self.tags.pop()
      if open_tag != tag:
        row, col = self.getpos()
        raise ValueError('%s,%s: Unexpected close tag, expected %s, got %s.' % (
            row, col, open_tag, tag))

      if is_keyword:
        msg = ''.join(self.data).strip()
        if msg:
          self.messages.append(msg)
        self.data = []
        self.in_keyword_tag = False

    if self.in_keyword_tag:
      self.data.append('</%s>' % tag)

  def handle_startendtag(self, tag, attrs):
    if self.in_keyword_tag:
      self.data.append(self._MakeStartTag(tag, attrs, self_closing=True))

  def handle_data(self, data):
    if self.in_keyword_tag:
      self.data.append(re.sub(r'\s+', ' ', data))

  def handle_entityref(self, name):
    if self.in_keyword_tag:
      self.data.append('&%s;' % name)

  def handle_charref(self, name):
    if self.in_keyword_tag:
      self.data.append('&#%s;' % name)

  def close(self):
    super(HTMLMessageParser, self).close()
    if self.tags:
      raise ValueError('Found unclosed tags: %r' % ([t[0] for t in self.tags]))

  @classmethod
  def ParseFile(cls, filename, options):
    parser = cls(options.html_tags)
    with open(filename) as fp:
      parser.feed(fp.read())
    parser.close()
    return parser.messages


def GetPotMessages(pot_filename):
  def ParseFileComments(comment):
    return [(filename, int(lineno))
            for filename, lineno in re.findall(r'(\S+?):(\d+)', comment)]

  def ParseMsgId(msgid):
    return ''.join(Unescape(s[1:-1]) for s in msgid.splitlines(False))

  with open(pot_filename) as fp:
    pot = fp.read()

  match = re.findall(r"""
  ((?:^\#:\ .*\n)+)  # The filename:lineno reference comment
  ^msgid\ (".*"\n(?:^".*"\n)*)  # The msgid
  """, pot, re.MULTILINE | re.VERBOSE)
  return [(filename, ParseMsgId(msgid))
          for comment, msgid in match
          for filename in ParseFileComments(comment)]


def ParseJSFiles(files, options):
  if not files:
    return []

  # Use xgettext to extract translatable text from javascript sources, and
  # merge them with our output.
  with tempfile.NamedTemporaryFile(prefix='pygettext', delete=False) as f:
    temp_filename = f.name
  keyword_args = ['-k' + keyword for keyword in options.js_keywords]
  cmd = [
      'xgettext', '--from-code=UTF-8', '--language=javascript', '-o',
      temp_filename, '--omit-header', '-k']
  cmd.extend(keyword_args)
  cmd.append('--')
  cmd.extend(files)

  try:
    if options.verbose:
      print 'Running xgettext on JS files %r' % files
    subprocess.check_call(cmd)
    return GetPotMessages(temp_filename)
  finally:
    if os.path.exists(temp_filename):
      os.remove(temp_filename)


def ParseJSONTestList(filename, options):
  prefixes = options.json_prefixes
  with open(filename, 'r') as fp:
    test_list = json.load(fp)

  messages = []

  def RecursiveFindMessages(obj):
    # json.load strings are always unicode.
    if isinstance(obj, unicode):
      for prefix in prefixes:
        if obj.startswith(prefix):
          messages.append(obj[len(prefix):])
          break
    elif isinstance(obj, list):
      for item in obj:
        RecursiveFindMessages(item)
    elif isinstance(obj, dict):
      for key in sorted(obj):
        RecursiveFindMessages(obj[key])

      # If key is label, assume that value is a i18n message.
      if 'label' in obj:
        value = obj['label']
        if isinstance(value, unicode) and not any(
            value.startswith(prefix) for prefix in prefixes):
          messages.append(value)

  RecursiveFindMessages(test_list)

  return messages


def ParseMultipleFilesWrapper(func):
  def Inner(files, options):
    messages = []
    for filename in files:
      if options.verbose:
        print 'Working on %s' % filename
      try:
        new_messages = func(filename, options)
        messages.extend(((filename, i), msg)
                        for i, msg in enumerate(new_messages))
      except Exception as e:
        sys.exit('ERROR %s: %s' % (filename, e))
    return messages
  return Inner


PARSERS = {
    '.py': ParseMultipleFilesWrapper(PyAstVisitor.ParseFile),
    '.html': ParseMultipleFilesWrapper(HTMLMessageParser.ParseFile),
    '.json': ParseMultipleFilesWrapper(ParseJSONTestList),
    '.js': ParseJSFiles
}


def main():
  parser = argparse.ArgumentParser(
      description='pygettext -- Python equivalent of xgettext(1)')
  parser.add_argument(
      '-k', '--keyword', dest='py_keywords', action='append', default=[],
      help=('Keywords to look for in python source code. '
            'You can have multiple -k flags on the command line.'))
  parser.add_argument(
      '-t', '--tags', dest='html_tags', action='append', default=[],
      help=('HTML custom tag names to look for in HTML. '
            'You can have multiple -t flags on the command line.'))
  parser.add_argument(
      '-j', '--js-keyword', dest='js_keywords', action='append', default=[],
      help=('Keywords to look for in javascript source code. '
            'You can have multiple -j flags on the command line.'))
  parser.add_argument(
      '-J', '--json-prefix', dest='json_prefixes', action='append', default=[],
      help=('Prefix to look for in JSON test lists. '
            'You can have multiple -J flags on the command line.'))
  parser.add_argument(
      '-o', '--output', default='messages.pot', dest='output_file',
      help='Rename the default output file from messages.pot to filename.')
  parser.add_argument(
      '-v', '--verbose', action='store_true',
      help='Print the names of the files being processed.')
  parser.add_argument(
      '-w', '--width', default=78, type=int,
      help='Set width of output to columns.')
  parser.add_argument(
      'input_files', nargs='*',
      help=('Input file. Can either be Python source code, JavaScript, JSON '
            'test list or HTML.'))
  options = parser.parse_args()

  input_files_by_type = collections.defaultdict(list)
  for filename in options.input_files:
    ext = os.path.splitext(filename)[1]
    if ext in PARSERS:
      input_files_by_type[ext].append(filename)
    else:
      sys.exit('Unknown file type %s for file %s' % (ext, filename))

  messages = []
  for filetype, files in input_files_by_type.iteritems():
    messages.extend(PARSERS[filetype](files, options))

  with open(options.output_file, 'w') as fp:
    WritePot(fp, messages, options.width)

if __name__ == '__main__':
  main()
