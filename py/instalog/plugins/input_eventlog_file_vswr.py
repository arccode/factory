#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input event_log file VSWR plugin.

Subclasses InputLogFile to correctly parse VSWR test runs from an event_log
file.

Sample VSWR event_log event:

    EVENT: vswr
    LOG_ID: 2d7e8500-d4b7-4067-b029-681c68675715
    PREFIX: VSWR
    SEQ: 27
    TIME: '2016-07-07T20:05:14.300Z'
    config:
      content:
        host:
          network:
            interface: auto
        info:
          last_updated: 2016-03-17 00:00:00
          name: Device VSWR Configuration
        network_analyzer:
          calibration_check_thresholds:
            max: 0.5
            min: -0.5
          measure_segment:
            max_frequency: 6800000000.0
            min_frequency: 2000000000.0
            sample_points: 1601
          possible_ips:
          - 192.168.1.55
        test:
          default_thresholds:
            max: 0.0
            min: -180.0
          device_models:
          - default_thresholds:
              max: 0.0
              min: -170.0
            measurement_sequence:
            - 1:
                name: wifi_main
                thresholds: []
              2:
                name: wifi_aux
                thresholds: []
            name: A00
            serial_number_regex: ^(.*)$
      file_path: rf/vswr_config.yaml
    dut:
      serial_number: D300005
    fixture_id: null
    network_analyzer:
      calibration_traces:
        parameters:
        - S11
        - S22
        traces:
          S11:
          - -0.028368414332200002
          - -0.027081608928599999
          - -0.025944533446899998
          - -0.020077736127199999
          - -0.022951841555000001
          S22:
          - -0.020293469076899998
          - -0.0093615634553599995
          - -0.020552330640700001
          - -0.023267613964100001
          - -0.021697542892900001
        x_axis:
        - 2000000000.0
        - 2003000000.0
        - 2006000000.0
        - 2009000000.0
        - 2012000000.0
      id: MY00000000
      ip: 192.168.1.55
    panel_serial: D300005
    test:
      end_time: 2016-07-07 13:05:13.079018
      failures: []
      fixture_id: null
      hash: 9b974ec2-1855-429c-be39-4e70ef990ea2
      invocation: null
      path: VSWR
      results:
        wifi_aux: {}
        wifi_main: {}
      start_time: 2016-07-07 12:59:27.470292
      traces:
        wifi_aux:
          2000: -0.60675784485299999
          2003: -0.61120105435299998
          2006: -0.62993682830499997
          2009: -0.64443275717000004
          2012: -0.66030253672299999
        wifi_main:
          2000: -0.60415915740799997
          2003: -0.61717472182099997
          2006: -0.63072568871900003
          2009: -0.64414262685000001
          2012: -0.65762982474200005
    #s
    ---
"""

import datetime

from cros.factory.instalog import datatypes
from cros.factory.instalog import plugin_base
from cros.factory.instalog.plugins import input_eventlog_file


class InputEventlogFileVSWR(input_eventlog_file.InputEventlogFile):

  def ConvertToVSWRTestlog(self, path, dct):
    """Converts the given event_log dict to a Testlog VSWR test_run event.

    If the provided event_log event corresponds to a VSWR run, convert it to
    a Testlog VSWR test_run event, and return it.  Otherwise, return None.

    Args:
      path: Path to the event_log file in question.
      dct: A dictionary containing the event_log event data.
    """
    if dct['EVENT'] != 'vswr':
      return None

    def DeserializeDateTime(string):
      return datetime.datetime.strptime(string, '%Y-%m-%dT%H:%M:%S.%fZ')

    test_run = {}
    test_run['__testlog__'] = True
    test_run['uuid'] = dct['test']['hash']
    test_run['type'] = 'station.test_run'
    test_run['apiVersion'] = '0.1'
    test_run['time'] = DeserializeDateTime(dct['TIME'])
    test_run['stationName'] = 'VSWR'
    test_run['seq'] = int(dct['SEQ'])
    test_run['stationDeviceId'] = path.rpartition('.')[2]
    test_run['stationInstallationId'] = path.rpartition('.')[2]
    test_run['testRunId'] = dct['test']['hash']
    test_run['testName'] = 'vswr'
    test_run['testType'] = 'vswr'
    test_run['arguments'] = {}

    # TODO(kitching): Figure out how to detect PASS/FAIL.  For reference:
    #                 BOOLEAN(BIT_AND(INTEGER(CASE WHEN REGEXP_MATCH(
    #                     attr.key, r'^test\.results\.wifi_aux\.\d+\.passed$')
    test_run['status'] = 'PASSED'

    test_run['startTime'] = dct['test']['start_time']
    test_run['endTime'] = dct['test']['end_time']
    test_run['duration'] = (test_run['endTime'] -
                            test_run['startTime']).total_seconds()
    test_run['operatorId'] = 'vswr'
    test_run['attachments'] = {}

    # TODO(kitching): Figure out how to detect failures.  For reference:
    #                 BOOLEAN(BIT_AND(INTEGER(CASE WHEN REGEXP_MATCH(
    #                     attr.key, r'^test\.results\.wifi_aux\.\d+\.passed$')
    test_run['failures'] = []

    test_run['serialNumbers'] = {'sub': dct['panel_serial']}
    test_run['parameters'] = {}

    test_run['series'] = {}
    for antenna, measurements in dct['test']['traces'].items():
      test_run['series'][antenna] = {}
      test_run['series'][antenna]['keyUnit'] = 'MHz'
      test_run['series'][antenna]['valueUnit'] = 'dB'
      test_run['series'][antenna]['data'] = []
      for freq, db in measurements.items():
        test_run['series'][antenna]['data'].append({})
        test_run['series'][antenna]['data'][-1]['key'] = freq
        test_run['series'][antenna]['data'][-1]['numericValue'] = db
        # TODO(kitching): Include minimum and maximum.
        # test_run['series'][antenna]['data'][-1]['expectedMinimum']
        # test_run['series'][antenna]['data'][-1]['expectedMaximum']

    return datatypes.Event(test_run)

  def ParseEvents(self, path, lines):
    """Returns a generator that creates Instalog Event objects.

    Generator should generate None if any erroneous data was skipped.  This is
    to give ParseAndEmit a chance to check how many bytes have been processed in
    the current batch, and whether it exceeds self.args.batch_max_bytes.

    Args:
      path: Path to the log file in question.
      lines: A generator which sequentially yields lines from the log file,
             where each line includes trailing \r and \n characters.
    """
    event_log_str_gen = self.GetEventlogStrings(lines)
    for event_log_str in event_log_str_gen:
      event_log_dict = self.ParseEventlogEvent(event_log_str, source_name=path)
      if not event_log_dict:
        yield None
      else:
        yield self.ConvertToVSWRTestlog(path, event_log_dict)


if __name__ == '__main__':
  plugin_base.main()
