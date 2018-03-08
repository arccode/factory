# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HTTP plugin common file."""

import datetime
import json
import time

import instalog_common  # pylint:disable=unused-import
from instalog import json_utils


def From0_1to0_2(event):
  """Upgrades the event format from Testlog API 0.1 to Testlog API 0.2 ."""
  def DateTimeToUnixTimestamp(obj):
    if isinstance(obj, basestring):
      obj = datetime.datetime.strptime(obj, json_utils.FORMAT_DATETIME)

    if isinstance(obj, datetime.datetime):
      return time.mktime(obj.timetuple()) + obj.microsecond * 1e-6
    elif isinstance(obj, float):
      return obj
    else:
      return None

  event['time'] = DateTimeToUnixTimestamp(event['time'])

  if event['type'] == 'station.test_run':
    event['startTime'] = DateTimeToUnixTimestamp(event['startTime'])
    if 'endTime' in event:
      event['endTime'] = DateTimeToUnixTimestamp(event['endTime'])
    if 'status' in event:
      if event['status'] == 'PASSED':
        event['status'] = 'PASS'
      if event['status'] == 'FAILED':
        event['status'] = 'FAIL'
    if 'arguments' in event:
      for name, dct in event['arguments'].iteritems():
        dct['value'] = json.dumps(dct['value'])

    new_parameters = {}
    if 'series' in event:
      for name, dct in event['series'].iteritems():
        key_name = name + '_key'
        value_name = name + '_value'
        new_parameters[key_name] = {'group': name, 'data': []}
        new_parameters[value_name] = {'group': name, 'data': []}
        if 'description' in dct:
          new_parameters[value_name]['description'] = dct['description']
        if 'keyUnit' in dct:
          new_parameters[key_name]['valueUnit'] = dct['keyUnit']
        if 'valueUnit' in dct:
          new_parameters[value_name]['valueUnit'] = dct['valueUnit']
        if 'data' in dct:
          for data in dct['data']:
            new_parameters[key_name]['data'].append(
                {'numericValue': data['key']})
            del data['key']
            new_parameters[value_name]['data'].append(data)
      del event.payload['series']
    if 'parameters' in event:
      for name, dct in event['parameters'].iteritems():
        name = 'parameter_' + name
        new_parameters[name] = {}
        if 'description' in dct:
          new_parameters[name]['description'] = dct['description']
          del dct['description']
        if 'valueUnit' in dct:
          new_parameters[name]['valueUnit'] = dct['valueUnit']
          del dct['valueUnit']
        new_parameters[name]['data'] = [dct]
    if new_parameters:
      event['parameters'] = new_parameters

  event['apiVersion'] = '0.2'

  return event


def UpgradeEvent(event):
  """Upgrades the event format to the latest Testlog API version."""
  if event['apiVersion'] == '0.1':
    event = From0_1to0_2(event)
  return event
