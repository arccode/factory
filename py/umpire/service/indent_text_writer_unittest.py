#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.service import indent_text_writer


class IndentTextWriterTest(unittest.TestCase):

  def testIndentDefault(self):
    w = indent_text_writer.IndentTextWriter()
    self.assertEqual('', w.Flush())
    w.Write('line 1')
    self.assertEqual('line 1', w.Flush())
    w.Write('line 1')
    w.Write('line 2')
    self.assertEqual('line 1\nline 2', w.Flush())

    w.Write('line 1')
    w.IncIndent()
    w.Write('indent line 2')
    w.Write('indent line 3')
    w.DecIndent()
    w.Write('line 4')
    self.assertEqual(
        'line 1\n'
        '  indent line 2\n'
        '  indent line 3\n'
        'line 4',
        w.Flush())

  def testCustomIndent(self):
    w = indent_text_writer.IndentTextWriter(indent=2, indent_space=4)
    w.Write('line 1')
    self.assertEqual('  line 1', w.Flush())
    w.Write('line 1')
    w.Write('line 2')
    self.assertEqual('  line 1\n  line 2', w.Flush())

    w.Write('line 1')
    w.IncIndent()
    w.Write('indent line 2')
    w.Write('indent line 3')
    w.DecIndent()
    w.Write('line 4')
    self.assertEqual(
        '\n'.join(['  line 1',
                   '      indent line 2',
                   '      indent line 3',
                   '  line 4']),
        w.Flush())

  def testNoIndentFirstLine(self):
    w = indent_text_writer.IndentTextWriter(indent_first_line=False)
    w.IncIndent()
    w.Write('first line')
    w.Write('second line')
    self.assertEqual(
        'first line\n  second line',
        w.Flush())

  def testEnterBlock(self):
    w = indent_text_writer.IndentTextWriter()
    w.Write('before block')
    w.EnterBlock('{}')
    w.Write('block 1')
    w.EnterBlock('()')
    w.Write('inner block 1')
    w.Write('inner block 2')
    w.ExitBlock()
    w.Write('block 2')
    w.ExitBlock()
    w.Write('after block')
    self.assertEqual(
        '\n'.join(['before block',
                   '{',
                   '  block 1',
                   '  (',
                   '    inner block 1',
                   '    inner block 2',
                   '  )',
                   '  block 2',
                   '}',
                   'after block']),
        w.Flush())


if __name__ == '__main__':
  unittest.main()
