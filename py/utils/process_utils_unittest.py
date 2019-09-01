#!/usr/bin/env python2
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import cStringIO
import logging
from logging import handlers
import os
import subprocess
import sys
import time
import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils.process_utils import CheckOutput
from cros.factory.utils.process_utils import PIPE
from cros.factory.utils.process_utils import PipeStdoutLines
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.process_utils import SpawnOutput
from cros.factory.utils.process_utils import TerminateOrKillProcess


class SpawnTest(unittest.TestCase):

  def setUp(self):
    log_entries = self.log_entries = []

    class Target(object):

      def handle(self, record):
        log_entries.append((record.levelname, record.msg % record.args))

    self.handler = handlers.MemoryHandler(capacity=0, target=Target())
    logging.getLogger().addHandler(self.handler)

    process_utils.dev_null = None

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

  def testCheckCallFunction(self):
    Spawn('exit 3', shell=True, check_call=lambda code: code == 3)
    self.assertRaises(
        subprocess.CalledProcessError,
        lambda: Spawn('exit 2', shell=True,
                      check_call=lambda code: code == 3))

  def testCheckOutput(self):
    self.assertEquals(
        'foo\n',
        Spawn('echo foo', shell=True, check_output=True).stdout_data)
    self.assertRaises(subprocess.CalledProcessError,
                      lambda: Spawn('exit 3', shell=True, check_output=True))

  def testReadStdout(self):
    process = Spawn('echo foo; echo bar; exit 3', shell=True, read_stdout=True)
    self.assertEquals('foo\nbar\n', process.stdout_data)
    self.assertEquals(['foo\n', 'bar\n'], process.stdout_lines())
    self.assertEquals(['foo', 'bar'], process.stdout_lines(strip=True))
    self.assertEquals(None, process.stderr_data)
    self.assertEquals(3, process.returncode)

  def testReadStderr(self):
    process = Spawn('(echo bar; echo foo) >& 2', shell=True, read_stderr=True)
    self.assertEquals(None, process.stdout_data)
    self.assertEquals('bar\nfoo\n', process.stderr_data)
    self.assertEquals(['bar\n', 'foo\n'], process.stderr_lines())
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

  def testIgnoreStdout(self):
    self.assertFalse(process_utils.dev_null)
    process = Spawn('echo ignored; echo foo >& 2', shell=True,
                    ignore_stdout=True, read_stderr=True)
    self.assertTrue(process_utils.dev_null)
    self.assertEquals('foo\n', process.stderr_data)

  def testIgnoreStderr(self):
    self.assertFalse(process_utils.dev_null)
    process = Spawn('echo foo; echo ignored >& 2', shell=True,
                    read_stdout=True, ignore_stderr=True)
    self.assertTrue(process_utils.dev_null)
    self.assertEquals('foo\n', process.stdout_data)

  def testOpenDevNull(self):
    self.assertFalse(process_utils.dev_null)
    dev_null = process_utils.OpenDevNull()
    self.assertEquals(os.devnull, dev_null.name)
    self.assertEquals(dev_null, process_utils.OpenDevNull())


_CMD_FOO_SUCCESS = 'echo foo; exit 0'
_CMD_FOO_FAILED = 'echo foo; exit 1'


class CheckOutputTest(unittest.TestCase):

  def testCheckOutput(self):
    self.assertEquals('foo\n', CheckOutput(_CMD_FOO_SUCCESS, shell=True))
    self.assertRaises(subprocess.CalledProcessError,
                      lambda: CheckOutput(_CMD_FOO_FAILED, shell=True))


class SpawnOutputTest(unittest.TestCase):

  def testSpawnOutput(self):
    self.assertEquals('foo\n', SpawnOutput(_CMD_FOO_SUCCESS, shell=True))
    self.assertEquals('foo\n', SpawnOutput(_CMD_FOO_FAILED, shell=True))
    self.assertRaises(subprocess.CalledProcessError,
                      lambda: SpawnOutput(_CMD_FOO_FAILED, shell=True,
                                          check_output=True))


class TerminateOrKillProcessTest(unittest.TestCase):

  def setUp(self):
    self.m = mox.Mox()
    self.m.StubOutWithMock(logging, 'info')

  def tearDown(self):
    self.m.UnsetStubs()

  def testTerminateProcess(self):
    process = Spawn(['sleep', '10'])
    logging.info('Stopping process %d', process.pid)
    logging.info('Process %d stopped', process.pid)
    self.m.ReplayAll()
    TerminateOrKillProcess(process, 2)
    self.m.VerifyAll()

  def testKillProcess(self):
    process = Spawn('trap true SIGTERM SIGKILL; sleep 10', shell=True)
    # Allow the process some time to execute and setup signal trap.
    time.sleep(1)
    logging.info('Stopping process %d', process.pid)
    logging.info('Sending SIGKILL to process %d', process.pid)
    logging.info('Process %d stopped', process.pid)
    self.m.ReplayAll()
    TerminateOrKillProcess(process, 2)
    self.m.VerifyAll()

  def testTerminateSudoProcess(self):
    process = Spawn(['sleep', '10'], sudo=True)
    logging.info('Stopping process %d', process.pid)
    spawn_msg = 'Running command: "kill %d"' % process.pid
    logging.info(spawn_msg)
    self.m.ReplayAll()
    TerminateOrKillProcess(process, sudo=True)
    self.m.VerifyAll()


