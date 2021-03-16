#!/usr/bin/env python3
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from io import StringIO
import logging
from logging import handlers
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils.process_utils import CalledProcessError
from cros.factory.utils.process_utils import CheckOutput
from cros.factory.utils.process_utils import CommandPipe
from cros.factory.utils.process_utils import PIPE
from cros.factory.utils.process_utils import PipeStdoutLines
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.process_utils import SpawnOutput
from cros.factory.utils.process_utils import TerminateOrKillProcess


class SpawnTest(unittest.TestCase):

  def setUp(self):
    log_entries = self.log_entries = []

    class Target:

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
    self.assertEqual('f<o>o\n', stdout)
    self.assertEqual('', stderr)
    self.assertEqual(0, process.returncode)
    self.assertEqual([('INFO',
                       '''Running command: "echo \'f<o>o\'"''')],
                     self.log_entries)

  def testShell(self):
    process = Spawn('echo foo', shell=True,
                    stdout=PIPE, stderr=PIPE, log=True)
    stdout, stderr = process.communicate()
    self.assertEqual('foo\n', stdout)
    self.assertEqual('', stderr)
    self.assertEqual(0, process.returncode)
    self.assertEqual([('INFO', 'Running command: "echo foo"')],
                     self.log_entries)

  def testCall(self):
    process = Spawn('echo blah; exit 3', shell=True, call=True)
    self.assertEqual(3, process.returncode)
    # stdout/stderr are not trapped
    self.assertEqual(None, process.stdout)
    self.assertEqual(None, process.stdout_data)

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
    self.assertEqual([('INFO', 'Running command: "exit 3"'),
                      ('ERROR', 'Exit code 3 from command: "exit 3"')],
                     self.log_entries)

  def testCheckCallFunction(self):
    Spawn('exit 3', shell=True, check_call=lambda code: code == 3)
    self.assertRaises(
        subprocess.CalledProcessError,
        lambda: Spawn('exit 2', shell=True,
                      check_call=lambda code: code == 3))

  def testCheckOutput(self):
    self.assertEqual(
        'foo\n',
        Spawn('echo foo', shell=True, check_output=True).stdout_data)
    self.assertRaises(subprocess.CalledProcessError,
                      lambda: Spawn('exit 3', shell=True, check_output=True))

  def testReadStdout(self):
    process = Spawn('echo foo; echo bar; exit 3', shell=True, read_stdout=True)
    self.assertEqual('foo\nbar\n', process.stdout_data)
    self.assertEqual(['foo\n', 'bar\n'], process.stdout_lines())
    self.assertEqual(['foo', 'bar'], process.stdout_lines(strip=True))
    self.assertEqual(None, process.stderr_data)
    self.assertEqual(3, process.returncode)

  def testReadStderr(self):
    process = Spawn('(echo bar; echo foo) >& 2', shell=True, read_stderr=True)
    self.assertEqual(None, process.stdout_data)
    self.assertEqual('bar\nfoo\n', process.stderr_data)
    self.assertEqual(['bar\n', 'foo\n'], process.stderr_lines())
    self.assertEqual(0, process.returncode)

  def testReadStdoutAndStderr(self):
    process = Spawn('echo foo; echo bar >& 2', shell=True,
                    read_stdout=True, read_stderr=True)
    self.assertEqual('foo\n', process.stdout_data)
    self.assertEqual('bar\n', process.stderr_data)
    self.assertEqual(('foo\n', 'bar\n'), process.communicate())
    self.assertEqual(0, process.returncode)

  def testLogStderrOnError(self):
    Spawn('echo foo >& 2', shell=True, log_stderr_on_error=True)
    self.assertFalse(self.log_entries)

    Spawn('echo foo >& 2; exit 3', shell=True, log_stderr_on_error=True)
    self.assertEqual(
        [('ERROR',
          'Exit code 3 from command: "echo foo >& 2; exit 3"; '
          'stderr: """\nfoo\n\n"""')],
        self.log_entries)

  def testIgnoreStdout(self):
    process = Spawn('echo ignored; echo foo >& 2', shell=True,
                    ignore_stdout=True, read_stderr=True)
    self.assertEqual('foo\n', process.stderr_data)

  def testIgnoreStderr(self):
    process = Spawn('echo foo; echo ignored >& 2', shell=True,
                    read_stdout=True, ignore_stderr=True)
    self.assertEqual('foo\n', process.stdout_data)

  def testTimeout(self):
    with self.assertRaises(process_utils.TimeoutExpired):
      Spawn(['sleep', '10'], check_call=True, timeout=1)
    with self.assertRaises(process_utils.TimeoutExpired):
      Spawn(['sleep', '10'], timeout=1)


