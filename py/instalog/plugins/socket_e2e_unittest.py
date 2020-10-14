#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import tempfile
import time
import unittest

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_sandbox
from cros.factory.instalog import testing
from cros.factory.instalog.utils import net_utils


class TestSocket(unittest.TestCase):

  def setUp(self):
    self.core = testing.MockCore()
    self.hostname = 'localhost'
    self.port = net_utils.FindUnusedPort()

    # Create PluginSandbox for output plugin.
    output_config = {
        'hostname': 'localhost',
        'port': self.port,
        'timeout': 1}
    self.output_sandbox = plugin_sandbox.PluginSandbox(
        'output_socket', config=output_config, core_api=self.core)

    # Create PluginSandbox for input plugin.
    input_config = {
        'hostname': 'localhost',
        'port': self.port}
    self.input_sandbox = plugin_sandbox.PluginSandbox(
        'input_socket', config=input_config, core_api=self.core)

    # Start the plugins.  Input needs to start first; otherwise Output will
    # sleep for _FAILED_CONNECTION_INTERVAL.
    self.input_sandbox.Start(True)
    time.sleep(0.5)
    self.output_sandbox.Start(True)

    # Store a BufferEventStream.
    self.stream = self.core.GetStream(0)

  def tearDown(self):
    self.output_sandbox.Stop(True)
    self.input_sandbox.Stop(True)
    self.core.Close()

  def testOneEvent(self):
    self.stream.Queue([datatypes.Event({})])
    self.output_sandbox.Flush(2, True)
    self.assertEqual(self.core.emit_calls, [[datatypes.Event({})]])

  def testOneEventOneAttachment(self):
    with tempfile.NamedTemporaryFile('w') as f:
      f.write('XXXXXXXXXX')
      f.flush()
      event = datatypes.Event({}, {'my_attachment': f.name})
      self.stream.Queue([event])
      self.output_sandbox.Flush(2, True)
      self.assertEqual(1, len(self.core.emit_calls))
      event_list = self.core.emit_calls[0]
      self.assertEqual(1, len(event_list))
      self.assertEqual({}, event_list[0].payload)
      self.assertEqual(1, len(event_list[0].attachments))
      self.assertEqual(b'my_attachment', list(event_list[0].attachments)[0])
      with open(next(iter(event_list[0].attachments.values()))) as f:
        self.assertEqual('XXXXXXXXXX', f.read())


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
