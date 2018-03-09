# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.lib import probe_function
from cros.factory.utils import process_utils


USB_SYSFS_PATH = '/sys/bus/usb/devices/usb*'


class GenericUSBHostFunction(probe_function.ProbeFunction):
  """Probe the generic USB host information."""

  def Probe(self):
    # On x86, USB hosts are PCI devices, located in parent of root USB.
    # On ARM and others, use the root device itself.
    arch = process_utils.CheckOutput('crossystem arch', shell=True)
    relpath = '.' if arch == 'arm' else '..'
    usb_bus_list = glob.glob(USB_SYSFS_PATH)
    usb_host_list = [
        os.path.abspath(os.path.join(os.path.realpath(path), relpath))
        for path in usb_bus_list]
    usb_host_list = list(set(usb_host_list))  # remove duplicated paths if any
    logging.debug('Paths of usb hosts: %s', usb_host_list)

    ret = []
    for path in usb_host_list:
      results = (function.InterpretFunction({'pci': path})() or
                 function.InterpretFunction({'usb': path})())
      if results:
        ret += results
    return ret
