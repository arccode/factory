# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""File-based buffer common.

A file-based buffer which writes its events to a single file on disk, and
separately maintains metadata.

There are three files maintained, plus one for each consumer created:

  data.json:

    Stores actual data.  Each line corresponds to one event.  As events are
    written to disk, each one is given a sequence number.  Format of each line:

        [SEQ_NUM, {EVENT_DATA}, CRC_SUM]

    Writing SEQ_NUM to data.json is not strictly necessary since we keep track
    of sequence numbers in metadata, but it is useful for debugging, and could
    also help when restoring a corrupt database.

  metadata.json:

    Stores current sequence numbers and cursor positions.  The "first seq" and
    "start pos" are taken to be absolute to the original untruncated data file,
    and refer to the beginning of data currently stored on disk.

    So if seq=1 was consumed by all Consumers, and Truncate removed it from
    disk, first_seq would be set to 2.

    Note that since the cursor positions are absolute, start_pos must be
    subtracted to get the actual position in the file on disk, e.g.:

        f.seek(current_pos - start_pos)

  consumers.json:

    Stores a list of all active Consumers.  If a Consumer is removed, it will be
    removed from this list, but its metadata file will continue to exist.  If it
    is ever re-created, the existing metadata will be used.  If this is
    undesired behaviour, the metadata file for that Consumer should be manually
    deleted.

  consumer_X.json:

    Stores the sequence number and cursor position of a particular Consumer.


Versioning:

  Another concept that is worth explaining separately is "versioning".  We want
  to support truncating, that is, when our file contains N records which have
  already been consumed by all Consumers, and M remaining records, remove the
  first N records from the main data file in order to save disk space.  After
  rewriting the data file, update metadata accordingly.

  But what happens if a failure occurs in between these two steps?  Our "old"
  metadata now is now paired with a "new" data file, which means we will likely
  be unable to read anything properly.

  To solve this problem, before re-writing the main data file, we save a
  metadata file to disk with both "old" and "new" metadata versions *before*
  performing a truncate on the main data file.  The key is a CRC hash of the
  first line of the main data file.  When the buffer first starts, it will check
  to see which key matches the first line, and it will use this metadata
  version.

  Thus, if a failure occurs *before* writing the main data file, the "old"
  metadata can be used.  If a failure occurs *after* writing the main data file,
  the "new" metadata can be used.
