#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mock
import os
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import board
from cros.factory.test.dut import memory
from cros.factory.test.dut import info
from cros.factory.test.dut import temp
from cros.factory.test.utils import stress_manager

# pylint: disable=W0212
class StressManagerUnittest(unittest.TestCase):
  def setUp(self):
    self.dut = mock.Mock(spec=board.DUTBoard)
    self.dut.memory = mock.Mock(spec=memory.LinuxMemory)
    self.dut.info = mock.Mock(spec=info.SystemInfo)
    self.dut.temp = temp.DummyTemporaryFiles(self.dut)
    self.dut.path = os.path

    self.dut.info.cpu_count = 8

    self.fake_process = mock.MagicMock()
    self.dut.Popen = mock.MagicMock(return_value=self.fake_process)

    self.manager = stress_manager.StressManager(self.dut)
    self.manager.stop = mock.MagicMock()

  def testRun(self):
    duration_secs = 10
    num_threads = 4
    memory_ratio = 0.5
    disk_thread = False
    total_memory = 1024 * 1024

    self.dut.memory.GetTotalMemoryKB = mock.Mock(return_value=total_memory)
    self.manager._CallStressAppTest = mock.MagicMock(return_value=None)
    self.manager._CallStressAppTest.side_effect = self._CallStressAppTestSideEffect

    with self.manager.Run(
        duration_secs, num_threads, memory_ratio, disk_thread):
      pass

    mem_usage = int(memory_ratio * total_memory / 1024)
    self.manager._CallStressAppTest.assert_called_with(
        duration_secs, num_threads, mem_usage, disk_thread)

  def testRunFreeMemoryOnly(self):
    duration_secs = 10
    num_threads = 4
    memory_ratio = 0.5
    disk_thread = False
    total_memory = 1024 * 1024
    free_memory = 0.5 * total_memory

    self.dut.memory.GetFreeMemoryKB = mock.Mock(return_value=free_memory)
    self.manager._CallStressAppTest = mock.MagicMock(return_value=None)
    self.manager._CallStressAppTest.side_effect = self._CallStressAppTestSideEffect

    with self.manager.Run(
        duration_secs, num_threads, memory_ratio, True, disk_thread):
      pass

    mem_usage = int(memory_ratio * free_memory / 1024)
    self.manager._CallStressAppTest.assert_called_with(
        duration_secs, num_threads, mem_usage, disk_thread)


  def _CallStressAppTestSideEffect(self, *unused_args):
    self.manager.output = 'Status: PASS'

  def testRunNotEnoughCPU(self):
    duration_secs = 10
    num_threads = 1000
    memory_ratio = 0.5
    total_memory = 1024 * 1024
    mem_usage = int(memory_ratio * total_memory / 1024)
    disk_thread = False

    self.dut.memory.GetTotalMemoryKB = mock.Mock(return_value=total_memory)
    self.manager._CallStressAppTest = mock.MagicMock(return_value=None)
    self.manager._CallStressAppTest.side_effect = self._CallStressAppTestSideEffect

    with self.manager.Run(
        duration_secs, num_threads, memory_ratio, disk_thread):
      pass

    self.manager._CallStressAppTest.assert_called_with(
        duration_secs, self.dut.info.cpu_count, mem_usage, disk_thread)

  def testRunNotEnoughMemory(self):
    duration_secs = 10
    num_threads = 1
    memory_ratio = 0.1
    mem_usage = 32
    disk_thread = False

    self.dut.memory.GetTotalMemoryKB = mock.Mock(return_value=100 * 1024)
    self.manager._CallStressAppTest = mock.MagicMock(return_value=None)
    self.manager._CallStressAppTest.side_effect = self._CallStressAppTestSideEffect

    with self.manager.Run(
        duration_secs, num_threads, memory_ratio, disk_thread):
      pass

    self.manager._CallStressAppTest.assert_called_with(
        duration_secs, num_threads, mem_usage, disk_thread)

  def testCallStressAppTest(self):
    duration_secs = 10
    num_threads = 1
    mem_usage = 32
    disk_thread = False

    with tempfile.NamedTemporaryFile() as output:
      stress_manager.tempfile.TemporaryFile = mock.MagicMock(
          return_value=output)
      self.manager._CallStressAppTest(duration_secs, num_threads, mem_usage,
                                      disk_thread)
      self.dut.Popen.assert_called_with(
          ['stressapptest', '-m', '1', '-M', '32', '-s', '10'],
          stdout=output)
      self.fake_process.wait.assert_called_with()

  def testCallStressAppTestWithDiskThread(self):
    duration_secs = 10
    num_threads = 1
    mem_usage = 32
    disk_thread = True

    with tempfile.NamedTemporaryFile() as output:
      stress_manager.tempfile.TemporaryFile = mock.MagicMock(
          return_value=output)
      self.manager._CallStressAppTest(duration_secs, num_threads, mem_usage,
                                      disk_thread)
      self.dut.Popen.assert_called_with(
          ['stressapptest', '-m', '1', '-M', '32', '-s', '10', '-f', mock.ANY,
           '-f', mock.ANY],
          stdout=output)
      self.fake_process.wait.assert_called_with()

  def testCallStressAppTestRunForever(self):
    duration_secs = None
    num_threads = 1
    mem_usage = 32
    disk_thread = False

    with tempfile.NamedTemporaryFile() as output:
      stress_manager.tempfile.TemporaryFile = mock.MagicMock(
          return_value=output)
      self.manager._CallStressAppTest(duration_secs, num_threads, mem_usage,
                                      disk_thread)
      self.dut.Popen.assert_called_with(
          ['stressapptest', '-m', '1', '-M', '32', '-s', mock.ANY],
          stdout=output)
      self.manager.stop.wait.assert_called_with()
      self.dut.Call.assert_called_with(['killall', 'stressapptest'])
      self.fake_process.wait.assert_called_with()


if __name__ == '__main__':
  unittest.main()
