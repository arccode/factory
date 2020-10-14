#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for simple file-based buffer."""

# TODO(kitching): Add tests that deal with "out of disk space" situations.
# TODO(kitching): Add tests for reading data from corrupted databases.
#                 - data.json is smaller than pos in metadata.json
#                 - metadata.json does not contain the right version
#                 - metadata.json is an empty dict {}
#                 - metadata.json does not exist
#                 - data.json does not exist
#                 - metadata recovery: uncorrupted data.json
#                 - metadata recovery: corruptions at the beginning of data.json
#                 - metadata recovery: corruptions at the end of data.json
#                 - metadata recovery: fully corrupted data.json
#                 - consumer metadata: seq smaller than first_seq
#                 - consumer metadata: seq larger than last_seq
#                 - consumer metadata: pos smaller than start_pos
#                 - consumer metadata: pos larger than end_pos
#                 - consumer metadata: pos not synchronized with seq
#                 - consumer metadata is an empty dict {}
#                 - consumer metadata missing cur_pos or cur_seq
# TODO(kitching): Add tests for failure during Truncate operation.

import collections
import functools
import logging
import os
import queue
import random
import shutil
import tempfile
import threading
import time
import unittest

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_base
# pylint: disable=no-name-in-module
from cros.factory.instalog.plugins import buffer_file_common
from cros.factory.instalog.plugins import buffer_simple_file
from cros.factory.instalog.utils import file_utils

# pylint: disable=protected-access


def _WithBufferSize(buffer_size):
  def ModifyFn(fn):
    @functools.wraps(fn)
    def Wrapper(*args, **kwargs):
      old_buffer_size_bytes = (
          buffer_simple_file.buffer_file_common._BUFFER_SIZE_BYTES)
      buffer_simple_file.buffer_file_common._BUFFER_SIZE_BYTES = buffer_size
      try:
        fn(*args, **kwargs)
      finally:
        buffer_simple_file.buffer_file_common._BUFFER_SIZE_BYTES = (
            old_buffer_size_bytes)
    return Wrapper
  return ModifyFn


