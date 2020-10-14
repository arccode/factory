#!/usr/bin/env python3
#
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for output classify plugin."""

import datetime
import logging
import os
import tempfile
import unittest
from unittest import mock

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_sandbox
from cros.factory.instalog.plugins import output_file
from cros.factory.instalog import testing


EVENT_FILE_NAME = output_file.EVENT_FILE_NAME
ATT_DIR_NAME = output_file.ATT_DIR_NAME
SAMPLE_TODAY = datetime.date(1989, 12, 12)
SAMPLE_SUBDIR_NAME = '19891212'


class TestOutputClassify(unittest.TestCase):

  def setUp(self):
    self.core = testing.MockCore()
    self.stream = self.core.GetStream(0)
    self.tmp_dir = tempfile.mkdtemp(prefix='output_classify_unittest_')
    self.target_dir = os.path.join(self.tmp_dir, 'target_dir')
    self.patcher = mock.patch('datetime.date')
    mock_date = self.patcher.start()
    mock_date.today.return_value = SAMPLE_TODAY

  def tearDown(self):
    self.core.Close()
    self.patcher.stop()

  def testOneEvent(self):
    config = {
        'interval': 1,
        'target_dir': self.target_dir}
    sandbox = plugin_sandbox.PluginSandbox(
        'output_classify', config=config,
        data_dir=self.tmp_dir, core_api=self.core)
    sandbox.Start(True)
    event = datatypes.Event({'deviceId': 'TEST_ID'})
    self.stream.Queue([event])
    sandbox.Flush(2, True)
    sandbox.Stop()

    base_dir = os.path.join(self.target_dir, SAMPLE_SUBDIR_NAME, 'TEST_ID')
    with open(os.path.join(base_dir, EVENT_FILE_NAME), 'r') as f:
      lines = f.readlines()
      self.assertEqual(1, len(lines))
      self.assertEqual(event, datatypes.Event.Deserialize(lines[0]))

  def testInvalidClassifiers(self):
    config = {
        'interval': 1,
        'target_dir': self.target_dir,
        'classifiers': ['a', 'b.c', '__INVALID__']}
    sandbox = plugin_sandbox.PluginSandbox(
        'output_classify', config=config,
        data_dir=self.tmp_dir, core_api=self.core)
    sandbox.Start(True)
    sandbox.AdvanceState(True)
    self.assertEqual(sandbox.GetState(), plugin_sandbox.DOWN)

  def testClassifiers(self):
    config = {
        'interval': 1,
        'target_dir': self.target_dir,
        'classifiers': ['a', 'b.c', '__DAY__', 'd']}
    sandbox = plugin_sandbox.PluginSandbox(
        'output_classify', config=config,
        data_dir=self.tmp_dir, core_api=self.core)
    sandbox.Start(True)
    event1 = datatypes.Event({'a': 'A', 'b': {'c': 'C'}, 'd': 'D', 'event': 1})
    event2 = datatypes.Event({'a': 'A', 'b': {'c': 'CC'}})
    event3 = datatypes.Event({'a': 'A', 'b': {'c': 'C'}, 'd': 'D', 'event': 3})
    self.stream.Queue([event1, event2, event3])
    sandbox.Flush(2, True)
    sandbox.Stop()

    base_dir = os.path.join(self.target_dir, 'A', 'C', SAMPLE_SUBDIR_NAME, 'D')
    with open(os.path.join(base_dir, EVENT_FILE_NAME), 'r') as f:
      lines = f.readlines()
      self.assertEqual(2, len(lines))
      self.assertEqual(event1, datatypes.Event.Deserialize(lines[0]))
      self.assertEqual(event3, datatypes.Event.Deserialize(lines[1]))

    base_dir = os.path.join(
        self.target_dir, 'A', 'CC', SAMPLE_SUBDIR_NAME, '__UNKNOWN__')
    with open(os.path.join(base_dir, EVENT_FILE_NAME), 'r') as f:
      lines = f.readlines()
      self.assertEqual(1, len(lines))
      self.assertEqual(event2, datatypes.Event.Deserialize(lines[0]))

  def ChangeRelativePath(self, event, base_dir):
    for att_id, relative_path in event.attachments.items():
      event.attachments[att_id] = os.path.join(
          base_dir, relative_path)

  def testOneEventOneAttachment(self):
    config = {
        'interval': 1,
        'target_dir': self.target_dir}
    sandbox = plugin_sandbox.PluginSandbox(
        'output_classify', config=config,
        data_dir=self.tmp_dir, core_api=self.core)
    sandbox.Start(True)
    att_path = os.path.join(self.tmp_dir, 'att')
    att_data = '!@#$%^&*()1234567890QWERTYUIOP'
    with open(att_path, 'w') as f:
      f.write(att_data)
    event = datatypes.Event({'deviceId': 'TEST_ID'}, {'att': att_path})
    self.stream.Queue([event])
    sandbox.Flush(2, True)
    sandbox.Stop()

    base_dir = os.path.join(self.target_dir, SAMPLE_SUBDIR_NAME, 'TEST_ID')
    with open(os.path.join(base_dir, EVENT_FILE_NAME)) as f:
      lines = f.readlines()
      self.assertEqual(1, len(lines))
      deserialized_event = datatypes.Event.Deserialize(lines[0])
      self.ChangeRelativePath(deserialized_event, base_dir)
      self.assertEqual(event, deserialized_event)


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
