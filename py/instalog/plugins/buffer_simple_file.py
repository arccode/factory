#!/usr/bin/env python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Simple file-based buffer.

A simple buffer plugin which writes its events to a single file on disk, and
separately maintains metadata. See buffer_file_common.py for details.
"""

from __future__ import print_function

import os
import shutil

from six import iteritems

import instalog_common  # pylint: disable=unused-import
from instalog import plugin_base
from instalog.plugins import buffer_file_common
from instalog.utils.arg_utils import Arg
from instalog.utils import file_utils


_TEMPORARY_ATTACHMENT_DIR = 'attachments_tmp_dir'
_DEFAULT_TRUNCATE_INTERVAL = 0  # truncating disabled
_DEFAULT_COPY_ATTACHMENTS = False  # use move instead of copy by default
_DEFAULT_ENABLE_FSYNC = True  # fsync when it receives events


class BufferSimpleFile(plugin_base.BufferPlugin):

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
    self.buffer_file = None
    self.attachments_tmp_dir = None
    super(BufferSimpleFile, self).__init__(*args, **kwargs)

  def SetUp(self):
    """Sets up the plugin."""
    self.buffer_file = buffer_file_common.BufferFile(
        self.args, self.logger.name, self.GetDataDir())

    self.attachments_tmp_dir = os.path.join(self.GetDataDir(),
                                            _TEMPORARY_ATTACHMENT_DIR)
    # Remove the attachments tmp dir, if Instalog terminated last time.
    if os.path.exists(self.attachments_tmp_dir):
      shutil.rmtree(self.attachments_tmp_dir)
    file_utils.TryMakeDirs(self.attachments_tmp_dir)

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

      self.info('Truncating database...')
      self.buffer_file.Truncate()
      self.info('Truncating complete.  Sleeping %d secs...',
                self.args.truncate_interval)
      self.Sleep(self.args.truncate_interval)

  def Produce(self, events):
    """See BufferPlugin.Produce.

    Note the careful edge cases with attachment files.  We want them *all* to
    be either moved or copied into the buffer's database, or *none* at all.
    """
    with file_utils.TempDirectory(dir=self.attachments_tmp_dir) as tmp_dir:
      try:
        # Step 1: Copy attachments.
        source_paths = []
        for event in events:
          for att_id, att_path in iteritems(event.attachments):
            source_paths.append(att_path)
            event.attachments[att_id] = os.path.join(
                tmp_dir, att_path.replace('/', '_'))
        if not buffer_file_common.CopyAttachmentsToTempDir(
            source_paths, tmp_dir, self.logger.name):
          return False
        # Step 2: Write the new events to the file.
        self.buffer_file.ProduceEvents(events)
        # Step 3: Remove source attachment files if necessary.
        if not self.args.copy_attachments:
          for path in source_paths:
            try:
              os.unlink(path)
            except Exception:
              self.exception('Some of source attachment files (%s) could not '
                             'be deleted; silently ignoring', path)
        return True
      except Exception:
        self.exception('Exception encountered when producing events')
        return False

  def AddConsumer(self, name):
    """See BufferPlugin.AddConsumer."""
    self.buffer_file.AddConsumer(name)

  def RemoveConsumer(self, name):
    """See BufferPlugin.RemoveConsumer."""
    self.buffer_file.RemoveConsumer(name)

  def ListConsumers(self, details=0):
    """See BufferPlugin.ListConsumers."""
    del details
    return self.buffer_file.ListConsumers()

  def Consume(self, name):
    """See BufferPlugin.Consume."""
    return self.buffer_file.Consume(name)


if __name__ == '__main__':
  plugin_base.main()
