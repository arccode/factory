#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""BigQuery upload output plugin.

Subclasses OutputBigQuery to create table rows for Testlog events.
"""

import datetime
import json
import math

# pylint: disable=import-error, no-name-in-module
from google.cloud.bigquery.schema import SchemaField

from cros.factory.instalog import plugin_base
from cros.factory.instalog.plugins import output_bigquery
from cros.factory.instalog.utils import time_utils


class OutputBigQueryTestlog(output_bigquery.OutputBigQuery):

  def GetTableSchema(self):
    """Returns a list of fields in the table schema."""
    return [
        # history
        SchemaField(u'history', u'record', u'REPEATED', None, (
            SchemaField(u'node_id', u'string', 'NULLABLE', None, ()),
            SchemaField(u'time', u'timestamp', 'NULLABLE', None, ()),
            SchemaField(u'plugin_id', u'string', 'NULLABLE', None, ()),
            SchemaField(u'plugin_type', u'string', 'NULLABLE', None, ()),
            SchemaField(u'target', u'string', 'NULLABLE', None, ())
        )),

        # station
        SchemaField(u'uuid', u'string', 'NULLABLE', None, ()),
        SchemaField(u'type', u'string', 'NULLABLE', None, ()),
        SchemaField(u'apiVersion', u'string', 'NULLABLE', None, ()),
        SchemaField(u'time', u'timestamp', 'NULLABLE', None, ()),
        SchemaField(u'seq', u'integer', 'NULLABLE', None, ()),
        SchemaField(u'dutDeviceId', u'string', 'NULLABLE', None, ()),
        SchemaField(u'stationDeviceId', u'string', 'NULLABLE', None, ()),
        SchemaField(u'stationInstallationId', u'string', 'NULLABLE', None, ()),

        # station.status
        SchemaField(u'filePath', u'string', 'NULLABLE', None, ()),
        SchemaField(u'serialNumbers', u'record', u'REPEATED', None, (
            SchemaField(u'key', u'string', 'NULLABLE', None, ()),
            SchemaField(u'value', u'string', 'NULLABLE', None, ())
        )),
        SchemaField(u'parameters', u'record', u'REPEATED', None, (
            SchemaField(u'key', u'string', 'NULLABLE', None, ()),
            SchemaField(u'description', u'string', 'NULLABLE', None, ()),
            SchemaField(u'group', u'string', 'NULLABLE', None, ()),
            SchemaField(u'valueUnit', u'string', 'NULLABLE', None, ()),
            SchemaField(u'data', u'record', u'REPEATED', None, (
                SchemaField(u'id', u'integer', 'NULLABLE', None, ()),
                SchemaField(u'status', u'string', 'NULLABLE', None, ()),
                SchemaField(u'numericValue', u'float', 'NULLABLE', None, ()),
                SchemaField(u'expectedMinimum', u'float', 'NULLABLE', None, ()),
                SchemaField(u'expectedMaximum', u'float', 'NULLABLE', None, ()),
                SchemaField(u'textValue', u'string', 'NULLABLE', None, ()),
                SchemaField(u'expectedRegex', u'string', 'NULLABLE', None, ()),
                SchemaField(u'serializedValue', u'string', 'NULLABLE', None, ())
            ))
        )),

        # station.init
        SchemaField(u'count', u'integer', 'NULLABLE', None, ()),
        SchemaField(u'success', u'boolean', 'NULLABLE', None, ()),
        SchemaField(u'failureMessage', u'string', 'NULLABLE', None, ()),

        # station.message
        SchemaField(u'message', u'string', 'NULLABLE', None, ()),
        SchemaField(u'lineNumber', u'integer', 'NULLABLE', None, ()),
        SchemaField(u'functionName', u'string', 'NULLABLE', None, ()),
        SchemaField(u'logLevel', u'string', 'NULLABLE', None, ()),
        SchemaField(u'testRunId', u'string', 'NULLABLE', None, ()),

        # station.test_run (also use testRunId)
        SchemaField(u'testName', u'string', 'NULLABLE', None, ()),
        SchemaField(u'testType', u'string', 'NULLABLE', None, ()),
        SchemaField(u'arguments', u'record', u'REPEATED', None, (
            SchemaField(u'key', u'string', 'NULLABLE', None, ()),
            SchemaField(u'description', u'string', 'NULLABLE', None, ()),
            SchemaField(u'value', u'string', 'NULLABLE', None, ())
        )),
        SchemaField(u'status', u'string', 'NULLABLE', None, ()),
        SchemaField(u'startTime', u'timestamp', 'NULLABLE', None, ()),
        SchemaField(u'endTime', u'timestamp', 'NULLABLE', None, ()),
        SchemaField(u'duration', u'float', 'NULLABLE', None, ()),
        SchemaField(u'operatorId', u'string', 'NULLABLE', None, ()),
        SchemaField(u'attachments', u'record', u'REPEATED', None, (
            SchemaField(u'key', u'string', 'NULLABLE', None, ()),
            SchemaField(u'description', u'string', 'NULLABLE', None, ()),
            SchemaField(u'path', u'string', 'NULLABLE', None, ()),
            SchemaField(u'mimeType', u'string', 'NULLABLE', None, ())
        )),
        SchemaField(u'failures', u'record', u'REPEATED', None, (
            SchemaField(u'id', u'integer', 'NULLABLE', None, ()),
            SchemaField(u'code', u'string', 'NULLABLE', None, ()),
            SchemaField(u'details', u'string', 'NULLABLE', None, ())
        )),

        # serialized
        SchemaField(u'serialized', u'string', 'NULLABLE', None, ())
    ]

  def ConvertEventToRow(self, event):
    """Converts an event to its corresponding BigQuery table row JSON string."""
    if not event.get('__testlog__', False):
      return None

    def DateTimeToUnixTimestamp(obj):
      if isinstance(obj, datetime.datetime):
        return time_utils.DatetimeToUnixtime(obj)
      if isinstance(obj, float):
        return obj
      return None

    row = {}

    # history
    row['history'] = []
    for process_stage in event.history:
      row['history'].append({})
      row['history'][-1]['node_id'] = process_stage.node_id
      row['history'][-1]['time'] = DateTimeToUnixTimestamp(
          process_stage.time)
      row['history'][-1]['plugin_id'] = process_stage.plugin_id
      row['history'][-1]['plugin_type'] = process_stage.plugin_type
      row['history'][-1]['target'] = process_stage.target

    # station
    row['uuid'] = event.get('uuid')
    row['type'] = event.get('type')
    row['apiVersion'] = event.get('apiVersion')
    row['time'] = DateTimeToUnixTimestamp(event.get('time'))
    row['seq'] = event.get('seq')
    row['dutDeviceId'] = event.get('dutDeviceId')
    row['stationDeviceId'] = event.get('stationDeviceId')
    row['stationInstallationId'] = event.get('stationInstallationId')

    # station.status
    row['filePath'] = event.get('filePath')  # also in station.message
    row['serialNumbers'] = []
    for key, value in event.get('serialNumbers', {}).items():
      row['serialNumbers'].append({})
      row['serialNumbers'][-1]['key'] = key
      row['serialNumbers'][-1]['value'] = value

    row['parameters'] = []
    for key, dct in event.get('parameters', {}).items():
      dct = dct or {}
      row['parameters'].append({})
      row['parameters'][-1]['key'] = key
      row['parameters'][-1]['description'] = dct.get('description')
      row['parameters'][-1]['group'] = dct.get('group')
      row['parameters'][-1]['status'] = dct.get('status')
      row['parameters'][-1]['valueUnit'] = dct.get('valueUnit')



    row['parameters'] = []
    for key, dct in event.get('parameters', {}).items():
      row['parameters'].append({})
      row['parameters'][-1]['key'] = key
      row['parameters'][-1]['description'] = dct.get('description')
      row['parameters'][-1]['group'] = dct.get('group')
      row['parameters'][-1]['valueUnit'] = dct.get('valueUnit')
      row['parameters'][-1]['data'] = []
      for i, data_dct in enumerate(dct.get('data', [])):
        row['parameters'][-1]['data'].append({})
        row['parameters'][-1]['data'][-1]['id'] = i
        row['parameters'][-1]['data'][-1]['status'] = data_dct.get('status')
        # TODO(chuntsen): Remove these casts when numericValue is reliable.
        if data_dct.get('numericValue') is not None:
          numeric_value = float(data_dct.get('numericValue'))
          if math.isinf(numeric_value) or math.isnan(numeric_value):
            numeric_value = None
          row['parameters'][-1]['data'][-1]['numericValue'] = numeric_value
        if data_dct.get('expectedMinimum') is not None:
          expected_minimum = float(data_dct.get('expectedMinimum'))
          if math.isinf(expected_minimum) or math.isnan(expected_minimum):
            expected_minimum = None
          row['parameters'][-1]['data'][-1][
              'expectedMinimum'] = expected_minimum
        if data_dct.get('expectedMaximum') is not None:
          expected_maximum = float(data_dct.get('expectedMaximum'))
          if math.isinf(expected_maximum) or math.isnan(expected_maximum):
            expected_maximum = None
          row['parameters'][-1]['data'][-1][
              'expectedMaximum'] = expected_maximum
        row['parameters'][-1]['data'][-1]['textValue'] = data_dct.get(
            'textValue')
        row['parameters'][-1]['data'][-1]['expectedRegex'] = data_dct.get(
            'expectedRegex')
        row['parameters'][-1]['data'][-1]['serializedValue'] = data_dct.get(
            'serializedValue')

    # station.init
    row['count'] = event.get('count')
    row['success'] = event.get('success')
    row['failureMessage'] = event.get('failureMessage')

    # station.message
    row['message'] = event.get('message')
    row['lineNumber'] = event.get('lineNumber')
    row['functionName'] = event.get('functionName')
    row['logLevel'] = event.get('logLevel')
    row['testRunId'] = event.get('testRunId')  # also in station.test_run

    # station.test_run
    row['testName'] = event.get('testName')
    row['testType'] = event.get('testType')

    row['arguments'] = []
    for key, dct in event.get('arguments', {}).items():
      row['arguments'].append({})
      row['arguments'][-1]['key'] = key
      row['arguments'][-1]['description'] = dct.get('description')
      # Cast to string since it can be any type.
      row['arguments'][-1]['value'] = dct.get('value')

    row['status'] = event.get('status')
    row['startTime'] = DateTimeToUnixTimestamp(event.get('startTime'))
    row['endTime'] = DateTimeToUnixTimestamp(event.get('endTime'))
    row['duration'] = event.get('duration')
    row['operatorId'] = event.get('operatorId')

    row['attachments'] = []
    for key, dct in event.get('attachments', {}).items():
      row['attachments'].append({})
      row['attachments'][-1]['key'] = key
      row['attachments'][-1]['description'] = dct.get('description')
      row['attachments'][-1]['path'] = dct.get('path')
      # Check to see whether the attachment path has been modified by
      # UploadAttachments.  If so, use that path instead.
      if ('__attachments__' in event and
          key in event['__attachments__']):
        row['attachments'][-1]['path'] = event['__attachments__'][key]
      row['attachments'][-1]['mimeType'] = dct.get('mimeType')

    row['failures'] = []
    for i, dct in enumerate(event.get('failures', [])):
      row['failures'].append({})
      row['failures'][-1]['id'] = i
      row['failures'][-1]['code'] = dct.get('code')
      row['failures'][-1]['details'] = dct.get('details')

    row['serialized'] = event.Serialize()
    return json.dumps(row, allow_nan=False)


if __name__ == '__main__':
  plugin_base.main()
