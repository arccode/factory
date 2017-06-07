#!/usr/bin/python2
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import logging
import os
import shutil
import tempfile
import time
import unittest

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import log_utils
from instalog import plugin_sandbox
from instalog import testing
from instalog.utils import net_utils

import gnupg


class TestHTTP(unittest.TestCase):

  def _CreatePlugin(self):
    self.core = testing.MockCore()
    self.hostname = 'localhost'
    self.port = net_utils.FindUnusedPort()

    # Create PluginSandbox for output plugin.
    output_config = {
        'hostname': 'localhost',
        'port': self.port,
        'batch_size': 4,
        'timeout': 10}
    self.output_sandbox = plugin_sandbox.PluginSandbox(
        'output_http', config=output_config, core_api=self.core)

    # Create PluginSandbox for input plugin.
    input_config = {
        'hostname': 'localhost',
        'port': self.port,
        'max_bytes': 30 * 1024 * 1024}  # 30mb
    self.input_sandbox = plugin_sandbox.PluginSandbox(
        'input_http', config=input_config, core_api=self.core)

    # Start the plugins.  Input needs to start first; otherwise Output will
    # sleep for _FAILED_CONNECTION_INTERVAL.
    self.input_sandbox.Start(True)
    time.sleep(0.5)
    self.output_sandbox.Start(True)

    # Store a BufferEventStream.
    self.stream = self.core.GetStream(0)

  def setUp(self):
    self._CreatePlugin()
    self._tmp_dir = tempfile.mkdtemp(prefix='http_e2e_unittest_')

  def tearDown(self):
    self.output_sandbox.Stop(True)
    self.input_sandbox.Stop(True)
    self.core.Close()
    shutil.rmtree(self._tmp_dir)

  def testOneEvent(self):
    self.stream.Queue([datatypes.Event({})])
    self.output_sandbox.Flush(2, True)
    self.assertEquals(self.core.emit_calls, [[datatypes.Event({})]])

  def testMultiEvent(self):
    with tempfile.NamedTemporaryFile('w', dir=self._tmp_dir) as f1:
      with tempfile.NamedTemporaryFile('w', dir=self._tmp_dir) as f2:
        att_path1 = f1.name
        att_path2 = f2.name
        att_data1 = '!' * 10 * 1024 * 1024  # 10mb
        att_data2 = '!' * 10 * 1024 * 1024  # 10mb
        with open(att_path1, 'w') as f:
          f.write(att_data1)
        with open(att_path2, 'w') as f:
          f.write(att_data2)
        event1 = datatypes.Event({}, {'my_attachment': att_path1})
        event2 = datatypes.Event({'AA': 'BB'}, {'my_attachment': att_path2})
        event3 = datatypes.Event({'CC': 'DD'}, {})
        self.stream.Queue([event1, event2, event3])
        self.output_sandbox.Flush(10, True)
        self.assertEqual(1, len(self.core.emit_calls))
        self.assertEqual(3, len(self.core.emit_calls[0]))
        self.assertEqual(event1, self.core.emit_calls[0][0])
        self.assertEqual(event2, self.core.emit_calls[0][1])
        self.assertEqual(event3, self.core.emit_calls[0][2])

  def testTooLargeRequest(self):
    with tempfile.NamedTemporaryFile('w', dir=self._tmp_dir) as f1:
      with tempfile.NamedTemporaryFile('w', dir=self._tmp_dir) as f2:
        att_path1 = f1.name
        att_path2 = f2.name
        att_data1 = '!' * 20 * 1024 * 1024  # 20mb
        att_data2 = '!' * 20 * 1024 * 1024  # 20mb
        with open(att_path1, 'w') as f:
          f.write(att_data1)
        with open(att_path2, 'w') as f:
          f.write(att_data2)
        event1 = datatypes.Event({'AA': 'BB'}, {'my_attachment': att_path1})
        event2 = datatypes.Event({'AA': 'BB'}, {'my_attachment': att_path2})
        self.stream.Queue([event1, event2])
        self.output_sandbox.Flush(10, True)
        self.assertEqual(2, len(self.core.emit_calls))
        self.assertEqual(1, len(self.core.emit_calls[0]))
        self.assertEqual(1, len(self.core.emit_calls[1]))
        self.assertEqual(event1, self.core.emit_calls[0][0])
        self.assertEqual(event2, self.core.emit_calls[1][0])

  def testTooLargeEvent(self):
    # Output HTTP plugin should have error message: One event is bigger than
    # input HTTP plugin's maximum request limit (event size = 41943699bytes,
    # input plugin maximum size = 31457280bytes)
    with tempfile.NamedTemporaryFile('w', dir=self._tmp_dir) as f:
      att_path = f.name
      att_data = '!' * 40 * 1024 * 1024  # 40mb
      with open(att_path, 'w') as f:
        f.write(att_data)
      event = datatypes.Event({'AA': 'BB'}, {'my_attachment': att_path})
      self.stream.Queue([event])
      self.output_sandbox.Flush(2, True)
      self.assertEqual(0, len(self.core.emit_calls))
      self.assertTrue(self.core.AllStreamsExpired())