_CMD_FOO_SUCCESS = 'echo foo; exit 0'
_CMD_FOO_FAILED = 'echo foo; exit 1'


class CheckOutputTest(unittest.TestCase):

  def testCheckOutput(self):
    self.assertEqual('foo\n', CheckOutput(_CMD_FOO_SUCCESS, shell=True))
    self.assertRaises(subprocess.CalledProcessError,
                      lambda: CheckOutput(_CMD_FOO_FAILED, shell=True))


class SpawnOutputTest(unittest.TestCase):

  def testSpawnOutput(self):
    self.assertEqual('foo\n', SpawnOutput(_CMD_FOO_SUCCESS, shell=True))
    self.assertEqual('foo\n', SpawnOutput(_CMD_FOO_FAILED, shell=True))
    self.assertRaises(subprocess.CalledProcessError,
                      lambda: SpawnOutput(_CMD_FOO_FAILED, shell=True,
                                          check_output=True))


class CommandPipeTest(unittest.TestCase):

  def setUp(self):
    self._bin = file_utils.CreateTemporaryFile()
    with open(self._bin, 'wb') as f:
      f.write(b'\x00\x01\x02\x03')

  def tearDown(self):
    os.unlink(self._bin)

  def testCommandPipe(self):
    p = CommandPipe().Pipe(['echo', '-n',
                            '1234']).Pipe(['cat', '-']).Pipe(['cat', '-'])
    self.assertEqual(('1234', ''), p.Communicate())
    self.assertEqual('1234', p.stdout_data)

    p = CommandPipe().Pipe('echo -n 1234 >&2', shell=True)
    self.assertEqual(('', '1234'), p.Communicate())
    self.assertEqual('1234', p.stderr_data)

    p = CommandPipe(encoding=None).Pipe(['cat', self._bin]).Pipe(
        ['cat', '-']).Pipe(['cat', '-'])
    self.assertEqual((b'\x00\x01\x02\x03', b''), p.Communicate())
    self.assertEqual(b'\x00\x01\x02\x03', p.stdout_data)

    # Check CommandPipe auto fulfill
    self.assertEqual('1234\n', CommandPipe().Pipe(['echo', '1234']).stdout_data)
    self.assertEqual(
        '1234\n',
        CommandPipe().Pipe('echo 1234 >&2', shell=True).stderr_data)

    # Check if this doesn't raise.
    CommandPipe(check=False).Pipe(['echo', '1234']).Pipe(['false']).Pipe(
        ['cat', '-']).Communicate()

    with self.assertRaises(CalledProcessError):
      CommandPipe().Pipe(['echo', '1234']).Pipe(['false']).Pipe(
          ['cat', '-']).Communicate()

    with self.assertRaises(CalledProcessError):
      CommandPipe().Pipe(['echo', '1234']).Pipe(['cat', '-']).Pipe(
          ['false']).Communicate()

    with self.assertRaises(CalledProcessError):
      CommandPipe().Pipe(['false']).Pipe(['echo', '1234']).Pipe(
          ['cat', '-']).Communicate()

    with self.assertRaises(CalledProcessError) as cm:
      p = CommandPipe()
      p.Pipe('echo -n 1234; echo -n 5678 >&2; false;', shell=True)
      p.Pipe(['cat', '-']).Pipe(['cat', '-'])
      p.Communicate()
    self.assertEqual(cm.exception.stdout, None)  # The stdout is piped to `cat`.
    self.assertEqual(cm.exception.stderr, '5678')

    with self.assertRaises(CalledProcessError) as cm:
      p = CommandPipe().Pipe('echo -n 1234; echo -n 5678 >&2; false;',
                             shell=True)
      p.Communicate()
    self.assertEqual(cm.exception.stdout, '1234')
    self.assertEqual(cm.exception.stderr, '5678')

    p = CommandPipe().Pipe('echo $MY_ENV', shell=True, env={'MY_ENV': '1234'})
    self.assertEqual(('1234\n', ''), p.Communicate())

    # dd will fail due to SIGPIPE error.
    p = CommandPipe(check=False).Pipe(['dd', 'if=/dev/zero']).Pipe(
        ['xxd', '-p']).Pipe(['head', '-n2'])
    self.assertEqual((('0' * 60 + '\n') * 2, ''), p.Communicate())

    with self.assertRaises(ValueError):
      CommandPipe().Communicate()
    with self.assertRaises(ValueError):
      p = CommandPipe().Pipe(['echo', '1234'])
      p.Communicate()
      p.Pipe(['echo', '5678'])  # Pipe after Communicate


