#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import shell


class ExecFunctionTest(unittest.TestCase):

  def testSimpleCommand(self):
    command = 'echo "hello world"'
    func = shell.ShellFunction(command=command, key='idx')
    result = func()
    self.assertEquals(result, [{'idx': 'hello world'}])

    func = shell.ShellFunction(command=command)
    result = func()
    self.assertEquals(result, [{shell.DEFAULT_KEY: 'hello world'}])

  def testSequenceCommand(self):
    command = 'echo "hello world"; echo "second line"'
    func = shell.ShellFunction(command=command, key='idx')
    result = func()
    self.assertEquals(result, [{'idx': 'hello world\nsecond line'}])

    func = shell.ShellFunction(command=command, key='idx', split_line=True)
    result = func()
    self.assertEquals(result, [{'idx': 'hello world'},
                               {'idx': 'second line'}])

  def testFailedCommand(self):
    command = 'echo "hello world"; echo "second line"; false'
    func = shell.ShellFunction(command=command, key='idx')
    result = func()
    self.assertEquals(result, [])

  def testPipeCommand(self):
    command = 'echo "hello" | sed "s/e/a/"'
    func = shell.ShellFunction(command=command, key='idx')
    result = func()
    self.assertEquals(result, [{'idx': 'hallo'}])

  def testStderrCommand(self):
    command = 'echo "hello world"; >&2 echo "second line"'
    func = shell.ShellFunction(command=command, key='idx')
    result = func()
    self.assertEquals(result, [{'idx': 'hello world'}])


if __name__ == '__main__':
  unittest.main()
