#!/usr/bin/env python3
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for priority multi-file-based buffer."""

import copy
import logging
import random
import shutil
import tempfile
import threading
import unittest

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog.plugins import buffer_priority_file
from cros.factory.instalog.utils import file_utils


# pylint: disable=protected-access
class TestBufferPriorityFile(unittest.TestCase):

  def _CreateBuffer(self, config=None):
    # Remove previous temporary folder if any.
    if self.data_dir is not None:
      shutil.rmtree(self.data_dir)
    self.data_dir = tempfile.mkdtemp(prefix='buffer_priority_file_unittest_')
    logging.info('Create state directory: %s', self.data_dir)
    self.sf = buffer_priority_file.BufferPriorityFile(
        config={} if config is None else config,
        logger_name='priority_file',
        store={},
        plugin_api=None)
    self.sf.GetDataDir = lambda: self.data_dir
    self.sf.SetUp()

  def setUp(self):
    self.data_dir = None
    self._CreateBuffer()

    self.pri_level_max = buffer_priority_file._PRIORITY_LEVEL
    self.e = []
    for pri_level in range(self.pri_level_max):
      self.e.append(datatypes.Event({'priority': pri_level}))

  def tearDown(self):
    shutil.rmtree(self.data_dir)

  def _ProducePriorityEvent(self, pri_level, target_file_num=None):
    """Produces a priority event to a specific data buffer."""
    assert pri_level < self.pri_level_max
    if target_file_num is not None:
      for file_num, file_num_lock in enumerate(self.sf._file_num_lock):
        if file_num != target_file_num:
          file_num_lock.acquire()
    result = self.sf.Produce([copy.deepcopy(self.e[pri_level])])
    assert result, 'Emit failed!'
    if target_file_num is not None:
      for file_num, file_num_lock in enumerate(self.sf._file_num_lock):
        if file_num != target_file_num:
          file_num_lock.release()

  def testConsumeOrder(self):
    self.sf.AddConsumer('a')

    self._ProducePriorityEvent(0, 0)
    self._ProducePriorityEvent(1, 1)
    self._ProducePriorityEvent(2, 2)
    self._ProducePriorityEvent(3, 3)
    stream = self.sf.Consume('a')
    for pri_level in range(self.pri_level_max):
      self.assertEqual(self.e[pri_level], stream.Next())
    self.assertEqual(None, stream.Next())
    stream.Commit()

    self._ProducePriorityEvent(3, 3)
    self._ProducePriorityEvent(2, 2)
    self._ProducePriorityEvent(1, 1)
    self._ProducePriorityEvent(0, 0)
    stream = self.sf.Consume('a')
    for pri_level in range(self.pri_level_max):
      self.assertEqual(self.e[pri_level], stream.Next())
    self.assertEqual(None, stream.Next())
    stream.Commit()

    self._ProducePriorityEvent(3, 0)
    self._ProducePriorityEvent(2, 0)
    self._ProducePriorityEvent(1, 0)
    self._ProducePriorityEvent(0, 0)
    stream = self.sf.Consume('a')
    for pri_level in range(self.pri_level_max):
      self.assertEqual(self.e[pri_level], stream.Next())
    self.assertEqual(None, stream.Next())
    stream.Commit()

    self._ProducePriorityEvent(0)
    self._ProducePriorityEvent(3)
    stream = self.sf.Consume('a')
    self.assertEqual(self.e[0], stream.Next())
    self.assertEqual(self.e[3], stream.Next())
    self._ProducePriorityEvent(2)
    self._ProducePriorityEvent(0)
    self.assertEqual(self.e[0], stream.Next())
    self.assertEqual(self.e[2], stream.Next())
    self.assertEqual(None, stream.Next())
    stream.Commit()

  def testMultithreadOrder(self):
    self.sf.AddConsumer('a')
    stream = self.sf.Consume('a')

    events = []
    for _unused_i in range(2000):
      for pri_level in range(self.pri_level_max):
        events.append(self.e[pri_level])
    random.shuffle(events)
    threads = []
    for i in range(0, 2000 * self.pri_level_max, 1000):
      threads.append(threading.Thread(target=self.sf.Produce,
                                      args=(events[i:i+1000],)))
    for t in threads:
      t.start()
    for t in threads:
      t.join()

    for pri_level in range(self.pri_level_max):
      for i in range(2000):
        self.assertEqual(self.e[pri_level], stream.Next())
    self.assertEqual(None, stream.Next())

  def testTruncate(self):
    self.sf.AddConsumer('a')

    self._ProducePriorityEvent(0, 0)
    self._ProducePriorityEvent(1, 1)
    self._ProducePriorityEvent(2, 2)
    self._ProducePriorityEvent(3, 3)
    self._ProducePriorityEvent(0, 3)
    self._ProducePriorityEvent(1, 2)
    self._ProducePriorityEvent(2, 1)
    self._ProducePriorityEvent(3, 0)

    stream = self.sf.Consume('a')
    self.assertEqual(self.e[0], stream.Next())
    self.assertEqual(self.e[0], stream.Next())
    self.assertEqual(self.e[1], stream.Next())
    stream.Commit()

    self.sf.Truncate()
    stream = self.sf.Consume('a')
    self.assertEqual(self.e[1], stream.Next())
    self.assertEqual(self.e[2], stream.Next())
    stream.Commit()

    self._ProducePriorityEvent(0)
    self._ProducePriorityEvent(1)

    stream = self.sf.Consume('a')
    self.assertEqual(self.e[0], stream.Next())
    self.assertEqual(self.e[1], stream.Next())
    self.assertEqual(self.e[2], stream.Next())
    stream.Commit()

    self._ProducePriorityEvent(0)
    self._ProducePriorityEvent(1)

    self.sf.Truncate()
    self.sf.TearDown()
    self.sf.SetUp()

    stream = self.sf.Consume('a')
    self.assertEqual(self.e[0], stream.Next())
    self.assertEqual(self.e[1], stream.Next())
    self.assertEqual(self.e[3], stream.Next())
    stream.Commit()

    self._ProducePriorityEvent(0)
    self._ProducePriorityEvent(1)

    stream = self.sf.Consume('a')
    self.assertEqual(self.e[0], stream.Next())
    self.assertEqual(self.e[1], stream.Next())
    self.assertEqual(self.e[3], stream.Next())
    self.assertEqual(None, stream.Next())
    stream.Commit()

  def testTruncateWithAttachments(self):
    self._CreateBuffer({'copy_attachments': True})
    for pri_level in range(self.pri_level_max):
      path = file_utils.CreateTemporaryFile()
      with open(path, 'w') as f:
        f.write('Priority leve = %d' % pri_level)
      self.e[pri_level].attachments['att'] = path
    self.testTruncate()

  def testRecoverTemporaryMetadata(self):
    self.sf.AddConsumer('a')
    stream = self.sf.Consume('a')

    self._ProducePriorityEvent(0, 0)
    self._ProducePriorityEvent(1, 1)
    self._ProducePriorityEvent(2, 2)
    self._ProducePriorityEvent(3, 3)

    self.assertEqual(self.e[0], stream.Next())

    self.sf.SaveTemporaryMetadata(0)
    # These four events should be ignored.
    self._ProducePriorityEvent(0, 0)
    self._ProducePriorityEvent(0, 0)
    self._ProducePriorityEvent(0, 0)
    self._ProducePriorityEvent(0, 0)
    # These two events should be recorded.
    self._ProducePriorityEvent(1, 1)
    self._ProducePriorityEvent(2, 2)

    stream.Commit()
    self.sf.TearDown()
    # SetUp will find the temporary metadata, and recovering it.
    self.sf.SetUp()
    stream = self.sf.Consume('a')

    self._ProducePriorityEvent(3, 3)

    self.assertEqual(self.e[1], stream.Next())
    self.assertEqual(self.e[1], stream.Next())
    self.assertEqual(self.e[2], stream.Next())
    self.assertEqual(self.e[2], stream.Next())
    self.assertEqual(self.e[3], stream.Next())
    self.assertEqual(self.e[3], stream.Next())
    self.assertEqual(None, stream.Next())

  def testRecoverTemporaryMetadataWithAttachments(self):
    self._CreateBuffer({'copy_attachments': True})
    for pri_level in range(self.pri_level_max):
      path = file_utils.CreateTemporaryFile()
      with open(path, 'w') as f:
        f.write('Priority leve = %d' % pri_level)
      self.e[pri_level].attachments['att'] = path
    self.testRecoverTemporaryMetadata()


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO, format=log_utils.LOG_FORMAT)
  unittest.main()