class TestRedirectStdout(unittest.TestCase):
  def setUp(self):
    self.saved_stdout = sys.stdout
    self.mock_stdout = cStringIO.StringIO()
    sys.stdout = self.mock_stdout

  def tearDown(self):
    sys.stdout = self.saved_stdout

  def testRedirectStdout(self):
    print 'before'
    dummy_file = process_utils.DummyFile()
    with process_utils.RedirectStandardStreams(stdout=dummy_file):
      print 'SHOULD_NOT_OUTPUT'
    print 'after'
    self.assertEquals('before\nafter\n', self.mock_stdout.getvalue())

  def testNotRedirectStdout(self):
    print 'before'
    with process_utils.RedirectStandardStreams(stdout=None):
      print 'SHOULD_OUTPUT'
    print 'after'
    self.assertEquals('before\nSHOULD_OUTPUT\nafter\n',
                      self.mock_stdout.getvalue())

  def testRedirectAgainStdoutWithinContext(self):
    dummy_file = process_utils.DummyFile()
    with self.assertRaises(IOError):
      with process_utils.RedirectStandardStreams(stdout=dummy_file):
        sys.stdout = process_utils.DummyFile()

  def testRedirectStdoutWithinContext(self):
    dummy_file = process_utils.DummyFile()
    print 'before'
    with process_utils.RedirectStandardStreams(stdout=None):
      print 'SHOULD_OUTPUT'
      sys.stdout = dummy_file
      print 'SHOULD_NOT_OUTPUT'
    print 'after'
    self.assertEquals('before\nSHOULD_OUTPUT\n', self.mock_stdout.getvalue())


class TestPipeStdoutLines(unittest.TestCase):
  def testBasic(self):
    buf = []
    process = Spawn('echo foo', stdout=PIPE, shell=True)
    PipeStdoutLines(process, buf.append)
    self.assertEqual(0, process.returncode)
    self.assertEqual(['foo'], buf)

  def testTwoReads(self):
    buf = []
    process = Spawn(
        'echo -n foo; sleep 0.01; echo bar', stdout=PIPE, shell=True)
    PipeStdoutLines(process, buf.append)
    self.assertEqual(0, process.returncode)
    self.assertEqual(['foobar'], buf)

  def testReadStreamed(self):
    with file_utils.UnopenedTemporaryFile() as f:
      process = Spawn('echo foo\n'
                      'while [ ! -e "%s" ]; do\n'
                      '  sleep 0.01\n'
                      'done\n'
                      'echo bar' % f, stdout=PIPE, shell=True)
      buf = []
      def _Callback(line):
        buf.append(line)
        file_utils.TouchFile(f)

      PipeStdoutLines(process, _Callback)
      self.assertEqual(0, process.returncode)
      self.assertEqual(['foo', 'bar'], buf)

  def testPartialLines(self):
    buf = []
    process = Spawn(
        'echo -n "foo\nbar"\n'
        'sleep 0.01\n'
        'echo -n "baz\nwww\nvvv"\n'
        'sleep 0.01\n'
        'echo -n ^\n'
        'sleep 0.01\n'
        'echo vvv',
        stdout=PIPE,
        shell=True)
    PipeStdoutLines(process, buf.append)
    self.assertEqual(0, process.returncode)
    self.assertEqual(['foo', 'barbaz', 'www', 'vvv^vvv'], buf)

  def testStdoutClosedEarly(self):
    buf = []
    process = Spawn(
        'echo "foo"\n'
        'exec 1>&- # Close stdout\n'
        'sleep 0.1\n',
        stdout=PIPE,
        shell=True)
    PipeStdoutLines(process, buf.append)
    self.assertEqual(0, process.returncode)
    self.assertEqual(['foo'], buf)

  def testStdoutGrabbedByChild(self):
    buf = []
    process = Spawn(
        'echo "parent"\n'
        '(sleep 0.5; echo "child") &\n'
        'echo "end"\n',
        stdout=PIPE,
        ignore_stderr=True,
        shell=True)
    PipeStdoutLines(process, buf.append)
    self.assertEqual(0, process.returncode)
    self.assertEqual(['parent', 'end'], buf)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