"""

from __future__ import print_function

import json
import logging
import os
import shutil
import threading
import zlib

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import log_utils
from instalog import plugin_base
from instalog.utils import file_utils


# The number of bytes to buffer when retrieving events from a file.
_BUFFER_SIZE_BYTES = 4 * 1024  # 4kb


class SimpleFileException(Exception):
  """General exception type for this plugin."""
  pass


def GetChecksum(data):
  """Generates an 8-character CRC32 checksum of given string."""
  return '{:08x}'.format(abs(zlib.crc32(data)))


def TryLoadJSON(path, logger=logging):
  """Attempts to load JSON from the given file.

  Returns:
    Parsed data from the file.  None if the file does not exist.

  Raises:
    Exception if there was some other problem reading the file, or if something
    went wrong parsing the data.
  """
  if not os.path.isfile(path):
    logger.info('%s: does not exist', path)
    return None
  try:
    with open(path, 'r') as f:
      return json.load(f)
  except Exception:
    logger.exception('%s: Error reading disk or loading JSON', path)
    raise


def CopyAttachmentsToTempDir(att_paths, tmp_dir):
  """Copys attachments to the temporary directory."""
  try:
    for att_path in att_paths:
      # Check that the source file exists.
      if not os.path.isfile(att_path):
        raise ValueError('Attachment path `%s` specified in event does not '
                         'exist' % att_path)
      target_path = os.path.join(tmp_dir, att_path.replace('/', '_'))
      logging.debug('Copying attachment: %s --> %s',
                    att_path, target_path)
      with open(target_path, 'w') as dst_f:
        with open(att_path, 'r') as src_f:
          shutil.copyfileobj(src_f, dst_f)
        # Fsync the file and the containing directory to make sure it
        # is flushed to disk.
        dst_f.flush()
        os.fdatasync(dst_f)
    # Fsync the containing directory to make sure all attachments are flushed
    # to disk.
    dirfd = os.open(tmp_dir, os.O_DIRECTORY)
    os.fsync(dirfd)
    os.close(dirfd)
    return True
  except Exception:
    logging.exception('Exception encountered when copying attachments')
    return False


class BufferFile(log_utils.LoggerMixin):

  def __init__(self, args, logger, data_dir):
    """Sets up the plugin."""
    self.args = args
    self.logger = logger
    self.data_dir = data_dir

    self.data_path = os.path.join(
        data_dir, 'data.json')
    self.metadata_path = os.path.join(
        data_dir, 'metadata.json')
    self.consumers_list_path = os.path.join(
        data_dir, 'consumers.json')
    self.consumer_path_format = os.path.join(
        data_dir, 'consumer_%s.json')
    self.attachments_dir = os.path.join(
        data_dir, 'attachments')
    if not os.path.exists(self.attachments_dir):
      os.makedirs(self.attachments_dir)

    # Lock for writing to the self.data_path file.  Used by
    # Produce and Truncate.
    self.data_write_lock = threading.Lock()

    # Lock for modifying the self.consumers variable or for
    # preventing other threads from changing it.
    self._consumer_lock = threading.Lock()
    self.consumers = {}

    self.old_version = None
    self.old_first_seq = None
    self.old_last_seq = None
    self.old_start_pos = None
    self.old_end_pos = None

    self.version = None
    self.first_seq = 1
    self.last_seq = 0
    self.start_pos = 0
    self.end_pos = 0

    # Try restoring metadata, if it exists.
    self._RestoreMetadata()
    if self.version:
      self._SaveMetadata()
    self._RestoreConsumers()

    # Try truncating any attachments from any partial Truncate operations.
    self._TruncateAttachments()

  def _SaveMetadata(self):
    """Writes metadata of main database to disk."""
    if not self.version:
      raise SimpleFileException('No `version` available for SaveMetadata')
    data = {self.version: {
        'first_seq': self.first_seq,
        'last_seq': self.last_seq,
        'start_pos': self.start_pos,
        'end_pos': self.end_pos}}
    if self.old_version:
      data[self.old_version] = {
          'first_seq': self.old_first_seq,
          'last_seq': self.old_last_seq,
          'start_pos': self.old_start_pos,
          'end_pos': self.old_end_pos}
    self.old_version = None
    with file_utils.AtomicWrite(self.metadata_path, fsync=True) as f:
      json.dump(data, f)

  def _RestoreMetadata(self):
    """Restores metadata for main data file from disk.

    If the metadata file does not exist, will silently return.
    """
    data = TryLoadJSON(self.metadata_path, self.logger)
    if data is not None:
      try:
        self._RestoreVersionFromDisk()
      except Exception:
        self.error('Data file unexpectedly missing; resetting metadata')
        return
      if self.version not in data:
        self.error('Could not find metadata version %s (available: %s); '
                   'recovering metadata from data file',
                   self.version, ', '.join(data.keys()))
        self._RecoverMetadata()
        return
      if len(data) > 1:
        self.info('Metadata contains multiple versions %s; choosing %s',
                  ', '.join(data.keys()), self.version)
      self.first_seq = data[self.version]['first_seq']
      self.last_seq = data[self.version]['last_seq']
      self.start_pos = data[self.version]['start_pos']
      self.end_pos = data[self.version]['end_pos']
      # Check that end_pos <= start_pos + size of data_path.
      if self.end_pos > self.start_pos + os.path.getsize(self.data_path):
        self.error('end_pos in restored metadata is larger than start_pos + '
                   'data file; recovering metadata from data file')
        self._RecoverMetadata()

  def _RecoverMetadata(self):
    """Recovers metadata from the main data file on disk.

    Uses the first valid record for first_seq and start_pos, and the last
    valid record for last_seq and end_pos.
    """
    first_record = False
    cur_pos = 0
    with open(self.data_path, 'r') as f:
      for line in f:
        seq, _unused_record = self.ParseRecord(line)
        if not first_record and seq:
          self.first_seq = seq
          self.start_pos = cur_pos
          first_record = True
        cur_pos += len(line)
        if seq:
          self.last_seq = seq
          self.end_pos = cur_pos
    self.info('Finished recovering metadata; sequence range found: %d to %d',
              self.first_seq, self.last_seq)

  def _SaveConsumers(self):
    """Saves the current list of active Consumers to disk."""
    with file_utils.AtomicWrite(self.consumers_list_path, fsync=True) as f:
      json.dump(self.consumers.keys(), f)

  def _RestoreConsumers(self):
    """Restore Consumers from disk.

    Creates a corresponding Consumer object for each Consumer listed on disk.
    Only ever called when the buffer first starts up, so we don't need to
    check for any existing Consumers in self.consumers.
    """
    data = TryLoadJSON(self.consumers_list_path, self.logger)
    if data:
      for name in data:
        self.consumers[name] = self._CreateConsumer(name)

  def _RestoreVersionFromDisk(self):
    """Restores version from the main data file on disk.

    See file-level docstring for more information about versions.

    Raises:
      Exception if the file could not be opened or read correctly.
    """
    with open(self.data_path, 'r') as f:
      self._StoreVersion(f.readline())

  def _StoreVersion(self, first_line):
    """Calculates version from the given string and saves to self.version.

    See file-level docstring for more information about versions.
    """
    self.version = GetChecksum(first_line)

  def _FormatRecord(self, seq, record):
    """Returns a record formatted as a line to be written to disk."""
    data = '%d, %s' % (seq, record)
    checksum = GetChecksum(data)
    return '[%s, %s]\n' % (data, checksum)

  def ParseRecord(self, line):
    """Parses and returns a line from disk as a record.

    Returns:
      A tuple of (seq_number, record), or None on failure.
    """
    line_inner = line.rstrip()[1:-1]  # Strip [] and newline
    data, _, checksum = line_inner.rpartition(', ')
    seq, _, record = data.partition(', ')
    if not seq or not record:
      self.warning('Parsing error for record %s', line.rstrip())
      return None, None
    if checksum != GetChecksum(data):
      self.warning('Checksum error for record %s', line.rstrip())
      return None, None
    return int(seq), record

  def _TruncateAttachments(self):
    """Deletes attachments of events no longer stored within data.json."""
    for fname in os.listdir(self.attachments_dir):
      fpath = os.path.join(self.attachments_dir, fname)
      if not os.path.isfile(fpath):
        continue
      seq, _unused_underscore, _att_id = fname.partition('_')
      if not seq.isdigit():
        continue
      if int(seq) < self.first_seq or int(seq) > self.last_seq:
        self.debug('Truncating attachment (<seq=%d or >seq=%d): %s',
                   self.first_seq, self.last_seq, fname)
        os.unlink(fpath)

  def ExternalizeEvent(self, event):
    """Modifies attachment paths of given event to be absolute."""
    for att_id in event.attachments.keys():
      # Reconstruct the full path to the attachment on disk.
      event.attachments[att_id] = os.path.abspath(os.path.join(
          self.attachments_dir, event.attachments[att_id]))
    return event

  def ProduceEvents(self, events):
    """Moves attachments, serializes events and writes them to the data_path."""
    with self.data_write_lock:
      # Truncate the size of the file in case of a previously unfinished
      # transaction.
      with open(self.data_path, 'a') as f:
        f.truncate(self.end_pos - self.start_pos)

      cur_seq = self.last_seq + 1
      cur_pos = self.end_pos - self.start_pos
      with open(self.data_path, 'a') as f:
        # On some machines, the file handle offset isn't set to EOF until
        # a write occurs.  Thus we must manually seek to the end to ensure
        # that f.tell() will return useful results.
        f.seek(0, 2)  # 2 means use EOF as the reference point.
        assert f.tell() == cur_pos
        for event in events:
          for att_id, att_path in event.attachments.iteritems():
            target_name = '%s_%s' % (cur_seq, att_id)
            target_path = os.path.join(self.attachments_dir, target_name)
            event.attachments[att_id] = target_name
            self.debug('Relocating attachment %s: %s --> %s',
                       att_id, att_path, target_path)
            # Note: This could potentially overwrite an existing file that got
            # written just before Instalog process stopped unexpectedly.
            os.rename(att_path, target_path)

          self.debug('Writing event with cur_seq=%d, cur_pos=%d',
                     cur_seq, cur_pos)
          output = self._FormatRecord(cur_seq, event.Serialize())

          # Store the version for SaveMetadata to use.
          if cur_pos == 0:
            self._StoreVersion(output)

          f.write(output)
          cur_seq += 1
          cur_pos += len(output)

        if self.args.enable_fsync:
          # Fsync the file and the containing directory to make sure it
          # is flushed to disk.
          f.flush()
          os.fdatasync(f)
          dirfd = os.open(os.path.dirname(self.data_path), os.O_DIRECTORY)
          os.fsync(dirfd)
          os.close(dirfd)
      self.last_seq = cur_seq - 1
      self.end_pos = self.start_pos + cur_pos
      self._SaveMetadata()

  def _GetFirstUnconsumedRecord(self):
    """Returns the seq and pos of the first unprocessed record.

    Checks each Consumer to find the earliest unprocessed record, and returns
    that record's seq and pos.
    """
    min_seq = self.last_seq + 1
    min_pos = self.end_pos
    for consumer in self.consumers.values():
      min_seq = min(min_seq, consumer.cur_seq)
      min_pos = min(min_pos, consumer.cur_pos)
    return min_seq, min_pos

  def Truncate(self, _truncate_attachments=True):
    """Truncates the main data file to only contain unprocessed records.

    See file-level docstring for more information about versions.

    Args:
      _truncate_attachments: Whether or not to truncate attachments.
                             For testing.
    """
    with self.data_write_lock, self._consumer_lock:
      # Does the buffer already have data in it?
      if not self.version:
        return
      try:
        for consumer in self.consumers.values():
          consumer.read_lock.acquire()
        min_seq, min_pos = self._GetFirstUnconsumedRecord()
        self.debug('Will truncate up until seq=%d, pos=%d', min_seq, min_pos)

        # Prepare the old vs. new metadata to write to disk.
        self.old_version = self.version
        self.old_first_seq = self.first_seq
        self.old_last_seq = self.last_seq
        self.old_start_pos = self.start_pos
        self.old_end_pos = self.end_pos
        self.first_seq = min_seq
        self.start_pos = min_pos

        with file_utils.AtomicWrite(self.data_path, fsync=True) as new_f:
          # AtomicWrite opens a file handle to a temporary file right next to
          # the real file (self.data_path), so we can open a "read" handle on
          # self.data_path without affecting AtomicWrite's handle.  Only when
          # AtomicWrite's context block ends will the temporary be moved to
          # replace self.data_path.
          with open(self.data_path, 'r') as old_f:
            old_f.seek(min_pos - self.old_start_pos)

            # Deal with the first line separately to get the new version.
            first_line = old_f.readline()
            self._StoreVersion(first_line)
            new_f.write(first_line)

            shutil.copyfileobj(old_f, new_f)

          # Before performing the "replace" step of write-replace (when
          # the file_utils.AtomicWrite context ends), save metadata to disk in
          # case of disk failure.
          self._SaveMetadata()

        # Now that we have written the new data and metadata to disk, remove any
        # unused attachments.
        if _truncate_attachments:
          self._TruncateAttachments()

      except Exception:
        self.exception('Exception occurred during Truncate operation')
        # If any exceptions occurred, restore metadata, to make sure we are
        # using the correct version, since we aren't sure if the write succeeded
        # or not.
        self._RestoreMetadata()
        raise
      finally:
        # Ensure that regardless of any errors, locks are released.
        for consumer in self.consumers.values():
          try:
            consumer.read_lock.release()
          except Exception:
            pass

  def _CreateConsumer(self, name):
    """Returns a new Consumer object with the given name."""
    return Consumer(name, self, self.consumer_path_format % name, self.logger)

  def AddConsumer(self, name):
    """See BufferPlugin.AddConsumer."""
    self.debug('Add consumer %s', name)
    with self._consumer_lock:
      if name in self.consumers:
        raise SimpleFileException('Consumer %s already exists' % name)
      self.consumers[name] = self._CreateConsumer(name)
      self._SaveConsumers()

  def RemoveConsumer(self, name):
    """See BufferPlugin.RemoveConsumer."""
    self.debug('Remove consumer %s', name)
    with self._consumer_lock:
      if name not in self.consumers:
        raise SimpleFileException('Consumer %s does not exist' % name)
      del self.consumers[name]
      self._SaveConsumers()

  def ListConsumers(self):
    """See BufferPlugin.ListConsumers."""
    with self._consumer_lock:
      # cur_seq represents the sequence ID of the consumer's next event.  If
      # that event doesn't exist yet, it will be set to the next (non-existent)
      # sequence ID.  We must subtract 1 to get the "last completed" event.
      cur_seqs = {key: consumer.cur_seq - 1
                  for key, consumer in self.consumers.iteritems()}
      # Grab last_seq at the end, in order to guarantee that for any consumer,
      # last_seq >= cur_seq, and that all last_seq are equal.
      last_seq = self.last_seq
      return {key: (cur_seq, last_seq)
              for key, cur_seq in cur_seqs.iteritems()}

  def Consume(self, name):
    """See BufferPlugin.Consume."""
    return self.consumers[name].CreateStream()


class Consumer(log_utils.LoggerMixin, plugin_base.BufferEventStream):
  """Represents a Consumer and its BufferEventStream.

  Since SimpleFile has only a single database file, there can only ever be one
  functioning BufferEventStream at any given time.  So we bundle the Consumer
  and its BufferEventStream into one object.  When CreateStream is called, a
  lock is acquired and the Consumer object is return.  The lock must first be
  acquired before any of Next, Commit, or Abort can be used.
  """

  def __init__(self, name, simple_file, metadata_path, logger):
    self.name = name
    self.simple_file = simple_file
    self.metadata_path = metadata_path
    self.logger = logger

    self._lock = threading.Lock()
    self.read_lock = threading.Lock()
    self.read_buf = []

    self.cur_seq = simple_file.first_seq
    self.cur_pos = simple_file.start_pos
    self.new_seq = self.cur_seq
    self.new_pos = self.cur_pos

    # Try restoring metadata, if it exists.
    self._RestoreMetadata()
    self._SaveMetadata()

  def CreateStream(self):
    """Creates a BufferEventStream object to be used by Instalog core.

    Since this class doubles as BufferEventStream, we mark that the
    BufferEventStream is "unexpired" by setting self._lock, and return self.

    Returns:
      `self` if BufferEventStream not already in use, None if busy.
    """
    return self if self._lock.acquire(False) else None

  def _SaveMetadata(self):
    """Saves metadata for this Consumer to disk (seq and pos)."""
    data = {'cur_seq': self.cur_seq,
            'cur_pos': self.cur_pos}
    with file_utils.AtomicWrite(self.metadata_path, fsync=True) as f:
      json.dump(data, f)

  def _RestoreMetadata(self):
    """Restores metadata for this Consumer from disk (seq and pos).

    On each restore, ensure that the available window of records on disk has
    not surpassed our own current record.  How would this happen?  If the
    Consumer is removed, records it still hasn't read are truncated from the
    main database, and the Consumer is re-added under the same name.

    If the metadata file does not exist, will silently return.
    """
    data = TryLoadJSON(self.metadata_path, self.logger)
    if data is not None:
      if 'cur_seq' not in data or 'cur_pos' not in data:
        self.error('Consumer %s metadata file invalid; resetting', self.name)
        return
      # Make sure we are still ahead of simple_file.
      self.cur_seq = min(max(self.simple_file.first_seq, data['cur_seq']),
                         self.simple_file.last_seq + 1)
      self.cur_pos = min(max(self.simple_file.start_pos, data['cur_pos']),
                         self.simple_file.end_pos)
      if (data['cur_seq'] < self.simple_file.first_seq or
          data['cur_seq'] > (self.simple_file.last_seq + 1)):
        self.error('Consumer %s cur_seq=%d is out of buffer range %d to %d, '
                   'correcting to %d', self.name, data['cur_seq'],
                   self.simple_file.first_seq, self.simple_file.last_seq + 1,
                   self.cur_seq)
      self.new_seq = self.cur_seq
      self.new_pos = self.cur_pos

  def _Buffer(self):
    """Returns a list of pending records.

    Stores the current buffer internally at self.read_buf.  If it already has
    data in it, self.read_buf will be returned as-is.  It will be "refilled"
    when it is empty.

    Reads up to _BUFFER_SIZE_BYTES from the file on each "refill".

    Returns:
      A list of records, where each is a three-element tuple:
        (record_seq, record_data, line_bytes).
    """
    if self.read_buf:
      return self.read_buf
    # Does the buffer already have data in it?
    if not self.simple_file.version:
      return self.read_buf
    self.debug('_Buffer: waiting for read_lock')
    with self.read_lock:
      with open(self.simple_file.data_path, 'r') as f:
        cur = self.new_pos - self.simple_file.start_pos
        f.seek(cur)
        total_bytes = 0
        skipped_bytes = 0
        for line in f:
          if total_bytes > _BUFFER_SIZE_BYTES:
            break
          size = len(line)
          cur += size
          if cur > (self.simple_file.end_pos - self.simple_file.start_pos):
            break
          seq, record = self.simple_file.ParseRecord(line)
          if seq is None:
            # Parsing of this line failed for some reason.
            skipped_bytes += size
            continue
          # Only add to total_bytes for a valid line.
          total_bytes += size
          # Include any skipped bytes from previously skipped records in the
          # "size" of this record, in order to allow the consumer to skip to the
          # proper offset.
          self.read_buf.append((seq, record, size + skipped_bytes))
          skipped_bytes = 0
    return self.read_buf

  def _Next(self):
    """Helper for _Next, also used for testing purposes.

    Returns:
      A tuple of (seq, record), or (None, None) if no records available.
    """
    if not self._lock.locked():
      raise plugin_base.EventStreamExpired
    buf = self._Buffer()
    if not buf:
      return None, None
    seq, record, size = buf.pop(0)
    self.new_seq = seq + 1
    self.new_pos += size
    return seq, record

  def Next(self):
    """See BufferEventStream.Next."""
    seq, record = self._Next()
    if not seq:
      return None
    event = datatypes.Event.Deserialize(record)
    return self.simple_file.ExternalizeEvent(event)

  def Commit(self):
    """See BufferEventStream.Commit."""
    if not self._lock.locked():
      raise plugin_base.EventStreamExpired
    self.cur_seq = self.new_seq
    self.cur_pos = self.new_pos
    # Ensure that regardless of any errors, locks are released.
    try:
      self._SaveMetadata()
    except Exception:
      # TODO(kitching): Instalog core or PluginSandbox should catch this
      #                 exception and attempt to safely shut down.
      self.exception('Commit: Write exception occurred, Events may be '
                     'processed by output plugin multiple times')
    finally:
      try:
        self._lock.release()
      except Exception:
        # TODO(kitching): Instalog core or PluginSandbox should catch this
        #                 exception and attempt to safely shut down.
        self.exception('Commit: Internal error occurred')

  def Abort(self):
    """See BufferEventStream.Abort."""
    if not self._lock.locked():
      raise plugin_base.EventStreamExpired
    self.new_seq = self.cur_seq
    self.new_pos = self.cur_pos
    self.read_buf = []
    try:
      self._lock.release()
    except Exception:
      # TODO(kitching): Instalog core or PluginSandbox should catch this
      #                 exception and attempt to safely shut down.
      self.exception('Abort: Internal error occurred')