class TestBufferSimpleFile(unittest.TestCase):

  def _CreateBuffer(self, config=None):
    # Remove previous temporary folder if any.
    if self.data_dir is not None:
      shutil.rmtree(self.data_dir)
    self.data_dir = tempfile.mkdtemp(prefix='buffer_simple_file_unittest_')
    logging.info('Create state directory: %s', self.data_dir)
    self.sf = buffer_simple_file.BufferSimpleFile(
        config={} if config is None else config,
        logger_name=self.logger.name,
        store={},
        plugin_api=None)
    self.sf.GetDataDir = lambda: self.data_dir
    self.sf.SetUp()
    self.e1 = datatypes.Event({'test1': 'event'})
    self.e2 = datatypes.Event({'test22': 'event'})
    self.e3 = datatypes.Event({'test333': 'event'})
    self.e4 = datatypes.Event({'test4444': 'event'})
    self.e5 = datatypes.Event({'test55555': 'event'})

  def setUp(self):
    self.logger = logging.getLogger('simple_file')
    self.data_dir = None
    self._CreateBuffer()

  def tearDown(self):
    shutil.rmtree(self.data_dir)

  def testFormatParseRecord(self):
    """Tests internal format and parse of data.json record."""
    SEQ = 1989
    RECORD = '{1: "hello world"}'
    FORMATED_RECORD = '[1989, {1: "hello world"}, "ea05f160"]\n'
    self.assertEqual(FORMATED_RECORD,
                     buffer_file_common.FormatRecord(SEQ, RECORD))
    seq, record = buffer_file_common.ParseRecord(
        FORMATED_RECORD, self.logger.name)
    self.assertEqual(SEQ, seq)
    self.assertEqual(RECORD, record)

    # TODO(chuntsen): Remove old format.
    seq, record = buffer_file_common.ParseRecord(
        '[1989, {1: "hello world"}, 15fa0ea0]\n', self.logger.name)
    self.assertEqual(SEQ, seq)
    self.assertEqual(RECORD, record)
    # TODO(chuntsen): Remove legacy test.
    seq, record = buffer_file_common.ParseRecord(
        '[1989, {1: "hello world"}, "15fa0ea0"]\n', self.logger.name)
    self.assertEqual(SEQ, seq)
    self.assertEqual(RECORD, record)

  def testAddRemoveConsumer(self):
    """Tests adding and removing a Consumer."""
    self.assertEqual({}, self.sf.ListConsumers())
    self.sf.AddConsumer('a')
    self.assertEqual(['a'], list(self.sf.ListConsumers()))
    self.sf.RemoveConsumer('a')
    self.assertEqual({}, self.sf.ListConsumers())

  def testWriteRead(self):
    """Tests writing and reading back an Event."""
    self.sf.Produce([self.e1])
    self.sf.AddConsumer('a')
    stream = self.sf.Consume('a')
    self.assertEqual(self.e1, stream.Next())

  def testLongCorruptedRecord(self):
    """Tests reading from a data store with a long corrupted record."""
    # Ensure that the size of the event is greater than _BUFFER_SIZE_BYTES.
    # pylint: disable=protected-access
    e = datatypes.Event(
        {'data':
         'x' * buffer_simple_file.buffer_file_common._BUFFER_SIZE_BYTES})
    self.sf.Produce([e])
    # Purposely corrupt the data file.
    with open(self.sf.buffer_file.data_path, 'r+') as f:
      f.seek(1)
      f.write('x')
    self.sf.Produce([self.e2])
    self.sf.AddConsumer('a')
    stream = self.sf.Consume('a')
    self.assertEqual(self.e2, stream.Next())

  def testSkippedRecords(self):
    """Tests recovery from skipped records due to corruption.

    Previously (prior to this test), a bug existed where, after a corrupt record
    was skipped, its length was not included in calculating "new_pos" for a
    consumer when processing subsequent records.

    To illustrate this bug, we design a situation where we have two "buffer
    refills".  The first one includes a garbage event (e2) which will be
    dropped.  Padding is inserted into event e to ensure that the last event e3
    is pushed into buffer refill #2.  Events are retrieved sequentially from
    buffer refill #1.  As long as len(e2) > len(e1), after retrieving the last
    event from buffer refill #1, the consumer's new_pos will be set to a
    location *before* the last event in buffer refill #1.  Thus the next buffer
    will include both e1 and e3.

      |--------------refill buffer #1----------------||---refill buffer #2---|
       [  e1  ]  [  e2  GARBAGE  ]  [  e  ]  [  e1  ]  [   e3   ]

      To calculate buffer size needed in e:
       --------   (doesn't count)   -------  -------- +1 to push over "<" limit

    The fix is to ensure that the length of any previous "garbage records" are
    included in the stored "length" of any event in the buffer.  E.g. in this
    case, the length of e2(GARBAGE) would be included in the length of event e.
    """
    self.sf.Produce([self.e1])
    e1_end = os.path.getsize(self.sf.buffer_file.data_path)
    self.sf.Produce([self.e2])
    e2_end = os.path.getsize(self.sf.buffer_file.data_path)

    # Corrupt event e2 by writing garbage at the end.
    with open(self.sf.buffer_file.data_path, 'r+') as f:
      f.seek(e2_end - 10)
      f.write('x' * 5)

    # pylint: disable=protected-access
    # Ensure that both e and e1 are included in the first buffer refill.  The
    # length of e can be based off of that of e1 (same base payload).
    bytes_left = (buffer_simple_file.buffer_file_common._BUFFER_SIZE_BYTES -
                  (e1_end * 3) + 1)
    e = datatypes.Event({'test1': 'event' + ('x' * bytes_left)})
    self.sf.Produce([e])
    self.sf.Produce([self.e1])
    self.sf.Produce([self.e3])

    self.sf.AddConsumer('a')
    stream = self.sf.Consume('a')
    self.assertEqual(self.e1, stream.Next())
    self.assertEqual(e, stream.Next())
    self.assertEqual(self.e1, stream.Next())
    self.assertEqual(self.e3, stream.Next())

  def testAppendedJunkStore(self):
    """Tests reading from a data store that has appended junk."""
    self.sf.Produce([self.e1])
    # Purposely append junk to the data store
    with open(self.sf.buffer_file.data_path, 'a') as f:
      f.write('xxxxxxxx')
    self.sf.Produce([self.e2])
    self.sf.AddConsumer('a')
    stream = self.sf.Consume('a')
    self.assertEqual(self.e1, stream.Next())
    self.assertEqual(self.e2, stream.Next())

  def testTwoBufferEventStreams(self):
    """Tries creating two BufferEventStream objects for one Consumer."""
    self.sf.AddConsumer('a')
    stream1 = self.sf.Consume('a')
    stream2 = self.sf.Consume('a')
    self.assertIsInstance(stream1, plugin_base.BufferEventStream)
    self.assertEqual(stream2, None)

  def testUseExpiredBufferEventStream(self):
    """Tests continuing to use an expired BufferEventStream."""
    self.sf.AddConsumer('a')
    stream = self.sf.Consume('a')
    stream.Commit()
    with self.assertRaises(plugin_base.EventStreamExpired):
      stream.Next()
    with self.assertRaises(plugin_base.EventStreamExpired):
      stream.Abort()
    with self.assertRaises(plugin_base.EventStreamExpired):
      stream.Commit()

  def testFirstLastSeq(self):
    """Checks the proper tracking of first_seq and last_seq."""
    self.assertEqual(self.sf.buffer_file.first_seq, 1)
    self.assertEqual(self.sf.buffer_file.last_seq, 0)

    first_seq, _ = self.sf.buffer_file._GetFirstUnconsumedRecord()
    self.assertEqual(first_seq, 1)

    self.sf.buffer_file.Truncate()
    self.assertEqual(self.sf.buffer_file.first_seq, 1)
    self.assertEqual(self.sf.buffer_file.last_seq, 0)

    first_seq, _ = self.sf.buffer_file._GetFirstUnconsumedRecord()
    self.assertEqual(first_seq, 1)

    self.sf.Produce([self.e1])
    self.assertEqual(self.sf.buffer_file.first_seq, 1)
    self.assertEqual(self.sf.buffer_file.last_seq, 1)

    first_seq, _ = self.sf.buffer_file._GetFirstUnconsumedRecord()
    self.assertEqual(first_seq, 2)

    self.sf.Produce([self.e1])
    self.assertEqual(self.sf.buffer_file.first_seq, 1)
    self.assertEqual(self.sf.buffer_file.last_seq, 2)

    first_seq, _ = self.sf.buffer_file._GetFirstUnconsumedRecord()
    self.assertEqual(first_seq, 3)

  def testTruncate(self):
    """Checks that Truncate truncates up to the last unread event."""
    self.sf.AddConsumer('a')
    self.assertEqual(self.sf.buffer_file.first_seq, 1)
    self.assertEqual(self.sf.buffer_file.last_seq, 0)

    self.sf.Produce([self.e1, self.e2])
    self.assertEqual(self.sf.buffer_file.first_seq, 1)
    self.assertEqual(self.sf.buffer_file.last_seq, 2)

    self.sf.buffer_file.Truncate()
    self.assertEqual(self.sf.buffer_file.first_seq, 1)
    self.assertEqual(self.sf.buffer_file.last_seq, 2)

    stream = self.sf.Consume('a')
    self.assertEqual(self.e1, stream.Next())
    stream.Commit()

    self.sf.buffer_file.Truncate()
    self.assertEqual(self.sf.buffer_file.first_seq, 2)
    self.assertEqual(self.sf.buffer_file.last_seq, 2)

  def testSeqOrder(self):
    """Checks that the order of sequence keys is consistent."""
    self.sf.AddConsumer('a')

    self.sf.buffer_file.Truncate()
    self.sf.Produce([self.e1])
    stream = self.sf.Consume('a')
    seq, _ = stream._Next()
    self.assertEqual(seq, 1)
    stream.Commit()

    self.sf.buffer_file.Truncate()
    self.sf.Produce([self.e1, self.e1])
    stream = self.sf.Consume('a')
    seq, _ = stream._Next()
    self.assertEqual(seq, 2)
    seq, _ = stream._Next()
    self.assertEqual(seq, 3)
    stream.Commit()

  @_WithBufferSize(0)  # Force only keeping one record in buffer.
  def testReloadBufferAfterTruncate(self):
    """Tests re-loading buffer of a BufferEventStream after Truncate."""
    self.sf.AddConsumer('a')
    self.sf.Produce([self.e1, self.e2, self.e3])
    stream1 = self.sf.Consume('a')
    self.assertEqual(self.e1, stream1.Next())
    stream1.Commit()
    stream2 = self.sf.Consume('a')
    # Explicitly check that stream2's buffer only contains one item.  This
    # means the buffer will need to be reloaded after the following sequence
    # of Next and Truncate.
    self.assertEqual(1, len(stream2._Buffer()))
    self.assertEqual(self.e2, stream2.Next())
    self.sf.buffer_file.Truncate()
    self.assertEqual(self.e3, stream2.Next())
    stream2.Commit()

  def testRecreateConsumer(self):
    """Tests for same position after removing and recreating Consumer."""
    self.sf.Produce([self.e1, self.e2, self.e3])
    self.sf.AddConsumer('a')
    stream1 = self.sf.Consume('a')
    self.assertEqual(self.e1, stream1.Next())
    stream1.Commit()
    self.sf.RemoveConsumer('a')
    self.sf.AddConsumer('a')
    stream2 = self.sf.Consume('a')
    self.assertEqual(self.e2, stream2.Next())
    stream2.Commit()

  def testRecreateConsumerAfterTruncate(self):
    """Tests that recreated Consumer updates position after truncate."""
    self.sf.Produce([self.e1, self.e2, self.e3])

    self.sf.AddConsumer('a')
    stream1 = self.sf.Consume('a')
    self.assertEqual(self.e1, stream1.Next())
    stream1.Commit()
    self.sf.RemoveConsumer('a')

    self.sf.AddConsumer('b')
    stream2 = self.sf.Consume('b')
    self.assertEqual(self.e1, stream2.Next())
    self.assertEqual(self.e2, stream2.Next())
    stream2.Commit()

    self.sf.buffer_file.Truncate()
    # Verify that the metadata is consistent after running Truncate.
    self.sf.SetUp()

    self.sf.AddConsumer('a')
    stream3 = self.sf.Consume('a')
    # Skips self.e2, since Truncate occurred while Consumer 'a' did not exist.
    self.assertEqual(self.e3, stream3.Next())
    stream3.Commit()

  def testMultiThreadProduce(self):
    """Tests for correct output with multiple threads Producing events."""
    random.seed(0)
    def ProducerThread():
      # Random sleep so that each thread produce isn't in sync.
      time.sleep(random.randrange(3) * 0.1)
      for unused_i in range(10):
        self.sf.Produce([self.e1, self.e2, self.e3])
    threads = []
    for unused_i in range(10):
      t = threading.Thread(target=ProducerThread)
      threads.append(t)
      t.start()
    for t in threads:
      t.join()

    # 10 threads, 10 * 3 events each = expected 300 events, 100 of each type.
    self.sf.AddConsumer('a')
    stream = self.sf.Consume('a')
    cur_seq = 1
    record_count = collections.defaultdict(int)
    while True:
      seq, record = stream._Next()
      if not seq:
        break
      # Make sure the sequence numbers are correct.
      self.assertEqual(cur_seq, seq)
      cur_seq += 1
      record_count[record] += 1
    self.assertEqual(3, len(record_count))
    self.assertTrue(all([x == 100 for x in record_count.values()]))

  @_WithBufferSize(80)  # Each line is around ~35 characters.
  def testMultiThreadConsumeTruncate(self):
    """Tests multiple Consumers reading simultaneously when Truncate occurs."""
    record_count_queue = queue.Queue()
    def ConsumerThread(consumer_id):
      stream = self.sf.Consume(consumer_id)
      record_count = collections.defaultdict(int)
      count = 0
      while True:
        # Commit and start a new BufferEventStream every 10 events.
        if count % 10 == 0:
          logging.info('Committing after 10 events...')
          stream.Commit()
          stream = self.sf.Consume(consumer_id)
        event = stream.Next()
        if not event:
          break
        record_count[repr(event.payload)] += 1
        count += 1
      stream.Commit()
      record_count_queue.put(record_count)

    self.sf.Produce([self.e1, self.e2, self.e3] * 25)
    for i in range(2):
      self.sf.AddConsumer(str(i))

    threads = []
    for i in range(2):
      t = threading.Thread(target=ConsumerThread, args=(str(i),))
      threads.append(t)
      t.start()

    for t in threads:
      while t.isAlive():
        # Add a small sleep to prevent occupying read_lock
        time.sleep(0.01)
        self.sf.buffer_file.Truncate()
      t.join()
    self.sf.buffer_file.Truncate()
    self.assertEqual(25 * 3 + 1, self.sf.buffer_file.first_seq)

    while not record_count_queue.empty():
      record_count = record_count_queue.get()
      self.assertEqual(3, len(record_count))
      self.assertTrue(all([x == 25 for x in record_count.values()]))

  def _CountAttachmentsInBuffer(self, sf):
    return len(os.listdir(sf.buffer_file.attachments_dir))

  def _TestAttachment(self, with_copy):
    """Helper function to test basic attachment functionality."""
    FILE_STRING = 'Hello World!'
    self._CreateBuffer({'copy_attachments': with_copy})
    with file_utils.UnopenedTemporaryFile() as path:
      with open(path, 'w') as f:
        f.write(FILE_STRING)
      self.assertTrue(os.path.isfile(path))
      event = datatypes.Event({}, {'a': path})
      self.assertEqual(True, self.sf.Produce([event]))
      self.assertTrue(os.path.isfile(path) == with_copy)

      # Get the event out of buffer to verify that the internal
      # attachment exists.
      self.sf.AddConsumer('a')
      stream = self.sf.Consume('a')
      internal_event = stream.Next()
      internal_path = internal_event.attachments['a']
      self.assertEqual(FILE_STRING, file_utils.ReadFile(internal_path))
      # Ensure that an absolute path is returned.
      self.assertTrue(internal_path.startswith('/'))
      self.assertEqual(1, self._CountAttachmentsInBuffer(self.sf))

  def testCopyAttachment(self):
    """Tests that an attachment is properly copied into the buffer state."""
    self._TestAttachment(True)

  def testMoveAttachment(self):
    """Tests that an attachment is properly moved into the buffer state."""
    self._TestAttachment(False)

  def testNonExistentAttachment(self):
    """Tests behaviour when a non-existent attachment is provided."""
    event = datatypes.Event({}, {'a': '/tmp/non_existent_file'})
    self.assertEqual(False, self.sf.Produce([event]))
    self.assertEqual(0, self._CountAttachmentsInBuffer(self.sf))

  def testPartFailMoveAttachmentTwoEvents(self):
    """Tests moving two attachments in separate events (real and fake)."""
    self._CreateBuffer({'copy_attachments': False})
    with file_utils.UnopenedTemporaryFile() as path:
      real_event = datatypes.Event({}, {'a': path})
      fake_event = datatypes.Event({}, {'a': '/tmp/non_existent_file'})
      self.assertEqual(False, self.sf.Produce([real_event, fake_event]))
      # Make sure source file still exists since Produce failed.
      self.assertTrue(os.path.isfile(path))
      # Make sure attachments_dir is empty.
      self.assertEqual(0, self._CountAttachmentsInBuffer(self.sf))

  def testPartFailMoveAttachmentOneEvent(self):
    """Tests moving two attachments in a single event (real and fake)."""
    self._CreateBuffer({'copy_attachments': False})
    with file_utils.UnopenedTemporaryFile() as path:
      event = datatypes.Event({}, {
          'a': path,
          'b': '/tmp/non_existent_file'})
      self.assertEqual(False, self.sf.Produce([event]))
      # Make sure source file still exists since Produce failed.
      self.assertTrue(os.path.isfile(path))
      # Make sure attachments_dir is empty.
      self.assertEqual(0, self._CountAttachmentsInBuffer(self.sf))

  def testTruncateAttachments(self):
    """Tests that truncate removes attachments of truncated events."""
    FILE_STRING = 'Hello World!'
    with file_utils.UnopenedTemporaryFile() as path:
      with open(path, 'w') as f:
        f.write(FILE_STRING)
      event = datatypes.Event({}, {'a': path})
      self.sf.Produce([event])
    self.assertEqual(1, self._CountAttachmentsInBuffer(self.sf))
    self.sf.buffer_file.Truncate(truncate_attachments=False)
    self.assertEqual(1, self._CountAttachmentsInBuffer(self.sf))
    self.sf.buffer_file.Truncate()
    self.assertEqual(0, self._CountAttachmentsInBuffer(self.sf))


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
