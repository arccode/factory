#!/usr/bin/env python3
#
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""BigQuery upload output plugin.

Subclasses OutputBigQuery to create table rows for factory report events.
"""

import json

# pylint: disable=import-error, no-name-in-module
from google.cloud.bigquery.schema import SchemaField
# pylint: enable=import-error, no-name-in-module

from cros.factory.instalog import plugin_base
from cros.factory.instalog.plugins import output_bigquery


class OutputBigQueryFactoryReport(output_bigquery.OutputBigQuery):

  def GetTableSchema(self):
    """Returns a list of fields in the table schema."""
    return [
        SchemaField('uuid', 'string', 'NULLABLE', None, ()),
        SchemaField('objectId', 'string', 'NULLABLE', None, ()),
        SchemaField('reportFilePath', 'string', 'NULLABLE', None, ()),
        SchemaField('toolkitVersion', 'string', 'NULLABLE', None, ()),
        SchemaField('factoryImageVersion', 'string', 'NULLABLE', None, ()),
        SchemaField('releaseImageVersion', 'string', 'NULLABLE', None, ()),
        SchemaField('hwid', 'string', 'NULLABLE', None, ()),
        SchemaField('phase', 'string', 'NULLABLE', None, ()),
        SchemaField('testlistName', 'string', 'NULLABLE', None, ()),
        SchemaField('testlistStation', 'string', 'NULLABLE', None, ()),
        SchemaField('apiVersion', 'string', 'NULLABLE', None, ()),
        SchemaField('dutDeviceId', 'string', 'NULLABLE', None, ()),
        SchemaField('stationDeviceId', 'string', 'NULLABLE', None, ()),
        SchemaField('stationInstallationId', 'string', 'NULLABLE', None, ()),
        SchemaField('fwid', 'string', 'NULLABLE', None, ()),
        SchemaField('roFwid', 'string', 'NULLABLE', None, ()),
        SchemaField('wpswBoot', 'string', 'NULLABLE', None, ()),
        SchemaField('wpswCur', 'string', 'NULLABLE', None, ()),
        SchemaField('ecWp', 'string', 'NULLABLE', None, ()),
        SchemaField('ecWpStatus', 'string', 'NULLABLE', None, ()),
        SchemaField('ecWpDetails', 'string', 'NULLABLE', None, ()),
        SchemaField('biosWp', 'string', 'NULLABLE', None, ()),
        SchemaField('biosWpStatus', 'string', 'NULLABLE', None, ()),
        SchemaField('biosWpDetails', 'string', 'NULLABLE', None, ()),
        SchemaField('modemStatus', 'string', 'NULLABLE', None, ()),
        SchemaField('platformName', 'string', 'NULLABLE', None, ()),
        SchemaField('modelName', 'string', 'NULLABLE', None, ()),
        SchemaField('time', 'timestamp', 'NULLABLE', None, ()),
        SchemaField('dutTime', 'timestamp', 'NULLABLE', None, ()),
        SchemaField('serialNumbers', 'record', 'REPEATED', None, (SchemaField(
            'key', 'string', 'NULLABLE', None,
            ()), SchemaField('value', 'string', 'NULLABLE', None, ()))),
        SchemaField('testStates', 'record', 'REPEATED', None, (SchemaField(
            'path', 'string', 'NULLABLE', None,
            ()), SchemaField('status', 'string', 'NULLABLE', None, ()))),
    ]

  def ConvertEventToRow(self, event):
    """Converts an event to its corresponding BigQuery table row JSON string."""
    if not event.get('__report__', False):
      return None

    row = {}

    row['uuid'] = event.get('uuid')
    row['objectId'] = event.get('objectId')
    row['reportFilePath'] = event.get('reportFilePath')
    row['toolkitVersion'] = event.get('toolkitVersion')
    row['factoryImageVersion'] = event.get('factoryImageVersion')
    row['releaseImageVersion'] = event.get('releaseImageVersion')
    row['hwid'] = event.get('hwid')
    row['phase'] = event.get('phase')
    row['testlistName'] = event.get('testlistName')
    row['testlistStation'] = event.get('testlistStation')
    row['apiVersion'] = event.get('apiVersion')
    row['dutDeviceId'] = event.get('dutDeviceId')
    row['stationDeviceId'] = event.get('stationDeviceId')
    row['stationInstallationId'] = event.get('stationInstallationId')
    row['fwid'] = event.get('fwid')
    row['roFwid'] = event.get('roFwid')
    row['wpswBoot'] = event.get('wpswBoot')
    row['wpswCur'] = event.get('wpswCur')
    row['ecWp'] = event.get('ecWp')
    row['ecWpStatus'] = event.get('ecWpStatus')
    row['ecWpDetails'] = event.get('ecWpDetails')
    row['biosWp'] = event.get('biosWp')
    row['biosWpStatus'] = event.get('biosWpStatus')
    row['biosWpDetails'] = event.get('biosWpDetails')
    row['modemStatus'] = json.dumps(event.get('modemStatus'))
    row['modelName'] = event.get('modelName')
    row['platformName'] = event.get('platformName')
    row['dutTime'] = event.get('dutTime')
    row['time'] = event.get('time')
    row['serialNumbers'] = []
    for key, value in event.get('serialNumbers', {}).items():
      row['serialNumbers'].append({})
      row['serialNumbers'][-1]['key'] = key
      row['serialNumbers'][-1]['value'] = str(value)
    row['testStates'] = []
    for path, status in event.get('testStates', []):
      row['testStates'].append({})
      row['testStates'][-1]['path'] = path
      row['testStates'][-1]['status'] = status

    return json.dumps(row, allow_nan=False)


if __name__ == '__main__':
  plugin_base.main()
