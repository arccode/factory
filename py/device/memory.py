# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import pipes

import factory_common  # pylint: disable=W0611
from cros.factory.device import component


"""System module for memory."""


class BaseMemory(component.DeviceComponent):
  """Abstract class for memory component."""

  def __init__(self, dut):
    super(BaseMemory, self).__init__(dut)

  def ResizeSharedMemory(self, size='100%'):
    """Override maximum size of shared memory.

    Args:
      size: Maximum size of the shared memory, given in bytes, or with a
          suffix '%' indicates the percentage of physical RAM.
          See mount(8) manual page for more information.

    Raises:
      Exception if failed.
    """
    raise NotImplementedError


class LinuxMemory(BaseMemory):
  """Implementation of BaseMemory on Linux system."""

  def __init__(self, dut):
    super(LinuxMemory, self).__init__(dut)

  def ResizeSharedMemory(self, size='100%'):
    """See BaseMemory.ResizeSharedMemory."""
    self._dut.CheckCall('mount -o remount,size=%s /dev/shm' % pipes.quote(size))

  def GetTotalMemoryKB(self):
    """Gets total memory of system in kB"""
    return self._dut.toybox.free('k').mem_total

  def GetFreeMemoryKB(self):
    """Gets free memory of system in kB"""
    return self._dut.toybox.free('k').mem_max_free


class AndroidMemory(LinuxMemory):
  """Implementation of BaseMemory on Android system."""

  def __init__(self, dut):
    super(AndroidMemory, self).__init__(dut)

  def ResizeSharedMemory(self, size='100%'):
    """See BaseMemory.ResizeSharedMemory."""
    # Android uses ashmem and does not have /dev/shm.
    # TODO(phoenixshen): Stressapptest on Android uses memalign/mmap to
    # allocate large blocks instead of using shared memory.
    # So we don't need to resize ashmem for stressapptest.
    # Implement this when we really need it.
    pass
