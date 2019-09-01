#!/usr/bin/env python2
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import tempfile
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.device import info
from cros.factory.device import memory
from cros.factory.device import temp
from cros.factory.device import types
from cros.factory.test.utils import stress_manager

# pylint: disable=protected-access
class StressManagerUnittest(unittest.TestCase):
  def setUp(self):
    self.dut = mock.Mock(spec=types.DeviceInterface)
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
    disk_thread_dir = None
    total_memory = 1024 * 1024
    max_errors = 1000

    self.dut.memory.GetTotalMemoryKB = mock.Mock(return_value=total_memory)
    self.manager._CallStressAppTest = mock.MagicMock(return_value=None)
    self.manager._CallStressAppTest.side_effect = (
        self._CallStressAppTestSideEffect)

    with self.manager.Run(
        duration_secs, num_threads, memory_ratio, disk_thread):
      pass

    mem_usage = int(memory_ratio * total_memory / 1024)
    self.manager._CallStressAppTest.assert_called_with(
        duration_secs, num_threads, mem_usage, disk_thread, disk_thread_dir,
        max_errors, None)

  def testRunForever(self):
    duration_secs = None
    num_threads = 1000
    memory_ratio = 0.5
    total_memory = 1024 * 1024
    mem_usage = int(memory_ratio * total_memory / 1024)
    disk_thread = False
    disk_thread_dir = None
    max_errors = 1000

    self.dut.memory.GetTotalMemoryKB = mock.Mock(return_value=total_memory)
    self.manager._CallStressAppTest = mock.MagicMock(
        return_value=None,
        side_effect=self._CallStressAppTestSideEffect)

    with self.manager.Run(
        duration_secs, num_threads, memory_ratio, disk_thread):
      pass

    self.manager._CallStressAppTest.assert_called_with(
        duration_secs, self.dut.info.cpu_count, mem_usage, disk_thread,
        disk_thread_dir, max_errors, None)

  def testRunForeverFail(self):
    duration_secs = None
    num_threads = 1000
    memory_ratio = 0.5
    total_memory = 1024 * 1024
    mem_usage = int(memory_ratio * total_memory / 1024)
    disk_thread = False
    disk_thread_dir = None
    max_errors = 1000

    def SideEffect(*unused_args):
      self.manager.output = 'Log: User exiting early'

    self.dut.memory.GetTotalMemoryKB = mock.Mock(return_value=total_memory)
    self.manager._CallStressAppTest = mock.MagicMock(
        return_value=None,
        side_effect=SideEffect)

    with self.assertRaises(stress_manager.StressManagerError):
      with self.manager.Run(
          duration_secs, num_threads, memory_ratio, disk_thread):
        pass

    self.manager._CallStressAppTest.assert_called_with(
        duration_secs, self.dut.info.cpu_count, mem_usage, disk_thread,
        disk_thread_dir, max_errors, None)

  def testRunForeverNoStatusOutput(self):
    duration_secs = None
    num_threads = 1000
    memory_ratio = 0.5
    total_memory = 1024 * 1024
    mem_usage = int(memory_ratio * total_memory / 1024)
    disk_thread = False
    disk_thread_dir = None
    max_errors = 1000

    def SideEffect(*unused_args):
      self.manager.output = ''

    self.dut.memory.GetTotalMemoryKB = mock.Mock(return_value=total_memory)
    self.manager._CallStressAppTest = mock.MagicMock(
        return_value=None,
        side_effect=SideEffect)

    with self.manager.Run(
        duration_secs, num_threads, memory_ratio, disk_thread):
      pass

    self.manager._CallStressAppTest.assert_called_with(
        duration_secs, self.dut.info.cpu_count, mem_usage, disk_thread,
        disk_thread_dir, max_errors, None)

  def testRunFreeMemoryOnly(self):
    duration_secs = 10
    num_threads = 4
    memory_ratio = 0.5
    disk_thread = False
    disk_thread_dir = None
    total_memory = 1024 * 1024
    free_memory = 0.5 * total_memory
    max_errors = 1000

    self.dut.memory.GetFreeMemoryKB = mock.Mock(return_value=free_memory)
    self.manager._CallStressAppTest = mock.MagicMock(return_value=None)
    self.manager._CallStressAppTest.side_effect = (
        self._CallStressAppTestSideEffect)

    with self.manager.Run(
        duration_secs, num_threads, memory_ratio, True, disk_thread):
      pass

    mem_usage = int(memory_ratio * free_memory / 1024)
    self.manager._CallStressAppTest.assert_called_with(
        duration_secs, num_threads, mem_usage, disk_thread, disk_thread_dir,
        max_errors, None)

  def _CallStressAppTestSideEffect(self, *args):
    del args  # Unused.
    self.manager.output = ('Log: User exiting early (13 seconds remaining)\n'
                           'Status: PASS')

  def testRunNotEnoughCPU(self):
    duration_secs = 10
    num_threads = 1000
    memory_ratio = 0.5
    total_memory = 1024 * 1024
    mem_usage = int(memory_ratio * total_memory / 1024)
    disk_thread = False
    disk_thread_dir = None
    max_errors = 1000

    self.dut.memory.GetTotalMemoryKB = mock.Mock(return_value=total_memory)
    self.manager._CallStressAppTest = mock.MagicMock(return_value=None)
    self.manager._CallStressAppTest.side_effect = (
        self._CallStressAppTestSideEffect)

    with self.manager.Run(
        duration_secs, num_threads, memory_ratio, disk_thread):
      pass

    self.manager._CallStressAppTest.assert_called_with(
        duration_secs, self.dut.info.cpu_count, mem_usage, disk_thread,
        disk_thread_dir, max_errors, None)

  def testRunNotEnoughMemory(self):
    duration_secs = 10
    num_threads = 1
    memory_ratio = 0.1
    mem_usage = 32
    disk_thread = False
    disk_thread_dir = None
    max_errors = 1000

    self.dut.memory.GetTotalMemoryKB = mock.Mock(return_value=100 * 1024)
    self.manager._CallStressAppTest = mock.MagicMock(return_value=None)
    self.manager._CallStressAppTest.side_effect = (
        self._CallStressAppTestSideEffect)

    with self.manager.Run(
        duration_secs, num_threads, memory_ratio, disk_thread):
      pass

    self.manager._CallStressAppTest.assert_called_with(
        duration_secs, num_threads, mem_usage, disk_thread, disk_thread_dir,
        max_errors, None)

  def testCallStressAppTest(self):
    duration_secs = 10
    num_threads = 1
    mem_usage = 32
    disk_thread = False
    disk_thread_dir = None
    max_errors = 1000

    with tempfile.NamedTemporaryFile() as output:
      stress_manager.tempfile.TemporaryFile = mock.MagicMock(
          return_value=output)
      self.manager._CallStressAppTest(duration_secs, num_threads, mem_usage,
                                      disk_thread, disk_thread_dir, max_errors,
                                      None)
      self.dut.Popen.assert_called_with(
          ['stressapptest', '--max_errors', '1000', '-m', '1', '-M', '32',
           '-s', '10'],
          stdout=output)
      self.fake_process.wait.assert_called_with()

  def testCallStressAppTestWithDiskThread(self):
    duration_secs = 10
    num_threads = 1
    mem_usage = 32
    disk_thread = True
    disk_thread_dir = None
    data_root = "/path/to/data/root"
    max_errors = 1000

    with tempfile.NamedTemporaryFile() as output:
      stress_manager.tempfile.TemporaryFile = mock.MagicMock(
          return_value=output)

      self.dut.storage.GetDataRoot = lambda: data_root
      self.dut.CheckCall = mock.MagicMock()

      self.manager._CallStressAppTest(duration_secs, num_threads, mem_usage,
                                      disk_thread, disk_thread_dir, max_errors,
                                      None)

      self.dut.CheckCall.assert_called_with(['mkdir', '-p', data_root])
      self.dut.Popen.assert_called_with(
          ['stressapptest', '--max_errors', '1000', '-m', '1', '-M', '32',
           '-s', '10', '-f', mock.ANY, '-f', mock.ANY],
          stdout=output)
      self.fake_process.wait.assert_called_with()

  def testCallStressAppTestWithDiskThreadWithDiskThreadDir(self):
    duration_secs = 10
    num_threads = 1
    mem_usage = 32
    disk_thread = True
    disk_thread_dir = '/path/to/disk_thread_dir'
    data_root = "/path/to/data/root"
    max_errors = 1234

    with tempfile.NamedTemporaryFile() as output:
      stress_manager.tempfile.TemporaryFile = mock.MagicMock(
          return_value=output)

      self.dut.storage.GetDataRoot = lambda: data_root
      self.dut.CheckCall = mock.MagicMock()

      self.manager._CallStressAppTest(duration_secs, num_threads, mem_usage,
                                      disk_thread, disk_thread_dir, max_errors,
                                      None)

      self.dut.CheckCall.assert_called_with(['mkdir', '-p', disk_thread_dir])

      self.dut.Popen.assert_called_with(
          ['stressapptest', '--max_errors', '1234', '-m', '1', '-M', '32',
           '-s', '10', '-f', mock.ANY, '-f', mock.ANY],
          stdout=output)
      self.fake_process.wait.assert_called_with()

  def testCallStressAppTestRunForever(self):
    duration_secs = None
    num_threads = 1
    mem_usage = 32
    disk_thread = False
    disk_thread_dir = None
    max_errors = 1001

    with tempfile.NamedTemporaryFile() as output:
      stress_manager.tempfile.TemporaryFile = mock.MagicMock(
          return_value=output)
      self.dut.toybox.pkill = mock.MagicMock(return_value=0)
      self.manager._CallStressAppTest(duration_secs, num_threads, mem_usage,
                                      disk_thread, disk_thread_dir, max_errors,
                                      None)
      self.dut.Popen.assert_called_with(
          ['stressapptest', '--max_errors', '1001', '-m', '1', '-M', '32',
           '-s', mock.ANY],
          stdout=output)
      self.manager.stop.wait.assert_called_with()
      self.dut.toybox.pkill.assert_called_with('stressapptest')
      self.fake_process.wait.assert_called_with()


if __name__ == '__main__':
  unittest.main()
