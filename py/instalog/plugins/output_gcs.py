#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Cloud Storage attachment upload output plugin."""

from cros.factory.instalog import plugin_base
from cros.factory.instalog.utils.arg_utils import Arg
from cros.factory.instalog.utils import file_utils
from cros.factory.instalog.utils import gcs_utils


_DEFAULT_INTERVAL = 5


class OutputCloudStorage(plugin_base.OutputPlugin):

  ARGS = [
      Arg('interval', (int, float),
          'Frequency to re-emit events, if no attachments are encountered. '
          'When attachments are encountered, events are re-emitted right '
          'after upload.',
          default=_DEFAULT_INTERVAL),
      Arg('key_path', str,
          'Path to Cloud Storage service account JSON key file.'),
      Arg('target_dir', str,
          'Path to the target bucket and directory on Google Cloud.'),
      Arg('use_sha1', bool,
          'Use the attachment\'s SHA1 hex-encoded hash as its filename.  '
          'Note that this means multiple attachments may point to the same '
          'file on Cloud Storage.  If set to False, the attachment ID will '
          'be used as its filename.',
          default=False),
      Arg('enable_emit', bool,
          'Strip events of their attachments and re-emit.',
          default=False),
  ]

  def __init__(self, *args, **kwargs):
    self.target_dir = None
    self.gcs = None
    super(OutputCloudStorage, self).__init__(*args, **kwargs)

  def SetUp(self):
    """Authenticates the connection to Cloud Storage."""
    self.target_dir = self.args.target_dir.strip('/')
    self.gcs = gcs_utils.CloudStorage(self.args.key_path, self.logger)

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
        break

    # Re-emit events with their attachments removed.
    if success and self.args.enable_emit:
      if not self.Emit(events):
        self.error('Unable to emit, aborting')
        success = False

    if success:
      event_stream.Commit()
    else:
      event_stream.Abort()
    self.debug('Processed batch of %d events', len(events))

    # Return False if failure occurred, or if no events were processed.
    return success and bool(events)

  def UploadEvent(self, event):
    """Uploads attachments of given event."""
    for att_id, att_path in event.attachments.items():
      target_filename = (file_utils.SHA1InHex(att_path) if self.args.use_sha1
                         else att_id)
      target_path = '/%s/%s' % (self.target_dir, target_filename)

      # Upload the file.
      self.gcs(att_path, target_path)

      # Relocate the attachments entry into the event payload.
      event.setdefault('__attachments__', {})[att_id] = 'gs:/%s' % target_path

    # Remove attachments from the event for re-emitting.
    event.attachments = {}


if __name__ == '__main__':
  plugin_base.main()