class TestHTTPAE(unittest.TestCase):

  def _CreateKeys(self):
    # Generate key pairs and export keys.
    # pylint: disable=unexpected-keyword-arg
    gpg_output = gnupg.GPG(homedir=os.path.join(self._tmp_dir, 'gpg_output'))
    gen_key_result = gpg_output.gen_key(
        gpg_output.gen_key_input(key_type='RSA',
                                 key_length=1024,
                                 subkey_type='RSA',
                                 subkey_length=1024))
    key_fpr_output = gen_key_result.fingerprint
    key_output = gpg_output.export_keys(key_fpr_output)

    gpg_input = gnupg.GPG(homedir=os.path.join(self._tmp_dir, 'gpg_input'))
    gen_key_result = gpg_input.gen_key(
        gpg_input.gen_key_input(key_type='RSA',
                                key_length=1024,
                                subkey_type='RSA',
                                subkey_length=1024))
    self._target_key = gen_key_result.fingerprint
    key_fpr_input = gen_key_result.fingerprint
    key_input = gpg_input.export_keys(key_fpr_input)

    # Import keys and trust keys.
    gpg_output.import_keys(key_input)
    gpg_output.sign_key(key_fpr_input)

    gpg_input.import_keys(key_output)
    gpg_input.sign_key(key_fpr_output)

  def _CreatePlugin(self):
    self.core = testing.MockCore()
    self.hostname = 'localhost'
    self.port = net_utils.FindUnusedPort()

    # Create PluginSandbox for output plugin.
    output_config = {
        'hostname': 'localhost',
        'port': self.port,
        'batch_size': 4,
        'timeout': 10,
        'enable_gnupg': True,
        'gnupg_home': os.path.join(self._tmp_dir, 'gpg_output'),
        'target_key': self._target_key}
    self.output_sandbox = plugin_sandbox.PluginSandbox(
        'output_http', config=output_config, core_api=self.core)

    # Create PluginSandbox for input plugin.
    input_config = {
        'hostname': 'localhost',
        'port': self.port,
        'enable_gnupg': True,
        'gnupg_home': os.path.join(self._tmp_dir, 'gpg_input')}
    self.input_sandbox = plugin_sandbox.PluginSandbox(
        'input_http', config=input_config, core_api=self.core)

    # Start the plugins.  Input needs to start first; otherwise Output will
    # sleep for _FAILED_CONNECTION_INTERVAL.
    self.input_sandbox.Start(True)
    time.sleep(0.5)
    self.output_sandbox.Start(True)

    # Store a BufferEventStream.
    self.stream = self.core.GetStream(0)

  def setUp(self):
    self._tmp_dir = tempfile.mkdtemp(prefix='http_ae_e2e_unittest_')
    self._target_key = None
    self._CreateKeys()
    self._CreatePlugin()

  def tearDown(self):
    self.output_sandbox.Stop(True)
    self.input_sandbox.Stop(True)
    self.core.Close()
    shutil.rmtree(self._tmp_dir)

  def testOneEvent(self):
    self.stream.Queue([datatypes.Event({})])
    self.output_sandbox.Flush(2, True)
    self.assertEquals(self.core.emit_calls, [[datatypes.Event({})]])

  def testMultiEvent(self):
    with tempfile.NamedTemporaryFile('w', dir=self._tmp_dir) as f1:
      with tempfile.NamedTemporaryFile('w', dir=self._tmp_dir) as f2:
        att_path1 = f1.name
        att_path2 = f2.name
        att_data1 = '!' * 10 * 1024 * 1024  # 10mb
        att_data2 = '!' * 10 * 1024 * 1024  # 10mb
        with open(att_path1, 'w') as f:
          f.write(att_data1)
        with open(att_path2, 'w') as f:
          f.write(att_data2)
        event1 = datatypes.Event({}, {'my_attachment': att_path1})
        event2 = datatypes.Event({'AA': 'BB'}, {'my_attachment': att_path2})
        event3 = datatypes.Event({'CC': 'DD'}, {})
        self.stream.Queue([event1, event2, event3])
        self.output_sandbox.Flush(10, True)
        self.assertEqual(1, len(self.core.emit_calls))
        self.assertEqual(3, len(self.core.emit_calls[0]))
        self.assertEqual(event1, self.core.emit_calls[0][0])
        self.assertEqual(event2, self.core.emit_calls[0][1])
        self.assertEqual(event3, self.core.emit_calls[0][2])


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO, format=log_utils.LOG_FORMAT)
  unittest.main()
