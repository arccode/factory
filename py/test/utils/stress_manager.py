#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import contextlib
import logging
import re
import tempfile
import threading

import factory_common  # pylint: disable=W0611


class StressManagerError(Exception):
  pass


class StressManager(object):
  """Manage CPU and memory load of the system using stressapptest.

  The manager runs stressapptest to occupy a specific amount of memry and
  threads for some duration.

  Usage:
      with StressManager(dut_instance).Run(duration_secs, num_threads,
                                           memory_ratio):
        # do something under stress

  Note that the "with" block will wait until both StressManager.Run and block
  content are finished.
  """
  def __init__(self, dut):
    self._dut = dut
    self._system_info = dut.info
    self.output = None

  # TODO(stimim): If duration_secs=None, then stresstestapp should keep running
  #               until it's context is over.
  @contextlib.contextmanager
  def Run(self, duration_secs, num_threads=None, memory_ratio=0.2,
          disk_thread=False):
    assert duration_secs > 0
    assert num_threads != 0
    assert memory_ratio > 0
    assert memory_ratio < 0.9

    cpu_count = self._system_info.cpu_count or 1
    if num_threads is None:
      num_threads = cpu_count
    elif num_threads > cpu_count:
      logging.warning(
          'Only %d CPUs availible on DUT, set num_threads to %d (was %d)',
          cpu_count, cpu_count, num_threads)
      num_threads = min(cpu_count, num_threads)

    # Allow shmem access to all of memory. This is used for 32 bit access to >
    # 1.4G. Virtual address space limitation prevents directly mapping the
    # memory.
    self._dut.memory.ResizeSharedMemory()

    mem = self._system_info.memory_total_kb or (100 * 1024)
    # we will use at least 32 MB of memory
    mem_usage = max(int(mem * memory_ratio / 1024), 32)

    thread = threading.Thread(target=self._CallStressAppTest,
                              args=(duration_secs, num_threads, mem_usage,
                                    disk_thread))
    # clear output
    self.output = None

    try:
      thread.start()
      yield
    finally:
      thread.join()

    if not re.search(r'Status: PASS', self.output, re.MULTILINE):
      raise StressManagerError(self.output)

  def _CallStressAppTest(self, duration_secs, num_threads, mem_usage,
                         disk_thread):
    assert isinstance(duration_secs, int)
    assert isinstance(num_threads, int)
    assert isinstance(mem_usage, int)
    assert isinstance(disk_thread, bool)

    cmd = ['stressapptest', '-m', str(num_threads), '-M', str(mem_usage), '-s',
           str(duration_secs)]
    with tempfile.TemporaryFile() as output:
      if disk_thread:
        with self._dut.temp.TempDirectory() as tempdir:
          for disk_file in ['sat.diskthread.a', 'sat.diskthread.b']:
            cmd += ['-f', self._dut.path.join(tempdir, disk_file)]
          self._dut.Call(cmd, stdout=output)
      else:
        self._dut.Call(cmd, stdout=output)
      output.seek(0)
      self.output = output.read()

