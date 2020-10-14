#!/usr/bin/env python3
#
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for output file plugin."""

import logging
import os
import tempfile
import unittest

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_sandbox
from cros.factory.instalog.plugins import output_file
from cros.factory.instalog import testing
from cros.factory.instalog.utils import file_utils


EVENT_FILE_NAME = output_file.EVENT_FILE_NAME
ATT_DIR_NAME = output_file.ATT_DIR_NAME


class TestOutputFile(unittest.TestCase):

  def setUp(self):
    self.core = testing.MockCore()
    self.stream = self.core.GetStream(0)
    self.tmp_dir = tempfile.mkdtemp(prefix='output_file_unittest_')
    self.target_dir = os.path.join(self.tmp_dir, 'target_dir')

  def tearDown(self):
    self.core.Close()

  def testOneEvent(self):
    config = {
        'interval': 1,
        'target_dir': self.target_dir}
    sandbox = plugin_sandbox.PluginSandbox(
        'output_file', config=config,
        data_dir=self.tmp_dir, core_api=self.core)
    sandbox.Start(True)
    # pylint: disable=protected-access
    plugin = sandbox._plugin
    event = datatypes.Event({'plugin': 'file'})
    self.stream.Queue([event])
    plugin.PrepareAndProcess()
    sandbox.Flush(2, True)
    sandbox.Stop()

    with open(os.path.join(self.target_dir, EVENT_FILE_NAME)) as f:
      lines = f.readlines()
      self.assertEqual(1, len(lines))
      deserialized_event = datatypes.Event.Deserialize(lines[0])
      self.assertEqual(event, deserialized_event)
      self.assertEqual(1, len(deserialized_event.history))

  def testExcludeHistory(self):
    config = {
        'exclude_history': True,
        'interval': 1,
        'target_dir': self.target_dir}
    sandbox = plugin_sandbox.PluginSandbox(
        'output_file', config=config,
        data_dir=self.tmp_dir, core_api=self.core)
    sandbox.Start(True)
    # pylint: disable=protected-access
    plugin = sandbox._plugin
    event = datatypes.Event(payload={'key': 'data w/o history'})
    self.stream.Queue([event])
    plugin.PrepareAndProcess()
    sandbox.Flush(2, True)
    sandbox.Stop()

    with open(os.path.join(self.target_dir, EVENT_FILE_NAME)) as f:
      lines = f.readlines()
      self.assertEqual(1, len(lines))
      deserialized_event = datatypes.Event.Deserialize(lines[0])
      self.assertEqual(event, deserialized_event)
      self.assertEqual([], deserialized_event.history)

  def ChangeRelativePath(self, event, base_dir):
    for att_id, relative_path in event.attachments.items():
      event.attachments[att_id] = os.path.join(
          base_dir, relative_path)

  def testOneEventOneAttachment(self):
    config = {
        'interval': 1,
        'target_dir': self.target_dir}
    sandbox = plugin_sandbox.PluginSandbox(
        'output_file', config=config,
        data_dir=self.tmp_dir, core_api=self.core)
    sandbox.Start(True)
    # pylint: disable=protected-access
    plugin = sandbox._plugin
    att_path = os.path.join(self.tmp_dir, 'att')
    att_data = '!@#$%^&*()1234567890QWERTYUIOP'
    with open(att_path, 'w') as f:
      f.write(att_data)
    event = datatypes.Event({'plugin': 'file'}, {'att': att_path})
    self.stream.Queue([event])
    plugin.PrepareAndProcess()
    sandbox.Flush(2, True)
    sandbox.Stop()

    with open(os.path.join(self.target_dir, EVENT_FILE_NAME)) as f:
      lines = f.readlines()
      self.assertEqual(1, len(lines))
      deserialized_event = datatypes.Event.Deserialize(lines[0])
      self.ChangeRelativePath(deserialized_event, self.target_dir)
      self.assertEqual(event, deserialized_event)

  def testMoveAndMerge(self):
    event1 = datatypes.Event({'event_id': '1'})
    event2 = datatypes.Event({'event_id': 2, 'plugin': 'file'},
                             {'att': 'attachments/att_test'})
    att_data = '!@#$%^&*()1234567890QWERTYUIOP'

    with file_utils.TempDirectory(prefix='src_dir_') as src_dir:
      os.makedirs(os.path.join(src_dir, ATT_DIR_NAME))
      with open(os.path.join(src_dir, EVENT_FILE_NAME), 'w') as f:
        f.write(event1.Serialize() + '\n')
        f.write(event2.Serialize() + '\n')
      att_path = os.path.join(src_dir, ATT_DIR_NAME, 'att_test')
      with open(att_path, 'w') as f:
        f.write(att_data)
      output_file.MoveAndMerge(src_dir, self.target_dir)

    with file_utils.TempDirectory(prefix='src_dir_') as src_dir:
      os.makedirs(os.path.join(src_dir, ATT_DIR_NAME))
      with open(os.path.join(src_dir, EVENT_FILE_NAME), 'w') as f:
        f.write(event2.Serialize() + '\n')
        f.write(event1.Serialize() + '\n')
      att_path = os.path.join(src_dir, ATT_DIR_NAME, 'att_test')
      with open(att_path, 'w') as f:
        f.write(att_data)
      output_file.MoveAndMerge(src_dir, self.target_dir)

    with open(os.path.join(self.target_dir, EVENT_FILE_NAME)) as f:
      lines = f.readlines()
      self.assertEqual(4, len(lines))
      self.assertEqual(event1, datatypes.Event.Deserialize(lines[0]))
      self.assertEqual(event2, datatypes.Event.Deserialize(lines[1]))
      self.assertEqual(event2, datatypes.Event.Deserialize(lines[2]))
      self.assertEqual(event1, datatypes.Event.Deserialize(lines[3]))


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
