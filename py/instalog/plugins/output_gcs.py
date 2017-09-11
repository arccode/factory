#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Cloud Storage attachment upload output plugin."""

from __future__ import print_function

import os

# pylint: disable=import-error
from google.cloud import storage
from google.oauth2 import service_account

import instalog_common  # pylint: disable=unused-import
from instalog import plugin_base
from instalog.utils.arg_utils import Arg
from instalog.utils import file_utils


_DEFAULT_INTERVAL = 5
_GCS_SCOPE = 'https://www.googleapis.com/auth/devstorage.read_write'
_CHUNK_SIZE = 4 * 1024 * 1024  # 4mb


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

  def __init__(self, *args, **kwargs):
    self.client = None
    self.bucket = None
    self.bucket_id = None
    self.dir_in_bucket = None
    super(OutputCloudStorage, self).__init__(*args, **kwargs)

  def SetUp(self):
    """Authenticates the connection to Cloud Storage."""
    self.args.target_dir = self.args.target_dir.strip('/')
    self.bucket_id, _unused_slash, self.dir_in_bucket = (
        self.args.target_dir.partition('/'))
    self.client = self.BuildClient()
    self.bucket = self.BuildBucket()

  def Main(self):
    """Main thread of the plugin."""
    while not self.IsStopping():
      if not self.ProcessNextBatch():
        # TODO(kitching): Find a better way to block the plugin when we are in
        #                 one of the PAUSING, PAUSED, or UNPAUSING states.
        self.Sleep(1)

  def BuildClient(self):
    """Builds a Storage client object."""
    credentials = service_account.Credentials.from_service_account_file(
        self.args.key_path, scopes=(_GCS_SCOPE,))
    return storage.Client(credentials=credentials)

  def BuildBucket(self):
    """Builds a Storage bucket object."""
    bucket = storage.Bucket(self.client, self.bucket_id)
    if not bucket.exists():
      raise ValueError('Bucket %s doesn\'t exist! Please create it before you '
                       'run this plugin')
    return bucket

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
    for att_id, att_path in event.attachments.iteritems():
      target_filename = (file_utils.SHA1InHex(att_path) if self.args.use_sha1
                         else att_id)
      path_in_bucket = '%s/%s' % (self.dir_in_bucket, target_filename)

      # Upload the file.
      self.info('Uploading to GCS: /%s/%s', self.bucket_id, path_in_bucket)
      self.UploadFile(att_path, path_in_bucket)


      # Relocate the attachments entry into the event payload.
      event.setdefault('__attachments__', {})[att_id] = 'gs:/%s/%s' % (
          self.bucket_id, path_in_bucket)

    # Remove attachments from the event for re-emitting.
    event.attachments = {}

  def UploadFile(self, local_path, target_path):
    """Attempts to upload a file to GCS, with resumability.

    Args:
      local_path: Path to the file on local disk.
      target_path: Target path in self.bucket.

    Raises:
      google.cloud.exceptions.GoogleCloudError if the upload response returns an
      error status.
      ValueError if the uploaded file on GCS doesn't exist or has different
      md5_hash/size.
    """
    local_md5 = file_utils.MD5InBase64(local_path)
    local_size = os.path.getsize(local_path)

    blob = storage.Blob(target_path, self.bucket, chunk_size=_CHUNK_SIZE)
    if blob.exists():
      blob.reload()
      if blob.md5_hash == local_md5 and blob.size == local_size:
        self.warning('File already exists on remote end with same size (%d) '
                     'and same MD5 hash (%s); skipping',
                     blob.size, blob.md5_hash)
        return
      else:
        self.error('File already exists on remote end, but size or MD5 hash '
                   'doesn\'t match; size on remote %s = %d, size on local %s = '
                   '%d; will overwrite',
                   target_path, blob.size, local_path, local_size)

    blob.upload_from_filename(local_path)
    blob.reload()
    if not blob.exists():
      raise ValueError('File doesn\'t exist after uploading')
    if blob.md5_hash != local_md5 or blob.size != local_size:
      raise ValueError('Size or MD5 mismatch after uploading; '
                       'local_size = %d, confirmed_size = %d; local_md5 = %s, '
                       'confirmed_md5 = %s',
                       local_size, blob.size, local_md5, blob.md5_hash)


if __name__ == '__main__':
  plugin_base.main()
