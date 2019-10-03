# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os

from cros.factory.probe import function
from cros.factory.probe.lib import cached_probe_function
from cros.factory.utils import process_utils


USB_SYSFS_PATH = '/sys/bus/usb/devices/usb*'


class GenericUSBHostFunction(cached_probe_function.GlobPathCachedProbeFunction):
  """Probe the generic USB host information."""
  GLOB_PATH = '/sys/bus/usb/devices/usb*'

  _DEV_RELPATH = None

  @classmethod
  def ProbeDevice(cls, dir_path):
    if cls._DEV_RELPATH is None:
      # On x86, USB hosts are PCI devices, located in parent of root USB.
      # On ARM and others, use the root device itself.
      arch = process_utils.CheckOutput('crossystem arch', shell=True)
      cls._DEV_RELPATH = '.' if arch == 'arm' else '..'

    path = os.path.abspath(
        os.path.realpath(os.path.join(dir_path, cls._DEV_RELPATH)))
    logging.debug('USB root hub sysfs path: %s', path)

    result = (function.InterpretFunction({'pci': path})() or
              function.InterpretFunction({'usb': path})())

    # Above functions shouldn't return more than one probed component.
    assert len(result) <= 1

    return result[0] if result else function.NOTHING
