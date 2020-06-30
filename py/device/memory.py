# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""System module for memory."""

import pipes

from cros.factory.device import device_types


class BaseMemory(device_types.DeviceComponent):
  """Abstract class for memory component."""

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

  def ResizeSharedMemory(self, size='100%'):
    """See BaseMemory.ResizeSharedMemory."""
    self._device.CheckCall(
        'mount -o remount,size=%s /dev/shm' % pipes.quote(size))

  def GetTotalMemoryKB(self):
    """Gets total memory of system in kB"""
    return self._device.toybox.free('k').mem_total

  def GetFreeMemoryKB(self):
    """Gets free memory of system in kB"""
    return self._device.toybox.free('k').mem_max_free


class AndroidMemory(LinuxMemory):
  """Implementation of BaseMemory on Android system."""

  def ResizeSharedMemory(self, size='100%'):
    """See BaseMemory.ResizeSharedMemory."""
    # Android uses ashmem and does not have /dev/shm.
    # TODO(phoenixshen): Stressapptest on Android uses memalign/mmap to
    # allocate large blocks instead of using shared memory.
    # So we don't need to resize ashmem for stressapptest.
    # Implement this when we really need it.
