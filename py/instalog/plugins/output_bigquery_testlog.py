#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""BigQuery upload output plugin.

Subclasses OutputBigQuery to create table rows for Testlog events.
"""

from __future__ import print_function

import json
import math
import time

import instalog_common  # pylint: disable=W0611
from instalog import plugin_base
from instalog.plugins import output_bigquery


class OutputBigQueryTestlog(output_bigquery.OutputBigQuery):

  def GetTableSchema(self):
    """Returns a list of fields in the table schema."""
    return [
        # history
        {'name': 'history', 'type': 'RECORD', 'mode': 'REPEATED', 'fields': [
            {'name': 'node_id', 'type': 'STRING'},
            {'name': 'orig_time', 'type': 'TIMESTAMP'},
            {'name': 'time', 'type': 'TIMESTAMP'},
            {'name': 'plugin_id', 'type': 'STRING'},
            {'name': 'plugin_type', 'type': 'STRING'},
            {'name': 'target', 'type': 'STRING'}]},

        # station
        {'name': 'uuid', 'type': 'STRING'},
        {'name': 'type', 'type': 'STRING'},
        {'name': 'apiVersion', 'type': 'STRING'},
        {'name': 'time', 'type': 'TIMESTAMP'},
        {'name': 'stationName', 'type': 'STRING'},
        {'name': 'seq', 'type': 'INTEGER'},
        {'name': 'stationDeviceId', 'type': 'STRING'},
        {'name': 'stationInstallationId', 'type': 'STRING'},

        # station.init
        {'name': 'count', 'type': 'INTEGER'},
        {'name': 'success', 'type': 'BOOLEAN'},
        {'name': 'failureMessage', 'type': 'STRING'},

        # station.message
        {'name': 'message', 'type': 'STRING'},
        {'name': 'filePath', 'type': 'STRING'},
        {'name': 'lineNumber', 'type': 'INTEGER'},
        {'name': 'functionName', 'type': 'STRING'},
        {'name': 'logLevel', 'type': 'STRING'},
        {'name': 'testRunId', 'type': 'STRING'},  # also in station.test_run

        # station.test_run
        {'name': 'testType', 'type': 'STRING'},
        {'name': 'arguments', 'type': 'RECORD', 'mode': 'REPEATED', 'fields': [
            {'name': 'key', 'type': 'STRING'},
            {'name': 'description', 'type': 'STRING'},
            {'name': 'value', 'type': 'STRING'}]},
        {'name': 'status', 'type': 'STRING'},
        {'name': 'startTime', 'type': 'TIMESTAMP'},
        {'name': 'endTime', 'type': 'TIMESTAMP'},
        {'name': 'duration', 'type': 'FLOAT'},
        {'name': 'operatorId', 'type': 'STRING'},
        {'name': 'attachments', 'type': 'RECORD', 'mode': 'REPEATED', 'fields': [
            {'name': 'key', 'type': 'STRING'},
            {'name': 'description', 'type': 'STRING'},
            {'name': 'path', 'type': 'STRING'},
            {'name': 'mimeType', 'type': 'STRING'}]},
        {'name': 'failures', 'type': 'RECORD', 'mode': 'REPEATED', 'fields': [
            {'name': 'id', 'type': 'INTEGER'},
            {'name': 'code', 'type': 'STRING'},
            {'name': 'details', 'type': 'STRING'}]},
        {'name': 'serialNumbers', 'type': 'RECORD', 'mode': 'REPEATED', 'fields': [
            {'name': 'key', 'type': 'STRING'},
            {'name': 'value', 'type': 'STRING'}]},
        {'name': 'parameters', 'type': 'RECORD', 'mode': 'REPEATED', 'fields': [
            {'name': 'key', 'type': 'STRING'},
            {'name': 'description', 'type': 'STRING'},
            {'name': 'group', 'type': 'STRING'},
            {'name': 'status', 'type': 'STRING'},
            {'name': 'valueUnit', 'type': 'STRING'},
            {'name': 'numericValue', 'type': 'FLOAT'},
            {'name': 'expectedMinimum', 'type': 'FLOAT'},
            {'name': 'expectedMaximum', 'type': 'FLOAT'},
            {'name': 'textValue', 'type': 'STRING'},
            {'name': 'expectedRegex', 'type': 'STRING'}]},
        {'name': 'series', 'type': 'RECORD', 'mode': 'REPEATED', 'fields': [
            {'name': 'key', 'type': 'STRING'},
            {'name': 'description', 'type': 'STRING'},
            {'name': 'group', 'type': 'STRING'},
            {'name': 'keyUnit', 'type': 'STRING'},
            {'name': 'valueUnit', 'type': 'STRING'},
            {'name': 'data', 'type': 'RECORD', 'mode': 'REPEATED', 'fields': [
                {'name': 'id', 'type': 'INTEGER'},
                {'name': 'key', 'type': 'FLOAT'},
                {'name': 'status', 'type': 'STRING'},
                {'name': 'numericValue', 'type': 'FLOAT'},
                {'name': 'expectedMinimum', 'type': 'FLOAT'},
                {'name': 'expectedMaximum', 'type': 'FLOAT'}]}]},
        {'name': 'serialized', 'type': 'STRING'}]

  def ConvertEventToRow(self, event):
    """Converts an event to its corresponding BigQuery table row JSON string."""
    if '__testlog__' not in event:
      return None

    def DateTimeToUnixTimestamp(obj):
      return time.mktime(obj.timetuple()) if obj else None

    row = {}

    # history
    row['history'] = []
    for process_stage in event.history:
      row['history'].append({})
      row['history'][-1]['node_id'] = process_stage.node_id
      row['history'][-1]['orig_time'] = DateTimeToUnixTimestamp(
          process_stage.orig_time)
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
    row['stationName'] = event.get('stationName')
    row['seq'] = event.get('seq')
    row['stationDeviceId'] = event.get('stationDeviceId')
    row['stationInstallationId'] = event.get('stationInstallationId')

    # station.init
    row['count'] = event.get('count')
    row['success'] = event.get('success')
    row['failureMessage'] = event.get('failureMessage')

    # station.message
    row['message'] = event.get('message')
    row['filePath'] = event.get('filePath')
    row['lineNumber'] = event.get('lineNumber')
    row['functionName'] = event.get('functionName')
    row['logLevel'] = event.get('logLevel')
    row['testRunId'] = event.get('testRunId')  # also in station.test_run

    # station.test_run
    row['testType'] = event.get('testType')

    row['arguments'] = []
    for key, dct in event.get('arguments', {}).iteritems():
      row['arguments'].append({})
      row['arguments'][-1]['key'] = key
      row['arguments'][-1]['description'] = dct.get('description')
      # Cast to string since it can be any type.
      row['arguments'][-1]['value'] = unicode(dct.get('value'))

    row['status'] = event.get('status')
    row['startTime'] = DateTimeToUnixTimestamp(event.get('startTime'))
    row['endTime'] = DateTimeToUnixTimestamp(event.get('endTime'))
    row['duration'] = event.get('duration')
    row['operatorId'] = event.get('operatorId')

    row['attachments'] = []
    for key, dct in event.get('attachments', {}).iteritems():
      row['attachments'].append({})
      row['attachments'][-1]['key'] = key
      row['attachments'][-1]['description'] = dct.get('description')
      row['attachments'][-1]['path'] = dct.get('path')
      # Check to see whether the attachment path has been modified by some other
      # Instalog plugin.  If so, use that path instead.
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

    row['serialNumbers'] = []
    for key, value in event.get('serialNumbers', {}).iteritems():
      row['serialNumbers'].append({})
      row['serialNumbers'][-1]['key'] = key
      row['serialNumbers'][-1]['value'] = value

    row['parameters'] = []
    for key, dct in event.get('parameters', {}).iteritems():
      dct = dct or {}
      row['parameters'].append({})
      row['parameters'][-1]['key'] = key
      row['parameters'][-1]['description'] = dct.get('description')
      row['parameters'][-1]['group'] = dct.get('group')
      row['parameters'][-1]['status'] = dct.get('status')
      row['parameters'][-1]['valueUnit'] = dct.get('valueUnit')

      # TODO(kitching): Remove these casts when numericValue is reliable.
      if dct.get('numericValue') is not None:
        numeric_value = float(dct.get('numericValue'))
        if math.isinf(numeric_value) or math.isnan(numeric_value):
          numeric_value = None
        row['parameters'][-1]['numericValue'] = numeric_value

      if dct.get('expectedMinimum') is not None:
        expected_minimum = float(dct.get('expectedMinimum'))
        if math.isinf(expected_minimum) or math.isnan(expected_minimum):
          expected_minimum = None
        row['parameters'][-1]['expectedMinimum'] = expected_minimum

      if dct.get('expectedMaximum') is not None:
        expected_maximum = float(dct.get('expectedMaximum'))
        if math.isinf(expected_maximum) or math.isnan(expected_maximum):
          expected_maximum = None
        row['parameters'][-1]['expectedMaximum'] = expected_maximum

      row['parameters'][-1]['textValue'] = dct.get('textValue')
      row['parameters'][-1]['expectedRegex'] = dct.get('expectedRegex')

    row['series'] = []
    for key, dct in event.get('series', {}).iteritems():
      row['series'].append({})
      row['series'][-1]['key'] = key
      row['series'][-1]['description'] = dct.get('description')
      row['series'][-1]['group'] = dct.get('group')
      row['series'][-1]['keyUnit'] = dct.get('valueUnit')
      row['series'][-1]['valueUnit'] = dct.get('valueUnit')
      row['series'][-1]['data'] = []
      for i, data_dct in enumerate(dct.get('data', [])):
        row['series'][-1]['data'].append({})
        row['series'][-1]['data'][-1]['id'] = i
        row['series'][-1]['data'][-1]['key'] = data_dct.get('key')
        row['series'][-1]['data'][-1]['status'] = data_dct.get('status')
        row['series'][-1]['data'][-1]['numericValue'] = data_dct.get(
            'numericValue')
        row['series'][-1]['data'][-1]['expectedMinimum'] = data_dct.get(
            'expectedMinimum')
        row['series'][-1]['data'][-1]['expectedMaximum'] = data_dct.get(
            'expectedMaximum')

    row['serialized'] = event.Serialize()
    return json.dumps(row, allow_nan=False)


if __name__ == '__main__':
  plugin_base.main()
