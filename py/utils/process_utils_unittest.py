#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import subprocess
import unittest
from logging import handlers

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn, PIPE


class SpawnTest(unittest.TestCase):
  def setUp(self):
    log_entries = self.log_entries = []

    class Target(object):
      def handle(self, record):
        log_entries.append((record.levelname, record.msg % record.args))

    self.handler = handlers.MemoryHandler(capacity=0, target=Target())
    logging.getLogger().addHandler(self.handler)

  def tearDown(self):
    logging.getLogger().removeHandler(self.handler)

  def testNoShell(self):
    process = Spawn(['echo', 'f<o>o'],
                    stdout=PIPE, stderr=PIPE,
                    log=True)
    stdout, stderr = process.communicate()
    self.assertEquals('f<o>o\n', stdout)
    self.assertEquals('', stderr)
    self.assertEquals(0, process.returncode)
    self.assertEquals([('INFO',
                        '''Running command: "echo \'f<o>o\'"''')],
                      self.log_entries)

  def testShell(self):
    process = Spawn('echo foo', shell=True,
                    stdout=PIPE, stderr=PIPE, log=True)
    stdout, stderr = process.communicate()
    self.assertEquals('foo\n', stdout)
    self.assertEquals('', stderr)
    self.assertEquals(0, process.returncode)
    self.assertEquals([('INFO', 'Running command: "echo foo"')],
                      self.log_entries)

  def testCall(self):
    process = Spawn('echo blah; exit 3', shell=True, call=True)
    self.assertEquals(3, process.returncode)
    # stdout/stderr are not trapped
    self.assertEquals(None, process.stdout)
    self.assertEquals(None, process.stdout_data)

    # Would cause a bad buffering situation.
    self.assertRaises(ValueError,
                      lambda: Spawn('echo', call=True, stdout=PIPE))
    self.assertRaises(ValueError,
                      lambda: Spawn('echo', call=True, stderr=PIPE))

  def testCheckCall(self):
    Spawn('exit 0', shell=True, check_call=True)
    self.assertRaises(subprocess.CalledProcessError,
                      lambda: Spawn('exit 3', shell=True, check_call=True))

    self.assertFalse(self.log_entries)
    self.assertRaises(
        subprocess.CalledProcessError,
        lambda: Spawn('exit 3', shell=True, check_call=True, log=True))
    self.assertEquals([('INFO', 'Running command: "exit 3"'),
                       ('ERROR', 'Exit code 3 from command: "exit 3"')],
                      self.log_entries)

  def testCheckOutput(self):
    self.assertEquals(
        'foo\n',
        Spawn('echo foo', shell=True, check_output=True).stdout_data)
    self.assertRaises(subprocess.CalledProcessError,
                      lambda: Spawn('exit 3', shell=True, check_output=True))

  def testReadStdout(self):
    process = Spawn('echo foo; exit 3', shell=True, read_stdout=True)
    self.assertEquals('foo\n', process.stdout_data)
    self.assertEquals(None, process.stderr_data)
    self.assertEquals(3, process.returncode)

  def testReadStderr(self):
    process = Spawn('echo bar >& 2', shell=True, read_stderr=True)
    self.assertEquals(None, process.stdout_data)
    self.assertEquals('bar\n', process.stderr_data)
    self.assertEquals(0, process.returncode)

  def testReadStdoutAndStderr(self):
    process = Spawn('echo foo; echo bar >& 2', shell=True,
                    read_stdout=True, read_stderr=True)
    self.assertEquals('foo\n', process.stdout_data)
    self.assertEquals('bar\n', process.stderr_data)
    self.assertEquals(('foo\n', 'bar\n'), process.communicate())
    self.assertEquals(0, process.returncode)

  def testLogStderrOnError(self):
    Spawn('echo foo >& 2', shell=True, log_stderr_on_error=True)
    self.assertFalse(self.log_entries)

    Spawn('echo foo >& 2; exit 3', shell=True, log_stderr_on_error=True)
    self.assertEquals(
        [('ERROR',
          'Exit code 3 from command: "echo foo >& 2; exit 3"; '
          'stderr: """\nfoo\n\n"""')],
        self.log_entries)

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
