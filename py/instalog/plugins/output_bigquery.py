#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""BigQuery upload output plugin.

Limits to keep in mind:
  daily load job limit per table: 1000 (every 86.4 seconds)
  daily load job limit per project: 10,000
  JSON row size: 2 MB
  JSON max file size: 5 TB
  max size per load job: 12 TB
"""

from __future__ import print_function

import httplib2
import os
import StringIO
import time

import instalog_common  # pylint: disable=W0611
from instalog import plugin_base
from instalog.utils.arg_utils import Arg

from apiclient.http import MediaIoBaseUpload
from apiclient.discovery import build
from apiclient.errors import HttpError
from oauth2client.service_account import ServiceAccountCredentials


_HTTP_TIMEOUT = 60
_JSON_MIMETYPE = 'application/json'
_UPLOAD_CHUNK_SIZE = 1024 * 1204  # 1mb
_JOB_NAME_PREFIX = 'instalog_'
_BIGQUERY_REQUEST_INTERVAL = 5
_BIGQUERY_REQUEST_MAX_FAILURES = 20
_BIGQUERY_SCOPE = 'https://www.googleapis.com/auth/bigquery'
_DEFAULT_INTERVAL = 90


class OutputBigQuery(plugin_base.OutputPlugin):

  ARGS = [
      Arg('interval', (int, float),
          'Frequency to upload a BigQuery import, in seconds.  Since BigQuery '
          'only allows 1000 imports per day per table, a value above 86.4 '
          'seconds is recommended to guarantee this limit will not be reached.',
          optional=True, default=_DEFAULT_INTERVAL),
      Arg('key_path', (str, unicode),
          'Path to BigQuery service account JSON key file.',
          optional=False),
      Arg('project_id', (str, unicode), 'Google Cloud project ID.',
          optional=False),
      Arg('dataset_id', (str, unicode), 'BigQuery dataset ID.',
          optional=False),
      Arg('table_id', (str, unicode), 'BigQuery target table name.',
          optional=False)
  ]

  def Start(self):
    """Stores the service object to run BigQuery API calls."""
    self.service = self.BuildService()

  def Main(self):
    """Main thread of the plugin."""
    while not self.IsStopping():
      if not self.PrepareAndUploadBatch():
        # TODO(kitching): Find a better way to block the plugin when we are in
        #                 one of the PAUSING, PAUSED, or UNPAUSING states.
        self.Sleep(1)

  def BuildService(self):
    """Builds a BigQuery service object."""
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        self.args.key_path, scopes=(_BIGQUERY_SCOPE,))
    http = credentials.authorize(httplib2.Http(timeout=_HTTP_TIMEOUT))
    return build('bigquery', 'v2', http=http)

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

  def GetLoadConfig(self):
    """Returns a load config dictionary to be used in the load job."""
    load_config = {
        'destinationTable': {
            'projectId': self.args.project_id,
            'datasetId': self.args.dataset_id,
            'tableId': self.args.table_id
        }
    }
    load_config['schema'] = {
        'fields': self.GetTableSchema()
    }
    load_config['sourceFormat'] = 'NEWLINE_DELIMITED_JSON'
    return load_config

  def StartLoadJob(self, job_id, media):
    """Starts a BigQuery load job with provided media.

    Args:
      job_id: The Job ID that should be assigned to this job.
      media: MediaIoBaseUpload object with JSON data.

    Raises:
      Exception if there was a problem with the request, or if there was a
      connection failure.
    """
    try:
      self.info('Starting load job %s...', job_id)
      self.service.jobs().insert(
          projectId=self.args.project_id,
          body={
              'jobReference': {
                  'jobId': job_id
              },
              'configuration': {
                  'load': self.GetLoadConfig()
              }
          },
          media_body=media).execute()
    except HttpError as e:
      # Succeeded already in starting the job?
      self.info('HttpError returned by job queue request: %s', e.resp.status)
      if e.resp.status == 409:
        # Response code 409/duplicate: "This error returns when trying to
        # create a job, dataset or table that already exists.  The error also
        # returns when a job's writeDisposition property is set to WRITE_EMPTY
        # and the destination table accessed by the job already exists."
        #
        # If this is due to the job existing, we should report success to
        # continue checking the job status.
        self.warning('Response code 409/duplicate: job, dataset, or table '
                     'may already exist.  If this error keeps occurring, '
                     'it is probably one of the latter two.')
      else:
        raise e
    return job_id

  def GetJobResult(self, job_id):
    """Gets the results of a particular job ID.

    Raises:
      Exception if there was a problem with the request, or if there was a
      connection failure.
    """
    return self.service.jobs().get(
        projectId=self.args.project_id, jobId=job_id).execute()

  def UploadBatch(self, media):
    """Uploads a batch of JSON data to BigQuery.

    Waits for the job to complete until returning.  Aborts either StartLoadJob
    or GetJobResult fails more than _BIGQUERY_REQUEST_MAX_FAILURES times.

    Returns:
      True on success, False on failure.
    """
    # Attempt to start the job.
    job_id = '%s%d' % (_JOB_NAME_PREFIX, time.time())
    for exception_count in xrange(1, _BIGQUERY_REQUEST_MAX_FAILURES + 1):
      try:
        self.StartLoadJob(job_id, media)
        break
      except Exception:
        self.warning('Error retrieving load job %s result (%d/%d)',
                     job_id, exception_count, _BIGQUERY_REQUEST_MAX_FAILURES,
                     exc_info=True)
      if exception_count != _BIGQUERY_REQUEST_MAX_FAILURES:
        time.sleep(_BIGQUERY_REQUEST_INTERVAL)
    else:
      self.error(
          'Give up starting load job %s result after %d attempts',
          job_id, _BIGQUERY_REQUEST_MAX_FAILURES)
      return False

    # Wait for the job to report completion.
    for exception_count in xrange(1, _BIGQUERY_REQUEST_MAX_FAILURES + 1):
      try:
        result = self.GetJobResult(job_id)
        self.debug('Load job %s result: %s', job_id, result)
        if result['status']['state'] not in ('PENDING', 'RUNNING', 'DONE'):
          self.error('Load job %s has unexpected state %s; aborting',
                     job_id, result['status']['state'])
          return False
        if 'errorResult' in result['status']:
          self.error('Load job %s failed in state %s: %s',
                     job_id, result['status']['state'],
                     result['status']['errorResult'])
          return False
        if result['status']['state'] == 'DONE':
          self.info('Load job %s successful', job_id)
          return True
      except Exception:
        self.warning('Error retrieving load job %s result (%d/%d)',
                     job_id, exception_count, _BIGQUERY_REQUEST_MAX_FAILURES,
                     exc_info=True)
      if exception_count != _BIGQUERY_REQUEST_MAX_FAILURES:
        time.sleep(_BIGQUERY_REQUEST_INTERVAL)
    else:
      self.error(
          'Give up retrieving load job %s result after %d attempts',
          job_id, exception_count)
    return False

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

  def PrepareAndUploadBatch(self):
    """Retrieves events, converts them to BigQuery format, and uploads them."""
    event_stream = self.NewStream()
    if not event_stream:
      return False

    json_stream = StringIO.StringIO()
    event_count = 0
    row_count = 0
    for event in event_stream.iter(timeout=self.args.interval):
      json_row = None
      try:
        json_row = self.ConvertEventToRow(event)
      except Exception:
        self.warning('Error converting event to row: %s', event, exc_info=True)
      if json_row is not None:
        json_stream.write(json_row + '\n')
        row_count += 1
      event_count += 1

    # No processed events result in BigQuery table rows.
    if row_count == 0 and event_count > 0:
      success_string = 'success' if event_stream.Commit() else 'failure'
      self.info('Commit %d events (no BigQuery rows): %s',
                event_count, success_string)
      return True

    if event_count == 0:
      event_stream.Abort()
      self.info('Abort %d events', event_count)
      return False

    # Write the current import job to disk for debugging purposes.
    with open(os.path.join(self.GetStateDir(), 'last_batch.json'), 'w') as f:
      f.write(json_stream.getvalue())

    media = MediaIoBaseUpload(json_stream, mimetype=_JSON_MIMETYPE,
                              chunksize=_UPLOAD_CHUNK_SIZE, resumable=False)
    self.info('Uploading BigQuery batch with %d events...', event_count)
    if self.UploadBatch(media):
      success_string = 'success' if event_stream.Commit() else 'failure'
      self.info('Commit %d events: %s', event_count, success_string)
      return True
    else:
      event_stream.Abort()
      self.info('Abort %d events', event_count)
      return False


if __name__ == '__main__':
  plugin_base.main()
