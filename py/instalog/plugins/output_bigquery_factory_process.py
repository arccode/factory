#!/usr/bin/env python3
#
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""BigQuery upload output plugin.

Subclasses OutputBigQuery to create table rows for factory process events.
"""

import json

# pylint: disable=import-error, no-name-in-module
from google.cloud.bigquery.schema import SchemaField
# pylint: enable=import-error, no-name-in-module

from cros.factory.instalog import plugin_base
from cros.factory.instalog.plugins import output_bigquery


class OutputBigQueryFactoryProcess(output_bigquery.OutputBigQuery):

  def GetTableSchema(self):
    """Returns a list of fields in the table schema."""
    return [
        SchemaField('uuid', 'string', 'NULLABLE', None, ()),
        SchemaField('time', 'timestamp', 'NULLABLE', None, ()),
        SchemaField('startTime', 'timestamp', 'NULLABLE', None, ()),
        SchemaField('decompressEndTime', 'timestamp', 'NULLABLE', None, ()),
        SchemaField('endTime', 'timestamp', 'NULLABLE', None, ()),
        SchemaField('duration', 'float', 'NULLABLE', None, ()),
        SchemaField('status', 'record', 'REPEATED', None,
                    (SchemaField('code', 'integer', 'NULLABLE', None, ()), )),
        SchemaField('messages', 'record', 'REPEATED', None,
                    (SchemaField('message', 'string', 'NULLABLE', None, ()), )),
    ]

  def ConvertEventToRow(self, event):
    """Converts an event to its corresponding BigQuery table row JSON string."""
    if not event.get('__process__', False):
      return None

    row = {}

    row['uuid'] = event.get('uuid')
    row['time'] = event.get('time')
    row['startTime'] = event.get('startTime')
    row['decompressEndTime'] = event.get('decompressEndTime')
    row['endTime'] = event.get('endTime')
    row['duration'] = event.get('duration')
    row['status'] = []
    for code in event.get('status', []):
      row['status'].append({})
      row['status'][-1]['code'] = code
    row['messages'] = []
    for message in event.get('message', []):
      row['messages'].append({})
      row['messages'][-1]['message'] = message

    return json.dumps(row, allow_nan=False)


if __name__ == '__main__':
  plugin_base.main()
