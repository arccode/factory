#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""BigQuery upload output plugin.

Load job limits:
  daily load job limit per table: 1000 (every 86.4 seconds)
  daily load job limit per project: 50,000
  JSON row size limit: 10 MB
  JSON max file size: 5 TB
  max size per load job: 15 TB

Partitioned table updates limits:
  daily updates partition limit per table: 2500
  updates partition limit per load job: 500

( Source: https://cloud.google.com/bigquery/quotas )
"""

import datetime
import os
import time

# pylint: disable=import-error, no-name-in-module
from google.api_core import exceptions
from google.cloud import bigquery
from google.oauth2 import service_account

from cros.factory.instalog import plugin_base
from cros.factory.instalog.utils.arg_utils import Arg
from cros.factory.instalog.utils import file_utils
from cros.factory.instalog.utils import gcs_utils


_BIGQUERY_SCOPE = 'https://www.googleapis.com/auth/bigquery'
_BIGQUERY_REQUEST_MAX_FAILURES = 20
_JOB_NAME_PREFIX = 'instalog_'
_JSON_MIMETYPE = 'NEWLINE_DELIMITED_JSON'
_ROW_SIZE_LIMIT = 9.5 * 1024 * 1024  # To avoid error loop, we set 9.5 mb limit.
_PARTITION_LIMIT = 500
_SECONDS_IN_A_DAY = 24 * 60 * 60
_DEFAULT_INTERVAL = 90
_DEFAULT_BATCH_SIZE = 3000


class OutputBigQuery(plugin_base.OutputPlugin):

  ARGS = [
      Arg(
          'interval', (int, float),
          'Frequency to upload a BigQuery import, in seconds.  Since BigQuery '
          'only allows 1000 imports per day per table, a value above 86.4 '
          'seconds is recommended to guarantee this limit will not be reached.',
          default=_DEFAULT_INTERVAL),
      Arg('batch_size', int, 'How many events to queue before transmitting.',
          default=_DEFAULT_BATCH_SIZE),
      Arg('key_path', str,
          'Path to BigQuery/CloudStorage service account JSON key file.'),
      Arg(
          'gcs_target_dir', str,
          'Path to the target bucket and directory on Google Cloud Storage.  '
          'If set to None, not upload attachments to GCS (default).',
          default=None),
      Arg('project_id', str, 'Google Cloud project ID.'),
      Arg('dataset_id', str, 'BigQuery dataset ID.'),
      Arg('table_id', str, 'BigQuery target table name.')
  ]

  def __init__(self, *args, **kwargs):
    self.client = None
    self.table_ref = None
    self._gcs = None
    super(OutputBigQuery, self).__init__(*args, **kwargs)

  def SetUp(self):
    """Builds the client object and the table object to run BigQuery calls."""
    self.client = self.BuildClient()
    self.CreateDatasetAndTable()
    self._gcs = gcs_utils.CloudStorage(self.args.key_path, self.logger)

  def Main(self):
    """Main thread of the plugin."""
    while not self.IsStopping():
      if not self.PrepareAndUpload():
        # TODO(kitching): Find a better way to block the plugin when we are in
        #                 one of the PAUSING, PAUSED, or UNPAUSING states.
        self.Sleep(1)

  def BuildClient(self):
    """Builds a BigQuery client object."""
    credentials = service_account.Credentials.from_service_account_file(
        self.args.key_path, scopes=(_BIGQUERY_SCOPE,))
    return bigquery.Client(project=self.args.project_id,
                           credentials=credentials)

  def CreateDatasetAndTable(self):
    """Creates the BigQuery dataset/table if it doesn't exist."""
    dataset_ref = self.client.dataset(self.args.dataset_id)
    try:
      dataset = self.client.get_dataset(dataset_ref)
      self.info('The dataset %s is created from %s',
                self.args.dataset_id, dataset.created)
    except exceptions.NotFound:
      _dataset = bigquery.Dataset(dataset_ref)
      dataset = self.client.create_dataset(_dataset)
      self.info('The dataset %s does not exist. Creating...',
                self.args.dataset_id)

    self.table_ref = dataset.table(self.args.table_id)
    try:
      table = self.client.get_table(self.table_ref)
      self.info('The table %s is created from %s',
                self.args.table_id, table.created)
    except exceptions.NotFound:
      _table = bigquery.Table(self.table_ref, schema=self.GetTableSchema())
      # pylint: disable=protected-access
      _table._properties['timePartitioning'] = {
          'type': 'DAY',
          'expirationMs': None,
          'field': 'time'}
      table = self.client.create_table(_table)
      self.info('The table %s does not exist. Creating...',
                self.args.table_id)

  def GetTableSchema(self):
    """Returns a list of fields in the table schema.

    Fields may be nested according to BigQuery RECORD type specification.

    Example:
        [
            {'name': 'event_time', 'type': 'TIMESTAMP'},
            {'name': 'event_fields', 'type': RECORD', 'fields':
                [
                    {'name': 'key': 'type': 'STRING'},
                    {'name': 'value': 'type': 'STRING'}
                ]
            }
        ]
    """
    raise NotImplementedError

  def ConvertEventToRow(self, event):
    """Converts an event to its corresponding BigQuery table row JSON string.

    Returns:
      A JSON string corresponding to the table row.  None if the event should
      not create any table row.

    Raises:
      Exception if something went wrong (unexpected data in the Event).  The
      exception will be logged and the row will be ignored.
    """
    raise NotImplementedError

  def UploadAttachments(self, event):
    """Uploads attachments in an event to Google Cloud Storage."""
    for att_id, att_path in event.attachments.items():
      target_filename = file_utils.SHA1InHex(att_path)
      target_dir = self.args.gcs_target_dir.strip('/')
      target_path = '/%s/%s' % (target_dir, target_filename)
      if not self._gcs.UploadFile(att_path, target_path, overwrite=True):
        return False

      # Relocate the attachments entry into the event payload.
      event.setdefault('__attachments__', {})[att_id] = 'gs:/%s' % target_path

    return True

  def PrepareFile(self, event_stream, json_path):
    """Retrieves events from event_stream and dumps them to the json_path.

    Returns:
      A tuple of (event_count, row_count), where:
        event_count: The number of events from event_stream.
        row_count: The number of BigQuery format events from event_stream.
    """
    event_count = 0
    row_count = 0
    partition_set = set()
    with open(json_path, 'w') as f:
      for event in event_stream.iter(timeout=self.args.interval,
                                     count=self.args.batch_size):
        event_count += 1
        if self.args.gcs_target_dir and not self.UploadAttachments(event):
          return event_count, -1
        json_row = None
        try:
          json_row = self.ConvertEventToRow(event)
        except Exception:
          self.warning('Error converting event to row: %s',
                       event, exc_info=True)
        if json_row is not None:
          if len(json_row) > _ROW_SIZE_LIMIT:
            # TODO(chuntsen): Find a better way to handle too big row.
            cur_time = datetime.datetime.now()
            big_event_filename = cur_time.strftime('Big_event_%Y%m%d_%H%M%S.%f')
            big_event_path = os.path.join(self.GetDataDir(),
                                          big_event_filename)
            self.warning('Find a too big event (row size = %d bytes), and save '
                         'it to %s', len(json_row), big_event_path)
            with open(big_event_path, 'w') as g:
              g.write(event.Serialize() + '\n')
          else:
            f.write(json_row + '\n')
            row_count += 1
            # We are using time column as the timePartitioning field
            partition_set.add(event['time'] // _SECONDS_IN_A_DAY)
        if len(partition_set) == _PARTITION_LIMIT:
          break

    return event_count, row_count

  def PrepareAndUpload(self):
    """Retrieves events, converts them to BigQuery format, and uploads them."""
    event_stream = self.NewStream()
    if not event_stream:
      return False

    with file_utils.UnopenedTemporaryFile(
        prefix='output_bigquery_') as json_path:
      event_count, row_count = self.PrepareFile(event_stream, json_path)

      if self.IsStopping():
        self.info('Plugin is stopping! Abort %d events', event_count)
        event_stream.Abort()
        return False

      # No processed events result in BigQuery table rows.
      if row_count == 0:
        self.info('Commit %d events (%d rows)', event_count, row_count)
        event_stream.Commit()
        return False
      # Failed to upload attachments.
      if row_count == -1:
        self.info('Abort %d events (%d rows)', event_count, row_count)
        event_stream.Abort()
        return False

      job_id = '%s%d' % (_JOB_NAME_PREFIX, time.time() * 1e6)
      self.info('Uploading %d rows into BigQuery (%s) ...', row_count, job_id)
      try:
        job = None
        with open(json_path, 'rb') as f:
          job_config = bigquery.LoadJobConfig()
          job_config.source_format = _JSON_MIMETYPE
          # No need to run job.begin() since upload_from_file() takes care of
          # this.
          job = self.client.load_table_from_file(
              file_obj=f,
              destination=self.table_ref,
              size=os.path.getsize(json_path),
              num_retries=_BIGQUERY_REQUEST_MAX_FAILURES,
              job_id=job_id,
              job_config=job_config)

        # Wait for job to complete.
        job.result()

      except Exception:
        event_stream.Abort()
        if job and hasattr(job, 'errors'):
          self.exception('Insert failed with errors: %s', job.errors)
        else:
          self.exception('Insert failed')
        self.info('Abort %d events (%d rows)', event_count, row_count)
        return False
      else:
        if job.state == 'DONE':
          self.info('Commit %d events (%d rows)', event_count, row_count)
          event_stream.Commit()
          return True
        event_stream.Abort()
        self.warning('Insert failed with errors: %s', job.errors)
        self.info('Abort %d events (%d rows)', event_count, row_count)
        return False


if __name__ == '__main__':
  plugin_base.main()
