# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


# DESCRIPTION :
#
# Factory test for USB ports.  The test checks USB ports are functional by
# requiring that an USB device be plugged in and unplugged from the number of
# ports specified.


import logging
import os

from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test.utils import media_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils


class USBTest(test_case.TestCase):
  ARGS = [
      Arg('expected_paths', str, 'USB device path', None),
      Arg('num_usb_ports', int, 'number of USB port', None),
      Arg('num_usb2_ports', int, 'number of USB 2.0 ports', None),
      Arg('num_usb3_ports', int, 'number of USB 3.0 ports', None)
  ]

  def setUp(self):
    self._expected_paths = self.args.expected_paths
    self._num_usb_ports = self.args.num_usb_ports
    self._num_usb2_ports = self.args.num_usb2_ports
    self._num_usb3_ports = self.args.num_usb3_ports

    self.assertTrue((self._num_usb_ports and self._num_usb_ports > 0) or
                    (self._num_usb2_ports and self._num_usb2_ports > 0) or
                    (self._num_usb3_ports and self._num_usb3_ports > 0),
                    'USB port count not specified.')

    if not self._num_usb_ports:
      self._num_usb_ports = (self._num_usb2_ports or 0) + (
          self._num_usb3_ports or 0)

    self._seen_usb2_paths = set()
    self._seen_usb3_paths = set()

    self.monitor = media_utils.MediaMonitor('usb', 'usb_device')

    if self._expected_paths:
      for path in self._expected_paths:
        if os.path.exists(path):
          self.RecordPath(path)

    self.ui.ToggleTemplateClass('font-large', True)
    self.SetMessage(self._num_usb_ports)

  def SetMessage(self, num_usb_ports):
    self.ui.SetState(
        _('Plug device into each USB port, {num_usb_ports} to go...',
          num_usb_ports=num_usb_ports))

  def RecordPath(self, sys_path):
    bus_path = os.path.dirname(sys_path)
    bus_ver_path = os.path.join(bus_path, 'version')
    bus_version = int(float(file_utils.ReadFile(bus_ver_path).strip()))

    if bus_version == 2:
      self._seen_usb2_paths.add(sys_path)
    elif bus_version == 3:
      self._seen_usb3_paths.add(sys_path)
    else:
      logging.warning('usb event for unknown bus version: %r', bus_version)
      return

    usb2_count = len(self._seen_usb2_paths)
    usb3_count = len(self._seen_usb3_paths)
    total_count = usb2_count + usb3_count

    finished = True
    if self._num_usb_ports:
      finished &= total_count >= self._num_usb_ports
    if self._num_usb2_ports:
      finished &= usb2_count >= self._num_usb2_ports
    if self._num_usb3_ports:
      finished &= usb3_count >= self._num_usb3_ports

    if finished:
      self.PassTask()
    else:
      self.SetMessage(self._num_usb_ports - total_count)

  def _Callback(self, device):
    self.RecordPath(device.sys_path)

  def runTest(self):
    callback = self.event_loop.CatchException(self._Callback)
    self.monitor.Start(on_insert=callback, on_remove=callback)
    self.WaitTaskEnd()

  def tearDown(self):
    self.monitor.Stop()
