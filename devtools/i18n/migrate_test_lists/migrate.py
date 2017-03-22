#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import collections
from lib2to3 import refactor
import logging
import os
import subprocess
import sys
import tempfile


_HAS_YAPF = True


def CheckYapf(no_yapf):
  """Detect whether there's yapf.

  We use yapf instead of pyformat since we need the --style option.
  """
  global _HAS_YAPF  # pylint: disable=global-statement
  if subprocess.call('which yapf >/dev/null 2>&1', shell=True):
    if not no_yapf:
      logging.error(
          'yapf not found, you can install it by "pip install yapf".')
      sys.exit(1)
    logging.warning('yapf not found, the transformed code may need to be'
                    ' manually formatted...'
                    ' You can install it by "pip install yapf".')
    _HAS_YAPF = False


def CalculateDiffRange(old_code_lines, new_code_lines):
  """A heuristic method to calculate which lines are changed in new code."""
  ptr_idx = 0
  changed_lines = []
  for i, line in enumerate(new_code_lines):
    try:
      idx = old_code_lines.index(line, ptr_idx)
    except ValueError:
      changed_lines.append(i + 1)  # lineno are 1-index
      continue
    ptr_idx = idx + 1

  ranges = []
  for lineno in changed_lines:
    if not ranges or lineno != ranges[-1][1] + 1:
      ranges.append([lineno, lineno])
    else:
      ranges[-1][1] += 1

  return ranges


class FormattedRefactoringTool(refactor.RefactoringTool):
  def write_file(self, new_text, filename, old_text, encoding=None):
    if not _HAS_YAPF:
      return super(FormattedRefactoringTool, self).write_file(
          new_text, filename, old_text)

    if old_text is None:
      with open(filename, 'r') as fp:
        old_code_lines = fp.readlines()
    else:
      old_code_lines = old_text.splitlines(True)

    super(FormattedRefactoringTool, self).write_file(new_text, filename,
                                                     old_text, encoding)

    # Calculate difference between new code and old code, and use yapf to
    # format changed lines.
    new_code_lines = new_text.splitlines(True)
    diff_ranges = CalculateDiffRange(old_code_lines, new_code_lines)
    args = [
        '-i', '--style',
        '{based_on_style: chromium, ALLOW_MULTILINE_LAMBDAS: true,'
        'I18N_FUNCTION_CALL: __this_func_doesnt_exist__bypass_yapf_default}'
    ]
    for start, end in diff_ranges:
      args.append('-l')
      args.append('%s-%s' % (start, end))

    subprocess.check_call(['yapf'] + args + [filename])


escapes = []


def MakeEscapes():
  for i in range(256):
    if 32 <= i <= 126:
      escapes.append(chr(i))
    else:
      escapes.append("\\%03o" % i)
  escapes[ord('\\')] = r'\\'
  escapes[ord('\t')] = r'\t'
  escapes[ord('\r')] = r'\r'
  escapes[ord('\n')] = r'\n'
  escapes[ord('\"')] = r'\"'


def Escape(s):
  return ''.join(escapes[ord(c)] if ord(c) < 256 else c for c in s)


def Normalize(s):
  """Converts Python string to format appropriate for .po files."""
  lines = s.splitlines(True)
  if len(lines) != 1:
    lines.insert(0, '')
  return ('\n'.join('"%s"' % Escape(l) for l in lines)).encode('UTF-8')


def WritePot(fp, messages, pot_header, width=78):
  print >> fp, pot_header

  # Collect files with same text together.
  message_dict = {}
  for fileloc, text in messages:
    message_dict.setdefault(text, set()).add(fileloc)

  messages = []
  for text, files in message_dict.iteritems():
    files = list(files)
    files.sort()
    messages.append((files, text))
  messages.sort()

  for files, text in messages:
    locline = '#:'
    filenames = set(filename for filename, unused_lineno in files)
    for filename in sorted(list(filenames)):
      s = ' ' + filename
      if len(locline) + len(s) <= width:
        locline = locline + s
      else:
        if len(locline) > 2:
          print >> fp, locline
        locline = "#:" + s
    if len(locline) > 2:
      print >> fp, locline
    print >> fp, 'msgid', Normalize(text[0])
    print >> fp, 'msgstr', Normalize(text[1])
    print >> fp, ""


def CheckConflictMessages(messages):
  message_dict = collections.defaultdict(dict)
  for fileloc, (msgid, msgstr) in messages:
    message_dict[msgid].setdefault(msgstr, []).append(fileloc)

  has_conflict = False
  for msgid, items in message_dict.iteritems():
    if len(items) == 1:
      continue
    has_conflict = True
    logging.warn('msgid "%s" has multiple translations:', msgid)
    for msgstr, filelocs in items.iteritems():
      logging.warn('  "%s" => %s', msgstr,
                   ', '.join('%s:%d' % s for s in filelocs))

  if has_conflict:
    logging.error('Some conflicting translation found,'
                  ' please fix them and run the script again...')
    sys.exit(1)


def GetI18nMessages(files, write=False, summarize=True):
  rt = FormattedRefactoringTool(['fix_test_list_label'], {}, [])
  rt.refactor(files, write)
  if summarize:
    rt.summarize()

  i18n_messages = []
  for fixer in rt.pre_order:
    if hasattr(fixer, 'i18n_messages'):
      i18n_messages.extend(fixer.i18n_messages)
  for fixer in rt.post_order:
    if hasattr(fixer, 'i18n_messages'):
      i18n_messages.extend(fixer.i18n_messages)
  return i18n_messages


def main():
  parser = argparse.ArgumentParser(
      description='Migrate old test list label_{en,zh} to new style.')
  parser.add_argument(
      '-t',
      '--target-po',
      help='Target .po file to be merged to',
      required=True,
      dest='po_file')
  parser.add_argument(
      '--no-yapf',
      action='store_true',
      help=("Run even there's no yapf installed on system. "
            'The output code would need to be manually formatted.'))
  parser.add_argument('files', help='Files to be transformed', nargs='+')
  args = parser.parse_args()

  logging.basicConfig(
      format='[%(levelname).1s] %(asctime)-8s L%(lineno)-3d %(message)s',
      datefmt='%H:%M:%S',
      level=logging.INFO)

  CheckYapf(args.no_yapf)
  MakeEscapes()

  i18n_messages = GetI18nMessages(args.files, summarize=False)
  CheckConflictMessages(i18n_messages)

  GetI18nMessages(args.files, write=True)

  if i18n_messages:
    fd, temp_fn = tempfile.mkstemp(prefix='migrate_test_list_', suffix='.pot')
    os.close(fd)
    try:
      orig_po_header = subprocess.check_output(
          ['sed', '-e', '/^$/Q', args.po_file])
      with open(temp_fn, 'w') as fp:
        WritePot(fp, i18n_messages, orig_po_header)
      merged_po = subprocess.check_output(
          ['msgcat', '-o', '-', args.po_file, temp_fn])
      with open(args.po_file, 'w') as fp:
        fp.write(merged_po)
    finally:
      if os.path.exists(temp_fn):
        os.unlink(temp_fn)


if __name__ == '__main__':
  main()
