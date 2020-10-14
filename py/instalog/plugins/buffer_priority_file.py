#!/usr/bin/env python3
#
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Priority multi-file-based buffer.

A priority multi-file-based buffer plugin which seperates its events to several
priority and writes to different files. Every level has several files to avoid
that many input plugins require and wait the file lock.

This plugin is constructed by many simple file buffer, so the consumer of this
plugin has many consumers of simple file buffer.

Since this is a priority multi-file-based buffer plugin, it doesn't guarantee
the order of its events."""

import itertools
import multiprocessing
import os
import shutil

from cros.factory.instalog import json_utils
from cros.factory.instalog import lock_utils
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_base
from cros.factory.instalog.plugins import buffer_file_common
from cros.factory.instalog.utils.arg_utils import Arg
from cros.factory.instalog.utils import file_utils


_PRIORITY_LEVEL = 4
# emit timeout in 10 seconds =
# (_LOCK_ACQUIRE_LOOP_TIMES * _PARTITION * _LOCK_ACQUIRE_TIMEOUT)
_PARTITION = 4
_LOCK_ACQUIRE_TIMEOUT = 0.1
_LOCK_ACQUIRE_LOOP_TIMES = 25
_PROCESSES_NUMBER = 10
_TEMPORARY_METADATA_DIR = 'metadata_tmp_dir'
_TEMPORARY_ATTACHMENT_DIR = 'attachments_tmp_dir'
_DEFAULT_TRUNCATE_INTERVAL = 0  # truncating disabled
_DEFAULT_COPY_ATTACHMENTS = False  # use move instead of copy by default
_DEFAULT_ENABLE_FSYNC = True  # fsync when it receives events


class BufferPriorityFile(plugin_base.BufferPlugin):

  ARGS = [
      Arg('truncate_interval', (int, float),
          'How often truncating the buffer file should be attempted.  '
          'If set to 0, truncating functionality will be disabled (default).',
          default=_DEFAULT_TRUNCATE_INTERVAL),
      Arg('copy_attachments', bool,
          'Instead of moving an attachment into the buffer, perform a copy '
          'operation, and leave the source file intact.',
          default=_DEFAULT_COPY_ATTACHMENTS),
      Arg('enable_fsync', bool,
          'Synchronize the buffer file when it receives events.  '
          'Default is True.',
          default=_DEFAULT_ENABLE_FSYNC)
  ]

  def __init__(self, *args, **kwargs):
    self.buffer_file = [[[] for unused_j in range(_PARTITION)]
                        for unused_i in range(_PRIORITY_LEVEL)]
    self.attachments_tmp_dir = None
    self.metadata_tmp_dir = None

    self.consumers = {}
    self._file_num_lock = [None] * _PARTITION

    self.process_pool = None

    self._produce_partition = 0
    self._consume_partition = 0

    super(BufferPriorityFile, self).__init__(*args, **kwargs)

  def SetUp(self):
    """Sets up the plugin."""
    self.attachments_tmp_dir = os.path.join(self.GetDataDir(),
                                            _TEMPORARY_ATTACHMENT_DIR)
    # Remove the attachments tmp dir, if Instalog terminated last time.
    if os.path.exists(self.attachments_tmp_dir):
      shutil.rmtree(self.attachments_tmp_dir)
    os.makedirs(self.attachments_tmp_dir)

    self.metadata_tmp_dir = os.path.join(self.GetDataDir(),
                                         _TEMPORARY_METADATA_DIR)
    # Recover Temporary Metadata.
    if os.path.isdir(self.metadata_tmp_dir):
      for file_name in os.listdir(self.metadata_tmp_dir):
        file_path = os.path.join(self.metadata_tmp_dir, file_name)
        if os.path.isfile(file_path):
          self.RecoverTemporaryMetadata(file_path)
    else:
      os.makedirs(self.metadata_tmp_dir)

    for pri_level in range(_PRIORITY_LEVEL):
      for file_num in range(_PARTITION):
        self.buffer_file[pri_level][file_num] = buffer_file_common.BufferFile(
            self.args,
            self.logger.name,
            os.path.join(self.GetDataDir(), '%d_%d' % (pri_level, file_num)))

    for file_num in range(_PARTITION):
      self._file_num_lock[file_num] = lock_utils.Lock(self.logger.name)

    for name in self.buffer_file[0][0].consumers.keys():
      self.consumers[name] = Consumer(name, self)

    self.process_pool = multiprocessing.Pool(processes=_PROCESSES_NUMBER)

  def TearDown(self):
    """Tears down the plugin."""
    self.process_pool.close()
    self.info('Joining the processes in the process pool')
    self.process_pool.join()
    self.info('Finished joining the processes')

  def Main(self):
    """Main thread of the plugin."""
    while not self.IsStopping():
      if not self.args.truncate_interval:
        # Truncating is disabled.  But we should keep the main thread running,
        # or else PluginSandbox will assume the plugin has crashed, and will
        # take the plugin down.
        # TODO(kitching): Consider altering PluginSandbox to allow Main to
        #                 return some particular value which signifies "I am
        #                 exiting of my own free will and I should be allowed to
        #                 continue running normally."
        self.Sleep(100)
        continue

      self.Truncate()
      self.info('Truncating complete.  Sleeping %d secs...',
                self.args.truncate_interval // _PARTITION)
      self.Sleep(self.args.truncate_interval // _PARTITION)

  def ProduceOrderIter(self):
    """Returns a iterator to get produce order of partitioned buffers."""
    first_level = self._produce_partition
    self._produce_partition = (self._produce_partition + 1) % _PARTITION
    return itertools.chain(range(first_level, _PARTITION),
                           range(0, first_level))

  def ConsumeOrderIter(self):
    """Returns a iterator to get consume order of partitioned buffers."""
    first_level = self._consume_partition
    return itertools.chain(range(first_level, _PARTITION),
                           range(0, first_level))

  def Truncate(self):
    """Truncates all data files to only contain unprocessed records."""
    # A buffer can be truncated faster after it is consumed for a while.
    file_num = self._consume_partition
    self._consume_partition = (self._consume_partition + 1) % _PARTITION
    with self._file_num_lock[file_num]:  # pylint: disable=not-context-manager
      for pri_level in range(_PRIORITY_LEVEL):
        self.info('Truncating database %d_%d...', pri_level, file_num)
        self.buffer_file[pri_level][file_num].Truncate(
            process_pool=self.process_pool)

  def EventLevel(self, event):
    """Prioritizes the level of the event.

    Returns:
      An integer of priority level.
    """
    pri = event.get('priority')
    return pri if pri in range(_PRIORITY_LEVEL) else _PRIORITY_LEVEL - 1

  def PrioritizeEvents(self, events):
    """Prioritizes the list of events, and seperates to several lists.

    Returns:
      A list of several lists, and each list has events in its priority level.
    """
    priority_events = [[] for unused_i in range(_PRIORITY_LEVEL)]
    for event in events:
      priority_events[self.EventLevel(event)].append(event)
    return priority_events

  def SaveTemporaryMetadata(self, file_num):
    """Saves all metadatas to a temporary file, to prevent unexpected failures.

    Returns:
      The path of temporary metadata.
    """
    # We didn't use file_utils.AtomicWrite since it create another file on
    # self.metadata_tmp_dir.
    with file_utils.UnopenedTemporaryFile() as tmp_path:
      tmp_metadata_path = os.path.join(self.metadata_tmp_dir,
                                       os.path.basename(tmp_path))
      all_metadata = {}
      for pri_level in range(_PRIORITY_LEVEL):
        metadata_path = self.buffer_file[pri_level][file_num].metadata_path
        if os.path.isfile(metadata_path):
          all_metadata[metadata_path] = file_utils.ReadFile(metadata_path)
        else:
          all_metadata[metadata_path] = None
      with open(tmp_path, 'w') as f:
        f.write(json_utils.encoder.encode(all_metadata))
      file_utils.AtomicCopy(tmp_path, tmp_metadata_path)
      file_utils.SyncDirectory(self.metadata_tmp_dir)
    return tmp_metadata_path

  def RecoverTemporaryMetadata(self, tmp_metadata_path):
    """Recovers metadatas in the temporary file."""
    all_metadata = json_utils.decoder.decode(
        file_utils.ReadFile(tmp_metadata_path))
    for path, metadata in all_metadata.items():
      self.info('Recover metadata: `%s` New: `%s` Old: `%s`', path, metadata,
                file_utils.ReadFile(path) if os.path.exists(path) else 'None')
      if metadata is None:
        if os.path.isfile(path):
          os.unlink(path)
      else:
        with file_utils.AtomicWrite(path) as f:
          f.write(metadata)

    os.unlink(tmp_metadata_path)

  def AcquireLock(self):
    for file_num in self.ProduceOrderIter():
      if self._file_num_lock[file_num].acquire(block=False):
        return file_num
    for unused_i in range(_LOCK_ACQUIRE_LOOP_TIMES):
      for file_num in self.ProduceOrderIter():
        if self._file_num_lock[file_num].acquire(
            timeout=_LOCK_ACQUIRE_TIMEOUT):
          return file_num
    return False

  def Produce(self, events):
    """See BufferPlugin.Produce.

    Note the careful edge cases with attachment files.  We want them *all* to
    be either moved or copied into the buffer's database, or *none* at all.
    """
    file_num = None
    tmp_metadata_path = ''
    with file_utils.TempDirectory(dir=self.attachments_tmp_dir) as tmp_dir:
      try:
        # Step 1: Copy attachments.
        source_paths = []
        for event in events:
          for att_id, att_path in event.attachments.items():
            source_paths.append(att_path)
            event.attachments[att_id] = os.path.join(
                tmp_dir, att_path.replace('/', '_'))
        if not self.process_pool.apply(
            buffer_file_common.CopyAttachmentsToTempDir,
            (source_paths, tmp_dir, self.logger.name)):
          return False

        # Step 2: Acquire a lock.
        file_num = self.AcquireLock()
        if file_num is None:
          return False

        tmp_metadata_path = self.SaveTemporaryMetadata(file_num)

        priority_events = self.PrioritizeEvents(events)
        # Step 3: Write the new events to the file.
        for pri_level in range(_PRIORITY_LEVEL):
          if not priority_events[pri_level]:
            continue
          self.buffer_file[pri_level][file_num].ProduceEvents(
              priority_events[pri_level], self.process_pool)
        # Step 4: Remove source attachment files if necessary.
        if not self.args.copy_attachments:
          for path in source_paths:
            try:
              os.unlink(path)
            except Exception:
              self.exception('One of source attachment files (%s) could not be '
                             'deleted; silently ignoring', path)
        os.unlink(tmp_metadata_path)
        return True
      except Exception:
        self.exception('Exception encountered in Produce')
        try:
          if os.path.isfile(tmp_metadata_path):
            self.RecoverTemporaryMetadata(tmp_metadata_path)
          if file_num is not None:
            for pri_level in range(_PRIORITY_LEVEL):
              self.buffer_file[pri_level][file_num].RestoreMetadata()
        except Exception:
          self.exception('Exception encountered in RecoverTemporaryMetadata '
                         '(%s)', tmp_metadata_path)
        return False
      finally:
        if file_num is not None:
          self._file_num_lock[file_num].CheckAndRelease()

  def AddConsumer(self, consumer_id):
    """See BufferPlugin.AddConsumer."""
    self.consumers[consumer_id] = Consumer(consumer_id, self)
    for pri_level in range(_PRIORITY_LEVEL):
      for file_num in range(_PARTITION):
        self.buffer_file[pri_level][file_num].AddConsumer(consumer_id)

  def RemoveConsumer(self, consumer_id):
    """See BufferPlugin.RemoveConsumer."""
    for pri_level in range(_PRIORITY_LEVEL):
      for file_num in range(_PARTITION):
        self.buffer_file[pri_level][file_num].RemoveConsumer(consumer_id)

  def ListConsumers(self, details=0):
    """See BufferPlugin.ListConsumers."""
    consumers_dict = {}
    progress_dict = {}
    for name in self.consumers:
      progress_dict[name] = {}
      for pri_level in range(_PRIORITY_LEVEL):
        progress_dict[name][pri_level] = {}
        for file_num in range(_PARTITION):
          progress_dict[name][pri_level][file_num] = (
              self.buffer_file[pri_level][file_num].ListConsumers()[name])
          if details >= 2:
            consumers_dict['%s(%d-%d)' % (name, pri_level, file_num)] = (
                progress_dict[name][pri_level][file_num])
        progress_dict[name][pri_level] = tuple(
            map(sum, list(zip(*progress_dict[name][pri_level].values()))))
        if details == 1:
          consumers_dict['%s(%d)' % (name, pri_level)] = (
              progress_dict[name][pri_level])
      progress_dict[name] = tuple(
          map(sum, list(zip(*progress_dict[name].values()))))
      if details <= 0:
        consumers_dict[name] = progress_dict[name]
    return consumers_dict

  def Consume(self, consumer_id):
    """See BufferPlugin.Consume."""
    return self.consumers[consumer_id].CreateStream()


class Consumer(log_utils.LoggerMixin, plugin_base.BufferEventStream):
  """Represents a Consumer and its BufferEventStream."""

  def __init__(self, name, priority_buffer):
    self.name = name
    self.priority_buffer = priority_buffer
    self.streams = []
    self.streams_index = 0

  def CreateStream(self):
    """Creates a BufferEventStream object to be used by Instalog core."""
    fail = False
    for pri_level in range(_PRIORITY_LEVEL):
      for file_num in self.priority_buffer.ConsumeOrderIter():
        self.streams.append(
            self.priority_buffer.buffer_file[pri_level][file_num].consumers[
                self.name].CreateStream())
        if self.streams[-1] is None:
          self.streams.pop()
          fail = True
          break
      if fail:
        break

    if fail:
      for stream in self.streams:
        stream.Abort()
      self.streams = []
      return None
    self.streams_index = 0
    return self

  def _Next(self):
    """Helper for Next."""
    while self.streams_index < len(self.streams):
      event = self.streams[self.streams_index].Next()
      if event is not None:
        return event
      self.streams_index += 1
    return None

  def Next(self):
    """See BufferEventStream.Next."""
    event = self._Next()
    if event is not None:
      return event

    # If the streams_index is the end, we should check all buffer file again.
    self.streams_index = 0

    # If there's no more event in any buffer file, we can return None now.
    return self._Next()

  def Commit(self):
    """See BufferEventStream.Commit."""
    for stream in self.streams:
      stream.Commit()
    self.streams = []

  def Abort(self):
    """See BufferEventStream.Abort."""
    for stream in self.streams:
      stream.Abort()
    self.streams = []


if __name__ == '__main__':
  plugin_base.main()
