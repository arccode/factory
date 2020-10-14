#!/usr/bin/env python3
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for output archive plugin."""

import copy
import glob
import logging
import os
import resource
import shutil
import tarfile
import tempfile
import time
import unittest

import psutil

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_sandbox
from cros.factory.instalog import testing


class TestOutputArchive(unittest.TestCase):

  def setUp(self):
    self.core = testing.MockCore()
    self.stream = self.core.GetStream(0)
    self.tmp_dir = tempfile.mkdtemp(prefix='output_archive_unittest_')
    self.event = datatypes.Event({'plugin': 'archive'})

  def tearDown(self):
    self.core.Close()
    shutil.rmtree(self.tmp_dir)

  def _GetMemoryUsage(self):
    """Returns current process's memory usage in bytes."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024

  def testMemoryUsage(self):
    big_event = datatypes.Event({'1mb': 'x' * 1024 * 1024})
    event_size = len(big_event.Serialize())
    config = {
        'interval': 1000,  # arbitrary long time
        'threshold_size': 1024 * 1024 * 1024,  # arbitrary large value
    }
    sandbox = plugin_sandbox.PluginSandbox(
        'output_archive', config=config,
        data_dir=self.tmp_dir, core_api=self.core)
    sandbox.Start(True)

    mem_usage_start = self._GetMemoryUsage()
    logging.info('Initial memory usage: %d', mem_usage_start)
    # additional_memory = big_event(1mb) * 10 events * 20 iterations = ~200mb
    # maximum_memory = (original_memory + additional_memory) plus 10% padding
    mem_usage_max = (mem_usage_start + (event_size * 10 * 20)) * 1.1
    for unused_i in range(20):
      events = [copy.deepcopy(big_event) for unused_j in range(10)]
      self.stream.Queue(events)

    sandbox.Flush(1, False)  # trigger archive creation
    while not self.stream.Empty():
      mem_usage = self._GetMemoryUsage()
      logging.info('Current memory usage: %d/%d', mem_usage, mem_usage_max)
      if mem_usage >= mem_usage_max:
        # The test has failed, but we need to interrupt the archive plugin
        # and get it to stop as quickly as possible.
        # Stop new events from being accessed.
        del self.core.streams[0]
        # Force any open file handles shut so the plugin stops writing
        # to the archive on disk.
        proc = psutil.Process()
        for f in proc.get_open_files():
          os.close(f.fd)
        # Manually set the plugin state to STOPPING and advance into this
        # state.
        # pylint: disable=protected-access
        sandbox._state = plugin_sandbox.STOPPING
        sandbox.AdvanceState(True)
        # Once the plugin has really stopped, report our error.
        self.fail('Memory usage exceeded: %d/%d' % (mem_usage, mem_usage_max))
      time.sleep(0.1)
    # pylint: disable=protected-access
    sandbox._state = plugin_sandbox.STOPPING
    sandbox.AdvanceState(True)

  def testOneEvent(self):
    config = {
        'interval': 1}
    sandbox = plugin_sandbox.PluginSandbox(
        'output_archive', config=config,
        data_dir=self.tmp_dir, core_api=self.core)
    sandbox.Start(True)
    # pylint: disable=protected-access
    plugin = sandbox._plugin
    self.stream.Queue([self.event])
    plugin.PrepareAndProcess()
    sandbox.Flush(2, True)
    sandbox.Stop()

    # Inspect the disk archive.
    archive_path = glob.glob(os.path.join(self.tmp_dir, 'InstalogEvents*'))[0]
    with tarfile.open(archive_path, 'r:gz') as tar:
      events_member = [n for n in tar.getnames() if 'events.json' in n][0]
      events_file = tar.extractfile(events_member)
      lines = events_file.readlines()
      self.assertEqual(1, len(lines))
      event = datatypes.Event.Deserialize(lines[0])
      self.assertEqual(event, self.event)


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
