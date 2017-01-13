#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Output archive plugin.

An archive plugin to backup all events and their attachments to a tar.gz file.

The archive name:
  'InstalogEvents_' + year + month + day + hour + minute + second

The archive structure:
  InstalogEvents_YYYYmmddHHMMSS.tar.gz
    InstalogEvents_YYYYmmddHHMMSS/
      events.json
      attachments/  # Will not have this dir if no attachment.
        000/${ATTACHMENT000_NAME}
        001/${ATTACHMENT001_NAME}
        ...
"""

# TODO(kitching): Add a unittest.

from __future__ import print_function

import datetime
import os
import shutil
import StringIO
import tarfile
import time

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import plugin_base
from instalog.utils.arg_utils import Arg
from instalog.utils import file_utils
from instalog.utils import time_utils


_ARCHIVE_MESSAGE_INTERVAL = 15  # 15sec
_DEFAULT_INTERVAL = 1 * 60 * 60  # 1hr
_DEFAULT_MAX_SIZE = 200 * 1024 * 1024  # 200mb


class OutputArchive(plugin_base.OutputPlugin):

  ARGS = [
      Arg('interval', (int, float),
          'How long to wait, in seconds, before creating the next archive.',
          optional=True, default=_DEFAULT_INTERVAL),
      Arg('max_size', int,
          'If the total_size bigger than max_size, archive these events.',
          optional=True, default=_DEFAULT_MAX_SIZE),
      Arg('target_dir', (str, unicode),
          'The directory in which to store archives.  Uses the plugin\'s '
          'data directory by default.',
          optional=True, default=None),
      Arg('enable_disk', bool,
          'Whether or not to save the archive to disk.  True by default.',
          optional=True, default=True),
      Arg('enable_emit', bool,
          'Whether or not to emit the archive as an attachment of a new '
          'Instalog event.  False by default.',
          optional=True, default=False),
  ]

  def SetUp(self):
    """Sets up the plugin."""
    if not self.args.enable_disk and self.args.target_dir:
      raise ValueError('If specifying a `target_dir\', `enable_disk\' must '
                       'be set to True')
    if not self.args.enable_disk and not self.args.enable_emit:
      raise ValueError('Please enable at least one of `enable_disk\' or '
                       '`enable_emit\'')

    # If saving to disk, ensure that the target_dir exists.
    if self.args.enable_disk and self.args.target_dir is None:
      self.args.target_dir = self.GetDataDir()
    if self.args.target_dir and not os.path.isdir(self.args.target_dir):
      os.makedirs(self.args.target_dir)

  def Main(self):
    """Main thread of the plugin."""
    while not self.IsStopping():
      if not self.PrepareAndArchive():
        self.Sleep(1)

  def GetEventsTarInfo(self, name, size):
    """Makes the file info of events.json."""
    info = tarfile.TarInfo(name)
    info.size = size
    info.mtime = time.time()
    info.mode = 0644
    info.type = tarfile.REGTYPE
    return info

  def Archive(self, events):
    """Archives events."""
    serialized_events_buffer = StringIO.StringIO()
    att_count = 0

    cur_time = datetime.datetime.now()
    archive_name = cur_time.strftime('InstalogEvents_%Y%m%d%H%M%S')
    archive_filename = '%s.tar.gz' % archive_name
    with file_utils.UnopenedTemporaryFile(
        prefix='instalog_archive_') as tmp_path:
      self.info('Archiving %d events in %s', len(events), archive_name)
      with tarfile.open(tmp_path, 'w:gz') as tar:
        for event in events:
          for att_id, att_path in event.attachments.iteritems():
            if os.path.isfile(att_path):
              att_name = os.path.basename(att_path)
              att_newpath = 'attachments/%03d/%s' % (att_count, att_name)
              att_count += 1
              tar.add(att_path, arcname=os.path.join(archive_name, att_newpath))
              event.attachments[att_id] = att_newpath
          serialized_events_buffer.write(event.Serialize() + '\n')
        info = self.GetEventsTarInfo(os.path.join(archive_name, 'events.json'),
                                     serialized_events_buffer.len)
        serialized_events_buffer.seek(0)
        tar.addfile(info, serialized_events_buffer)

      # What should we do with the archive?
      if self.args.target_dir:
        target_path = os.path.join(self.args.target_dir, archive_filename)
        self.info('Saving archive to file %s', target_path)
        if self.args.enable_emit:
          # We still need the file for the emit() call.
          shutil.copyfile(tmp_path, target_path)
        else:
          # We don't need the file anymore, so use move.
          shutil.move(tmp_path, target_path)
      if self.args.enable_emit:
        self.info('Emitting event with attachment %s', archive_filename)
        event = datatypes.Event(
            {'__archive__': True, 'time': cur_time},
            {archive_filename: tmp_path})
        self.Emit([event])
    return True

  def PrepareAndArchive(self):
    """Retrieves events, and archives them."""
    event_stream = self.NewStream()
    if not event_stream:
      return False

    events = []
    time_last = time_utils.MonotonicTime()
    total_size = 0
    for event in event_stream.iter(timeout=self.args.interval):
      events.append(event)
      self.debug('len(events) = %d', len(events))
      total_size += len(event.Serialize())
      for att_id, att_path in event.attachments.iteritems():
        if os.path.isfile(att_path):
          total_size += os.path.getsize(att_path)

      time_now = time_utils.MonotonicTime()
      if (time_now - time_last) >= _ARCHIVE_MESSAGE_INTERVAL:
        time_last = time_now
        self.info('Currently at %.2f%% of %.2fMB before archiving',
                  100.0 * total_size / self.args.max_size,
                  self.args.max_size / 1024.0 / 1024)
      if total_size >= self.args.max_size:
        break

    # Commit these events.
    if len(events) == 0:
      event_stream.Commit()
      return False
    elif self.Archive(events):
      self.info('Commit %d events', len(events))
      event_stream.Commit()
      return True
    else:
      self.info('Abort %d events', len(events))
      event_stream.Abort()
      return False


if __name__ == '__main__':
  plugin_base.main()
