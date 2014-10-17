# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


# DESCRIPTION :
#
# Factory test for USB ports.  The test checks USB ports are functional by
# requiring that an USB device be plugged in and unplugged from the number of
# ports specified.


import unittest
import logging
import os
import pyudev
import threading

import factory_common  # pylint: disable=W0611
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection
from cros.factory.test import factory


_UDEV_ACTION_INSERT = 'add'
_UDEV_ACTION_REMOVE = 'remove'

_MSG_PROMPT_FMT = lambda t: test_ui.MakeLabel(
    'Plug device into each USB port, %d to go...<br>' % t,
    zh='在每个 USB 端口插入装置, 还有 %d 个待测试...<br>' % t,
    css_class='usb-test-info')

# The layout contains one div for usb test
_ID_CONTAINER = 'usb-test-container'
_HTML_USB = '<div id="%s"></div>\n' % (_ID_CONTAINER)

_CSS_USB_TEST = '.usb-test-info { font-size: 2em; }'

class PyudevThread(threading.Thread):
  '''A thread class for monitoring udev events in the background.'''

  def __init__(self, callback, **udev_filters):
    threading.Thread.__init__(self)
    self._callback = callback
    self._udev_filters = dict(udev_filters)

  def run(self):
    '''Create a loop to monitor udev events and invoke callback function.'''
    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(**self._udev_filters)
    for action, device in monitor:
      self._callback(action, device)

class USBTest(unittest.TestCase):
  ARGS = [
    Arg('expected_paths', str, 'USB device path', None, optional=True),
    Arg('num_usb_ports', int, 'number of USB port', None, optional=True),
    Arg('num_usb2_ports', int, 'number of USB 2.0 ports', None, optional=True),
    Arg('num_usb3_ports', int, 'number of USB 3.0 ports', None, optional=True),
  ]
  version = 1

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)

    self._pyudev_thread = None
    self._expected_paths = self.args.expected_paths
    self._num_usb_ports = self.args.num_usb_ports
    self._num_usb2_ports = self.args.num_usb2_ports
    self._num_usb3_ports = self.args.num_usb3_ports

    self.assertTrue((self._num_usb_ports and (self._num_usb_ports > 0)) or
        (self._num_usb2_ports and (self._num_usb2_ports > 0)) or
        (self._num_usb3_ports and (self._num_usb3_ports > 0)),
        'USB port count not specified.')

    if not self._num_usb_ports:
      self._num_usb_ports = (self._num_usb2_ports or 0) + (
          self._num_usb3_ports or 0)

    self._seen_usb2_paths = set()
    self._seen_usb3_paths = set()

    if self._expected_paths:
      for path in self._expected_paths:
        if os.path.exists(path):
          self.record_path(path)

    self.template.SetState(_HTML_USB)
    self.ui.AppendCSS(_CSS_USB_TEST)
    self.ui.SetHTML(_MSG_PROMPT_FMT(self._num_usb_ports), id=_ID_CONTAINER)

  def record_path(self, sys_path):
    bus_path = os.path.dirname(sys_path)
    bus_ver_path = os.path.join(bus_path, 'version')
    bus_version = int(float(open(bus_ver_path, 'r').read().strip()))

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
      self.ui.Pass()
    else:
      self.ui.SetHTML(_MSG_PROMPT_FMT(self._num_usb_ports - total_count),
          id=_ID_CONTAINER)

  def usb_event_cb(self, action, device):
    if action not in [_UDEV_ACTION_INSERT, _UDEV_ACTION_REMOVE]:
      return

    factory.log('USB %s device path %s' % (action, device.sys_path))
    if self._expected_paths and device.sys_path not in self._expected_paths:
      return

    self.record_path(device.sys_path)

  def runTest(self):
    # Create a daemon pyudev thread to listen to device events
    self._pyudev_thread = PyudevThread(self.usb_event_cb,
        subsystem='usb', device_type='usb_device')
    self._pyudev_thread.daemon = True
    self._pyudev_thread.start()

    self.ui.Run()
