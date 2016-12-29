#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Cloud Storage attachment upload output plugin."""

from __future__ import print_function

import instalog_common  # pylint: disable=W0611
from instalog import plugin_base
from instalog.utils.arg_utils import Arg
from instalog.utils import file_utils
from instalog.utils import gcs_utils


_DEFAULT_INTERVAL = 5


class OutputCloudStorage(plugin_base.OutputPlugin):

  ARGS = [
      Arg('interval', (int, float),
          'Frequency to re-emit events, if no attachments are encountered. '
          'When attachments are encountered, events are re-emitted right '
          'after upload.',
          optional=True, default=_DEFAULT_INTERVAL),
      Arg('key_path', (str, unicode),
          'Path to Cloud Storage service account JSON key file.',
          optional=False),
      Arg('target_dir', (str, unicode),
          'Path to the target bucket and directory on Google Cloud.',
          optional=False),
      Arg('use_sha1', bool,
          'Use the attachment\'s SHA1 hex-encoded hash as its filename.  '
          'Note that this means multiple attachments may point to the same '
          'file on Cloud Storage.  If set to False, the attachment ID will '
          'be used as its filename.',
          optional=True, default=False),
      Arg('enable_emit', bool,
          'Strip events of their attachments and re-emit.',
          optional=False, default=False),
  ]

  def SetUp(self):
    """Authenticates the connection to Cloud Storage."""
    self.gcs = gcs_utils.CloudStorage(self.args.key_path)
    self.args.target_dir = self.args.target_dir.rstrip('/')

  def Main(self):
    """Main thread of the plugin."""
    while not self.IsStopping():
      if not self.ProcessNextBatch():
        # TODO(kitching): Find a better way to block the plugin when we are in
        #                 one of the PAUSING, PAUSED, or UNPAUSING states.
        self.Sleep(1)

  def ProcessNextBatch(self):
    """Gets the next event with attachments and uploads it.

    Returns:
      True if the next batch was successfully processed.  False if there were no
      events available for processing, or if an error occurred.
    """
    event_stream = self.NewStream()
    if not event_stream:
      return False

    events = []
    success = True
    for event in event_stream.iter(timeout=self.args.interval):
      events.append(event)

      if event.attachments:
        try:
          self.debug('Will upload %d attachments from event',
                     len(event.attachments))
          self.UploadEvent(event)
        except Exception:
          self.exception('Exception encountered during upload, aborting')
          success = False
        else:
          # Re-emit events with their attachments removed.
          if self.args.enable_emit:
            self.Emit(events)
          break

    event_stream.Commit() if success else event_stream.Abort()
    self.debug('Processed batch of %d events', len(events))

    # Return False if no events were processed.
    return bool(events)

  def UploadEvent(self, event):
    """Uploads attachments of given event."""
    for att_id, att_path in event.attachments.iteritems():
      target_filename = (file_utils.SHA1InHex(att_path) if self.args.use_sha1
                         else att_id)
      target_path = '%s/%s' % (self.args.target_dir, target_filename)

      # Upload the file.
      self.info('Uploading %s --> %s', att_path, target_path)
      resumable_uri = self.gcs.UploadFile(att_path, target_path)

      # Relocate the attachments entry into the event payload.
      event.setdefault('__attachments__', {})[att_id] = 'gs:/%s' % target_path

      if resumable_uri:
        raise IOError('Could not upload file %s successfully: %r'
                      % (att_id, event))

    # Remove attachments from the event for re-emitting.
    event.attachments = {}


if __name__ == '__main__':
  plugin_base.main()
