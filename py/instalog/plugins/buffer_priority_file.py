#!/usr/bin/python2
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

from __future__ import print_function

import multiprocessing
import os
import shutil

import instalog_common  # pylint: disable=unused-import
from instalog import json_utils
from instalog import lock_utils
from instalog import log_utils
from instalog import plugin_base
from instalog.plugins import buffer_file_common
from instalog.utils.arg_utils import Arg
from instalog.utils import file_utils


_PRIORITY_LEVEL = 4
_LEVEL_FILE = 4
_LOCK_ACQUIRE_TIMEOUT = 0.1
_LOCK_ACQUIRE_LOOP_TIMES = 25  # emit timeout in
                               # (_LOCK_ACQUIRE_LOOP_TIMES * _LEVEL_FILE *
                               #  _LOCK_ACQUIRE_TIMEOUT) = 10sec
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
    self.buffer_file = [[[] for _unused_j in xrange(_LEVEL_FILE)]
                        for _unused_i in xrange(_PRIORITY_LEVEL)]
    self.attachments_tmp_dir = None
    self.metadata_tmp_dir = None

    self.consumers = {}
    self._file_num_lock = [None] * _LEVEL_FILE

    self.process_pool = None

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

    for pri_level in xrange(_PRIORITY_LEVEL):
      for file_num in xrange(_LEVEL_FILE):
        self.buffer_file[pri_level][file_num] = buffer_file_common.BufferFile(
            self.args,
            self.logger.name,
            os.path.join(self.GetDataDir(), '%d_%d' % (pri_level, file_num)))

    for file_num in xrange(_LEVEL_FILE):
      self._file_num_lock[file_num] = lock_utils.Lock()

    for name in self.buffer_file[0][0].consumers.keys():
      self.consumers[name] = Consumer(name, self)

    self.process_pool = multiprocessing.Pool(processes=_PROCESSES_NUMBER)

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
      self.Sleep(self.args.truncate_interval)

  def Truncate(self):
    """Truncates all data files to only contain unprocessed records."""
    for file_num in xrange(_LEVEL_FILE):
      with self._file_num_lock[file_num]:
        for pri_level in xrange(_PRIORITY_LEVEL):
          self.info('Truncating database %d_%d...', pri_level, file_num)
          self.buffer_file[pri_level][file_num].Truncate(
              process_pool=self.process_pool)
    self.info('Truncating complete.  Sleeping %d secs...',
              self.args.truncate_interval)

  def EventLevel(self, event):
    """Prioritizes the level of the event.

    Returns:
      An integer of priority level.
    """
    pri_levels = xrange(_PRIORITY_LEVEL)
    pri = event.get('priority')
    return pri if pri in pri_levels else _PRIORITY_LEVEL - 1

  def PrioritizeEvents(self, events):
    """Prioritizes the list of events, and seperates to several lists.

    Returns:
      A list of several lists, and each list has events in its priority level.
    """
    priority_events = [[] for _unused_i in xrange(_PRIORITY_LEVEL)]
    for event in events:
      priority_events[self.EventLevel(event)].append(event)
    return priority_events

  def SaveTemporaryMetadata(self, file_num):
    """Saves all metadatas to a temporary file, to prevent unexpected failures.

    Returns:
      The path of temporary metadata.
    """
    tmp_path = file_utils.CreateTemporaryFile()
    tmp_metadata_path = os.path.join(self.metadata_tmp_dir,
                                     os.path.basename(tmp_path))
    all_metadata = {}
    for pri_level in xrange(_PRIORITY_LEVEL):
      metadata_path = self.buffer_file[pri_level][file_num].metadata_path
      if os.path.isfile(metadata_path):
        all_metadata[metadata_path] = file_utils.ReadFile(metadata_path)
      else:
        all_metadata[metadata_path] = None
    with open(tmp_path, 'w') as f:
      f.write(json_utils.encoder.encode(all_metadata))
    file_utils.AtomicCopy(tmp_path, tmp_metadata_path)
    return tmp_metadata_path

  def RecoverTemporaryMetadata(self, tmp_metadata_path):
    """Recovers metadatas in the temporary file."""
    all_metadata = json_utils.decoder.decode(
        file_utils.ReadFile(tmp_metadata_path))
    for path, metadata in all_metadata.iteritems():
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
    for file_num in xrange(_LEVEL_FILE):
      if self._file_num_lock[file_num].acquire(block=False):
        return file_num
    for _unused_i in xrange(_LOCK_ACQUIRE_LOOP_TIMES):
      for file_num in xrange(_LEVEL_FILE):
        if self._file_num_lock[file_num].acquire(
            timeout=_LOCK_ACQUIRE_TIMEOUT):
          return file_num
    return False

  def Produce(self, events):
    """See BufferPlugin.Produce.

    Note the careful edge cases with attachment files.  We want them *all* to
    be either moved or copied into the buffer's database, or *none* at all.
    """
    file_num = False
    tmp_metadata_path = ''
    with file_utils.TempDirectory(dir=self.attachments_tmp_dir) as tmp_dir:
      try:
        # Step 1: Copy attachments.
        source_paths = []
        for event in events:
          for att_id, att_path in event.attachments.iteritems():
            source_paths.append(att_path)
            event.attachments[att_id] = os.path.join(
                tmp_dir, att_path.replace('/', '_'))
        if not self.process_pool.apply(
            buffer_file_common.CopyAttachmentsToTempDir,
            (source_paths, tmp_dir, self.logger.name)):
          return False

        # Step 2: Acquire a lock.
        file_num = self.AcquireLock()
        if file_num is False:
          return False

        tmp_metadata_path = self.SaveTemporaryMetadata(file_num)

        priority_events = self.PrioritizeEvents(events)
        # Step 3: Write the new events to the file.
        for pri_level in xrange(_PRIORITY_LEVEL):
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
          if file_num is not False:
            for pri_level in xrange(_PRIORITY_LEVEL):
              self.buffer_file[pri_level][file_num].RestoreMetadata()
        except Exception:
          self.exception('Exception encountered in RecoverTemporaryMetadata '
                         '(%s)', tmp_metadata_path)
        return False
      finally:
        if file_num is not False and self._file_num_lock[file_num].locked():
          self._file_num_lock[file_num].release()

  def AddConsumer(self, name):
    """See BufferPlugin.AddConsumer."""
    self.consumers[name] = Consumer(name, self)
    for pri_level in xrange(_PRIORITY_LEVEL):
      for file_num in xrange(_LEVEL_FILE):
        self.buffer_file[pri_level][file_num].AddConsumer(name)

  def RemoveConsumer(self, name):
    """See BufferPlugin.RemoveConsumer."""
    for pri_level in xrange(_PRIORITY_LEVEL):
      for file_num in xrange(_LEVEL_FILE):
        self.buffer_file[pri_level][file_num].RemoveConsumer(name)

  def ListConsumers(self):
    """See BufferPlugin.ListConsumers."""
    consumers_dict = {}
    for name in self.consumers.keys():
      consumers_dict[name] = (0, 0)
    for pri_level in xrange(_PRIORITY_LEVEL):
      for file_num in xrange(_LEVEL_FILE):
        progress_dict = self.buffer_file[pri_level][file_num].ListConsumers()
        for name, progress in progress_dict.iteritems():
          consumers_dict[name] = (consumers_dict[name][0] + progress[0],
                                  consumers_dict[name][1] + progress[1])
    return consumers_dict

  def Consume(self, name):
    """See BufferPlugin.Consume."""
    return self.consumers[name].CreateStream()


class Consumer(log_utils.LoggerMixin, plugin_base.BufferEventStream):
  """Represents a Consumer and its BufferEventStream."""

  def __init__(self, name, priority_buffer):
    self.name = name
    self.priority_buffer = priority_buffer
    self.streams = []

  def CreateStream(self):
    """Creates a BufferEventStream object to be used by Instalog core."""
    fail = False
    for pri_level in xrange(_PRIORITY_LEVEL):
      for file_num in xrange(_LEVEL_FILE):
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
    return self

  def Next(self):
    """See BufferEventStream.Next."""
    for stream in self.streams:
      event_or_none = stream.Next()
      if event_or_none is not None:
        return event_or_none
    return None

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