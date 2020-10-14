#!/usr/bin/env python3
#
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Output file plugin.

An output file plugin to save all events and their attachments to an
"events.json" file and an "attachments" directory.

The structure of data:
  ${target_dir}/
    events.json
    attachments/
      ${ATTACHMENT_0_HASH}
      ${ATTACHMENT_1_HASH}
      ${ATTACHMENT_2_HASH}
      ...
"""

import os
import shutil

from cros.factory.instalog import plugin_base
from cros.factory.instalog.utils.arg_utils import Arg
from cros.factory.instalog.utils import file_utils
from cros.factory.instalog.utils import time_utils


_PROCESS_MESSAGE_INTERVAL = 60  # 60sec
_DEFAULT_INTERVAL = 1 * 60 * 60  # 1hr
_DEFAULT_BATCH_SIZE = float('inf')  # Infinity. Only change when needed.
_DEFAULT_THRESHOLD_SIZE = 200 * 1024 * 1024  # 200mb
EVENT_FILE_NAME = 'events.json'
ATT_DIR_NAME = 'attachments'


def MoveAndMerge(src_dir, dst_dir):
  """Moves data files from src_dir and merges with data files on dst_dir"""
  file_utils.TryMakeDirs(os.path.join(dst_dir, ATT_DIR_NAME))

  for att_name in os.listdir(os.path.join(src_dir, ATT_DIR_NAME)):
    att_src_path = os.path.join(src_dir, ATT_DIR_NAME, att_name)
    att_dst_path = os.path.join(dst_dir, ATT_DIR_NAME, att_name)
    if not os.path.isfile(att_dst_path):
      shutil.move(att_src_path, att_dst_path)
  file_utils.SyncDirectory(os.path.join(dst_dir, ATT_DIR_NAME))

  with open(os.path.join(dst_dir, EVENT_FILE_NAME), 'a') as dst_f:
    with open(os.path.join(src_dir, EVENT_FILE_NAME), 'r') as src_f:
      shutil.copyfileobj(src_f, dst_f)
      dst_f.flush()
      os.fdatasync(dst_f.fileno())
  file_utils.SyncDirectory(dst_dir)


class OutputFile(plugin_base.OutputPlugin):

  ARGS = [
      Arg('interval', (int, float),
          'How long to wait, in seconds, before the next process.',
          default=_DEFAULT_INTERVAL),
      Arg('batch_size', (int, float),
          'How many events to queue before transmitting.',
          default=_DEFAULT_BATCH_SIZE),
      Arg('threshold_size', int,
          'If the total_size bigger than threshold_size, process these events.',
          default=_DEFAULT_THRESHOLD_SIZE),
      Arg('target_dir', str,
          'The directory in which to store files.  Uses the plugin\'s data '
          'directory by default.',
          default=None),
      Arg('exclude_history', bool,
          'To save the events without any ProcessStage.  Uses this argument if '
          'ProcessStage uses too much space.',
          default=False)
  ]

  def __init__(self, *args, **kwargs):
    super(OutputFile, self).__init__(*args, **kwargs)
    self.target_dir = None

  def SetUp(self):
    """Sets up the plugin."""
    # If saving to disk, ensure that the target_dir exists.
    if self.args.target_dir is None:
      self.target_dir = self.GetDataDir()
    else:
      if not os.path.isdir(self.args.target_dir):
        os.makedirs(self.args.target_dir)
      self.target_dir = self.args.target_dir

  def Main(self):
    """Main thread of the plugin."""
    while not self.IsStopping():
      if not self.PrepareAndProcess():
        self.Sleep(1)

  def PrepareEvent(self, event, base_dir):
    """Copies an event's attachments and returns its serialized form."""
    for att_id, att_path in event.attachments.items():
      if os.path.isfile(att_path):
        att_hash = file_utils.SHA1InHex(att_path)
        att_newpath = os.path.join(ATT_DIR_NAME, att_hash)
        shutil.copyfile(att_path, os.path.join(base_dir, att_newpath))
        event.attachments[att_id] = att_newpath
    return event.Serialize()

  def GetEventAttachmentSize(self, event):
    """Returns the total size of given event's attachments."""
    total_size = 0
    for _unused_att_id, att_path in event.attachments.items():
      if os.path.isfile(att_path):
        total_size += os.path.getsize(att_path)
    return total_size

  def ProcessEvents(self, base_dir):
    """Processes events which are saved on base_dir."""
    MoveAndMerge(base_dir, self.target_dir)
    return True

  def PrepareAndProcess(self):
    """Retrieves events, and processes them."""
    event_stream = self.NewStream()
    if not event_stream:
      return False

    with file_utils.TempDirectory(prefix='output_file_') as base_dir:
      self.debug('Creating temporary directory: %s', base_dir)
      # Create the attachments directory.
      att_dir = os.path.join(base_dir, ATT_DIR_NAME)
      os.mkdir(att_dir)

      # In order to save memory, write directly to a temp file on disk.
      with open(os.path.join(base_dir, EVENT_FILE_NAME), 'w') as events_f:
        num_events = 0
        total_size = 0
        time_last = time_utils.MonotonicTime()
        for event in event_stream.iter(timeout=self.args.interval,
                                       count=self.args.batch_size):
          if self.args.exclude_history:
            event.history = []
          serialized_event = self.PrepareEvent(event, base_dir)
          attachment_size = self.GetEventAttachmentSize(event)
          events_f.write(serialized_event + '\n')

          total_size += len(serialized_event) + attachment_size
          num_events += 1
          self.debug('num_events = %d', num_events)

          # Throttle our status messages.
          time_now = time_utils.MonotonicTime()
          if (time_now - time_last) >= _PROCESS_MESSAGE_INTERVAL:
            time_last = time_now
            self.info('Currently at %.2f%% of %.2fMB before processing',
                      100 * total_size / self.args.threshold_size,
                      self.args.threshold_size / 1024 / 1024)
          if total_size >= self.args.threshold_size:
            break

      if self.IsStopping():
        self.info('Plugin is stopping! Abort %d events', num_events)
        event_stream.Abort()
        return False

      if num_events == 0:
        self.debug('Commit 0 events')
        event_stream.Commit()
        return True
      if self.ProcessEvents(base_dir):
        self.info('Commit %d events', num_events)
        event_stream.Commit()
        return True
      self.info('Abort %d events', num_events)
      event_stream.Abort()
      return False

if __name__ == '__main__':
  plugin_base.main()