class TerminateOrKillProcessTest(unittest.TestCase):

  def DoTest(self, logging_debug_mock, is_sudo, is_trap):
    if is_trap:
      process = Spawn('trap true SIGTERM SIGKILL; sleep 10', shell=True,
                      sudo=is_sudo)
      # Allow the process some time to execute and setup signal trap.
      time.sleep(1)
    else:
      process = Spawn(['sleep', '10'], sudo=is_sudo)

    def AssertTerminate(need_kill):
      expected = [
          mock.call('Stopping process %d.', process.pid),
          mock.call('Cannot terminate, sending SIGKILL to process %d.',
                    process.pid),
          mock.call('Process %d stopped.', process.pid),
      ]
      if not need_kill:
        expected.pop(-2)

      self.assertEqual(logging_debug_mock.call_args_list, expected)
      logging_debug_mock.reset_mock()

    TerminateOrKillProcess(process, 1, sudo=is_sudo)
    AssertTerminate(need_kill=is_trap)

    # Make sure it won't raise exceptions for a process which has completed.
    TerminateOrKillProcess(process, 1, sudo=is_sudo)
    AssertTerminate(need_kill=False)

  @mock.patch('logging.debug')
  def testTerminateProcess(self, logging_debug_mock):
    self.DoTest(logging_debug_mock, is_sudo=False, is_trap=False)

  @mock.patch('logging.debug')
  def testKillProcess(self, logging_debug_mock):
    self.DoTest(logging_debug_mock, is_sudo=False, is_trap=True)

  @mock.patch('logging.debug')
  def testTerminateSudoProcess(self, logging_debug_mock):
    self.DoTest(logging_debug_mock, is_sudo=True, is_trap=False)

  @mock.patch('logging.debug')
  def testKillSudoProcess(self, logging_debug_mock):
    self.DoTest(logging_debug_mock, is_sudo=True, is_trap=True)


class TestRedirectStdout(unittest.TestCase):
  def setUp(self):
    self.saved_stdout = sys.stdout
    self.mock_stdout = StringIO()
    sys.stdout = self.mock_stdout

  def tearDown(self):
    sys.stdout = self.saved_stdout

  def testRedirectStdout(self):
    print('before')
    dummy_file = process_utils.DummyFile()
    with process_utils.RedirectStandardStreams(stdout=dummy_file):
      print('SHOULD_NOT_OUTPUT')
    print('after')
    self.assertEqual('before\nafter\n', self.mock_stdout.getvalue())

  def testNotRedirectStdout(self):
    print('before')
    with process_utils.RedirectStandardStreams(stdout=None):
      print('SHOULD_OUTPUT')
    print('after')
    self.assertEqual('before\nSHOULD_OUTPUT\nafter\n',
                     self.mock_stdout.getvalue())

  def testRedirectAgainStdoutWithinContext(self):
    dummy_file = process_utils.DummyFile()
    with self.assertRaises(IOError):
      with process_utils.RedirectStandardStreams(stdout=dummy_file):
        sys.stdout = process_utils.DummyFile()

  def testRedirectStdoutWithinContext(self):
    dummy_file = process_utils.DummyFile()
    print('before')
    with process_utils.RedirectStandardStreams(stdout=None):
      print('SHOULD_OUTPUT')
      sys.stdout = dummy_file
      print('SHOULD_NOT_OUTPUT')
    print('after')
    self.assertEqual('before\nSHOULD_OUTPUT\n', self.mock_stdout.getvalue())


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
