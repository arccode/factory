# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import division

import contextlib
import logging
import re
import tempfile
import threading


DEFAULT_MAX_ERRORS = 1000


class StressManagerError(Exception):
  pass


class StressManager:
  """Manage CPU and memory load of the system using stressapptest.

  The manager runs stressapptest to occupy a specific amount of memory and
  threads for some duration.

  Usage:
      with StressManager(dut_instance).Run(duration_secs, num_threads,
                                           memory_ratio):
        # do something under stress

  Note that the "with" block will wait until both StressManager.Run and block
  content are finished.
  """

  def __init__(self, dut):
    """Constructor of StressManager

    Args:
      :type dut: cros.factory.device.device_types.DeviceInterface
    """
    self._dut = dut
    self._system_info = dut.info
    self.output = None
    self.stop = threading.Event()

  @contextlib.contextmanager
  def Run(self, duration_secs=None, num_threads=None, memory_ratio=0.2,
          free_memory_only=False, disk_thread=False, disk_thread_dir=None,
          max_errors=DEFAULT_MAX_ERRORS, taskset_args=None):
    """Runs stressapptest.

    Runs stressapptest to occupy a specific amount of memory and threads for
    some duration. If duration_secs is None, it will run until the context is
    over.

    Args:
      duration_secs: Number of seconds to execute stressapptest.
      num_threads: Number of thread, can either be None (use the number of CPU
          cores), negative number -k (use (#cpu - k) threads), or positive
          number k (use k threads).
      memory_ratio: Ratio of memory to be used for stressapptest.
      free_memory_only: Only use free memory for test. If set to True, only
          memory_ratio * free_memory is used for stressapptest.
      disk_thread: stress disk using -f argument of stressapptest.
      disk_thread_dir: directory of disk thread file will be placed.
      taskset_args: Argument to taskset to control the CPU affinity of
          stressapptest. stressapptest would be run by taskset when this is not
          None.

    Raise:
      StressManagerError when execution fails.
    """

    assert duration_secs is None or duration_secs > 0
    assert num_threads != 0
    assert memory_ratio > 0
    assert memory_ratio <= (1 if free_memory_only else 0.9)

    cpu_count = self._system_info.cpu_count or 1
    if num_threads is None:
      num_threads = cpu_count
    elif num_threads < 0:
      if -1 * num_threads >= cpu_count:
        logging.warning(
            'Only %d CPUs availible on DUT, set num_threads to 1 (was %d)',
            cpu_count, num_threads)
        num_threads = 1
      else:
        num_threads += cpu_count
    elif num_threads > cpu_count:
      logging.warning(
          'Only %d CPUs availible on DUT, set num_threads to %d (was %d)',
          cpu_count, cpu_count, num_threads)
      num_threads = min(cpu_count, num_threads)

    # Allow shmem access to all of memory. This is used for 32 bit access to >
    # 1.4G. Virtual address space limitation prevents directly mapping the
    # memory.
    self._dut.memory.ResizeSharedMemory()

    if free_memory_only:
      mem = self._dut.memory.GetFreeMemoryKB()
    else:
      mem = self._dut.memory.GetTotalMemoryKB()

    # we will use at least 32 MB of memory
    mem_usage = max(int(mem * memory_ratio / 1024), 32)

    thread = threading.Thread(
        target=self._CallStressAppTest,
        args=(duration_secs, num_threads, mem_usage, disk_thread,
              disk_thread_dir, max_errors, taskset_args))
    # clear output
    self.output = None
    self.stop.clear()

    try:
      thread.start()
      yield
    finally:
      if duration_secs is None:
        self.stop.set()
      thread.join()

    # If stressapptest get killed before its initialization fully done, it
    # will not output the status lines. This case should consider as success.
    if duration_secs is None and not re.search(r'Log: User exiting early',
                                               self.output, re.MULTILINE):
      return

    if not re.search(r'Status: PASS', self.output, re.MULTILINE):
      raise StressManagerError(self.output)

  def _CallStressAppTest(self, duration_secs, num_threads, mem_usage,
                         disk_thread, disk_thread_dir, max_errors,
                         taskset_args):
    assert isinstance(duration_secs, int) or duration_secs is None
    assert isinstance(num_threads, int)
    assert isinstance(mem_usage, int)
    assert isinstance(disk_thread, bool)
    assert disk_thread_dir is None or isinstance(disk_thread_dir, str)
    assert isinstance(taskset_args, list) or taskset_args is None

    cmd = []
    if taskset_args is not None:
      cmd.append('taskset')
      cmd.extend(taskset_args)
    cmd.extend([
        'stressapptest', '--max_errors',
        str(max_errors), '-m',
        str(num_threads), '-M',
        str(mem_usage), '-s',
        str(duration_secs if duration_secs is not None else 10 ** 8)
    ])
    with tempfile.TemporaryFile('w+') as output:
      if disk_thread:
        if not disk_thread_dir:
          disk_thread_dir = self._dut.storage.GetDataRoot()

        self._dut.CheckCall(['mkdir', '-p', disk_thread_dir])

        for disk_file in ['sat.diskthread.a', 'sat.diskthread.b']:
          cmd += ['-f', self._dut.path.join(disk_thread_dir, disk_file)]
      logging.info('Running %r', cmd)
      process = self._dut.Popen(cmd, stdout=output)

      if duration_secs is None:
        self.stop.wait()
        self._dut.toybox.pkill('stressapptest')
      process.wait()
      output.seek(0)
      self.output = output.read()


class DummyStressManager:
  """A stress manager with no load."""
  def __init__(self, *args, **kwargs):
    pass

  @contextlib.contextmanager
  def Run(self, *args, **kwargs):
    del args, kwargs  # Unused.
    yield
