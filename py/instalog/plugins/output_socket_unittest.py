#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for output socket plugin."""

from __future__ import print_function

import hashlib
import logging
import mock
import socket
import tempfile
import time
import unittest

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import log_utils
from instalog import plugin_sandbox
from instalog import testing


class TestInputSocket(unittest.TestCase):

  def setUp(self):
    self.core = testing.MockCore()
    config = {
        'hostname': 'localhost',
        'port': 8000,  # Does not actually need a valid available port.
        'timeout': 1}
    self.sandbox = plugin_sandbox.PluginSandbox(
        'output_socket', config=config, core_api=self.core)

    # Mock out the socket and set up default EventStream.
    self.sock = mock.MagicMock()
    self.patcher = mock.patch('socket.socket', return_value=self.sock)
    self.patcher.start()
    self.sock.recv.return_value = '1'  # Always return success.
    self.stream = self.core.GetStream(0)  # Only need one BufferEventStream.

    # Start the plugin.
    self.sandbox.Start(True)
    self.plugin = self.sandbox._plugin

  def tearDown(self):
    self.sandbox.Stop(True)
    self.patcher.stop()
    self.assertTrue(self.core.AllStreamsExpired())

  def _GetSentData(self):
    data = ''.join([x[1][0] for x in self.sock.sendall.mock_calls])
    self.sock.sendall.mock_calls = []
    return data

  def testPing(self):
    time.sleep(1)
    self.assertEqual(
        '0\0',  # ping
        self._GetSentData())

  def testMidTransmissionFailure(self):
    with mock.patch.object(self.plugin, 'Ping', return_value=True):
      with mock.patch.object(self.sock, 'sendall', side_effect=socket.error):
        self.core.GetStream(0).Queue([datatypes.Event({})])
        self.sandbox.Flush(0.1, True)
      with mock.patch.object(self.sock, 'sendall', side_effect=Exception):
        self.core.GetStream(0).Queue([datatypes.Event({})])
        self.sandbox.Flush(0.1, True)

  def testInvalidHeader(self):
    self.sock.recv.return_value = 'x'
    self.assertFalse(self.plugin.Ping())

  def testOneEvent(self):
    event = datatypes.Event({})
    with mock.patch.object(event, 'Serialize', return_value='EVENT'):
      self.core.GetStream(0).Queue([event])
      self.sandbox.Flush(2, True)
      self.assertEqual('0\0'  # ping
                       '1\0'
                       '5\0'
                       'EVENT'
                       '7c90977a1d83c431f761e4bae201bddd4a6f31d6\0'
                       '0\0',
                       self._GetSentData())

  def testOneEventOneAttachment(self):
    with tempfile.NamedTemporaryFile() as f:
      f.write('XXXXXXXXXX')
      f.flush()
      event = datatypes.Event({}, {'my_attachment': f.name})
      with mock.patch.object(event, 'Serialize', return_value='EVENT'):
        self.core.GetStream(0).Queue([event])
        self.sandbox.Flush(2, True)
        self.assertEqual('0\0'  # ping
                         '1\0'
                         '5\0'
                         'EVENT'
                         '7c90977a1d83c431f761e4bae201bddd4a6f31d6\0'
                         '1\0'
                         '13\0my_attachment'
                         '8c18ccf21585d969762e4da67bc890da8672ba5c\0'
                         '10\0XXXXXXXXXX'
                         '1c17e556736c4d23933f99d199e7c2c572895fd2\0',
                         self._GetSentData())


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG, format=log_utils.LOG_FORMAT)
  unittest.main()
