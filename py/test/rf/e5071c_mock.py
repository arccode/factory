#!/usr/bin/env python2
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Mock the E5071C ENA Series Network Analyzer

This program is mainly for developing software locally without a Network
Analyzer. A local TCP server that simulate the behavior of a E5071C will
be started.

For detail format and meaning of the SCPI command, please refer to its
offical manual or online help:
  http://ena.tm.agilent.com/e5071c/manuals/webhelp/eng/
"""

import argparse
import logging
import os
import re
import SimpleHTTPServer
import SocketServer
import threading

from scpi_mock import MockServerHandler
from scpi_mock import MockTestServer


class E5601CMock(object):
  # Class level variable to keep current status
  _sweep_type = None
  _sweep_segment = None
  _x_axis = None
  _trace_config = None
  _trace_map = {}

  # regular expression of SCPI command
  RE_SET_TRIGGER_CONTINUOUS = r':INIT.*(\d):CONT.* (ON|OFF)$'
  RE_TRIGGER_IMMEDIATEDLY = r':INIT.*(\d):IMM.*$'
  RE_SET_SWEEP_TYPE = r':SENS:SWE.*:TYPE (SEGM.*|LIN.*)$'
  RE_GET_SWEEP_TYPE = r':SENS:SWE.*:TYPE\?$'
  RE_SET_SWEEP_SEGMENT = r':SENS:SEGM.*:DATA (.*)$'
  RE_GET_SWEEP_SEGMENT = r':SENS:SEGM.*:DATA\?$'
  RE_GET_X_AXIS = r':CALC.*:SEL.*:DATA:XAX.*\?$'
  RE_SET_TRACE_COUNT = r':CALC:PAR:COUN.* (.*)$'
  RE_GET_TRACE_COUNT = r':CALC:PAR:COUN.*\?$'
  RE_SET_TRACE_CONFIG = r':CALC:PAR.*(\d):DEF.* [Ss](\d)(\d)$'
  RE_GET_TRACE_CONFIG = r':CALC:PAR.*(\d):DEF.*\?$'
  RE_GET_TRACE = r':CALC:TRACE(\d):DATA:FDAT\?$'
  RE_SAVE_SCREENSHOT = r':MMEM.*:STOR.*:IMAG.* (.*)$'
  RE_SET_MARKER = r':CALC.*([\d]+):SEL.*:MARK.*([\d]+):X (.*)$'
  RE_SET_FREQ_START = r':SENS:FREQ:STAR.* (.*)$'
  RE_SET_FREQ_STOP = r':SENS:FREQ:STOP (.*)$'

  # Constants
  SWEEP_SEGMENT_PREFIX = ['5', '0', '0', '0', '0', '0']
  SWEEP_SEGMENT_PREFIX_LEN = len(SWEEP_SEGMENT_PREFIX)
  # A typical tuple is (start_freq, end_freq, num_of_points)
  SEGMENT_TUPLE_LEN = 3
  # Value used when no pre-defined trace is found.
  DEFAULT_SIGNAL = -10.0

  @classmethod
  def LoadTrace(cls, trace_name, csv_file_path):
    # TODO(itspeter): Load trace saved from E5071C and replay it.
    raise NotImplementedError

  @classmethod
  def SetTriggerContinuous(cls, input_str):
    match_obj = re.match(cls.RE_SET_TRIGGER_CONTINUOUS, input_str)
    channel = int(match_obj.group(1))
    state = match_obj.group(2)
    logging.info('Simulated to set trigger continuous to %s on channel %d',
                 state, channel)

  @classmethod
  def TriggerImmediately(cls, input_str):
    match_obj = re.match(cls.RE_TRIGGER_IMMEDIATEDLY, input_str)
    channel = int(match_obj.group(1))
    logging.info('Simulated to trigger immediately on channel %d', channel)

  @classmethod
  def SetSweepType(cls, input_str):
    match_obj = re.match(cls.RE_SET_SWEEP_TYPE, input_str)
    cls._sweep_type = match_obj.group(1)

  @classmethod
  def GetSweepType(cls, input_str):
    del input_str  # Unused.
    return cls._sweep_type + '\n'

  @classmethod
  def SetSweepSegment(cls, input_str):
    match_obj = re.match(cls.RE_SET_SWEEP_SEGMENT, input_str)
    data = match_obj.group(1)
    parameters = data.split(',')
    assert (
        cls.SWEEP_SEGMENT_PREFIX ==
        parameters[:cls.SWEEP_SEGMENT_PREFIX_LEN]), (
            'Only specific prefix is support for command SENS:SEGM:DATA')
    # Parse and store the segments
    num_of_segments = int(parameters[cls.SWEEP_SEGMENT_PREFIX_LEN])
    assert len(parameters) == (
        cls.SEGMENT_TUPLE_LEN * num_of_segments +
        len(cls.SWEEP_SEGMENT_PREFIX) + 1), (
            'Length of parameters is %d, not supported') % len(parameters)

    cls._sweep_segment = []
    x_axis_points = []
    for idx in xrange(cls.SWEEP_SEGMENT_PREFIX_LEN + 1, len(parameters), 3):
      start_freq = float(parameters[idx])
      end_freq = float(parameters[idx + 1])
      sample_points = int(parameters[idx + 2])
      assert sample_points == 2, (
          'sample points only support two (start and end)')

      x_axis_points.append(start_freq)
      x_axis_points.append(end_freq)
      cls._sweep_segment.append((start_freq, end_freq, sample_points))

    # Construct the X-axis
    cls._x_axis = sorted(x_axis_points)

  @classmethod
  def GetSweepSegment(cls, input_str):
    del input_str  # Unused.
    return_strings = []
    return_strings.extend(cls.SWEEP_SEGMENT_PREFIX)
    return_strings.append(str(len(cls._sweep_segment)))
    for start_freq, end_freq, sample_points in cls._sweep_segment:
      return_strings.extend(
          ['%.1f' % start_freq, '%.1f' % end_freq, str(sample_points)])
    return ','.join(return_strings) + '\n'

  @classmethod
  def GetXAxis(cls, input_str):
    del input_str  # Unused.
    return ','.join(['%+.11E' % x for x in cls._x_axis]) + '\n'

  @classmethod
  def SetTraceCount(cls, input_str):
    match_obj = re.match(cls.RE_SET_TRACE_COUNT, input_str)
    lens = int(match_obj.group(1))
    # Prepare equal length of list for further trace setting
    cls._trace_config = ['UndefinedTrace' for unused_idx in xrange(lens)]

  @classmethod
  def GetTraceCount(cls, input_str):
    del input_str  # Unused.
    return str(len(cls._trace_config)) + '\n'

  @classmethod
  def SetTraceConfig(cls, input_str):
    match_obj = re.match(cls.RE_SET_TRACE_CONFIG, input_str)
    parameter_idx = int(match_obj.group(1)) - 1  # index starts from 0
    assert parameter_idx < len(cls._trace_config), (
        'Index out of predefined trace size %d') % len(cls._trace_config)
    port_x = int(match_obj.group(2))
    port_y = int(match_obj.group(3))
    cls._trace_config[parameter_idx] = 'S%d%d' % (port_x, port_y)

  @classmethod
  def GetTraceConfig(cls, input_str):
    match_obj = re.match(cls.RE_GET_TRACE_CONFIG, input_str)
    parameter_idx = int(match_obj.group(1)) - 1  # index starts from 0
    assert parameter_idx < len(cls._trace_config), (
        'Index out of predefined trace size %d') % len(cls._trace_config)
    return cls._trace_config[parameter_idx] + '\n'

  @classmethod
  def GetTrace(cls, input_str):
    match_obj = re.match(cls.RE_GET_TRACE, input_str)
    parameter_idx = int(match_obj.group(1)) - 1  # index starts from 0
    assert parameter_idx < len(cls._trace_config), (
        'Index out of predefined trace size %d') % len(cls._trace_config)

    trace_info = cls._trace_map.get(cls._trace_config[parameter_idx], None)
    if not trace_info:
      logging.info('No existing trace info for %s',
                   cls._trace_config[parameter_idx])
      # Set trace_info to an empty dict so DEFAULT_SIGNAL will be returned
      trace_info = {}

    values = []
    for x_pos in sorted(cls._x_axis):
      signal = trace_info.get(x_pos, None)
      if not signal:
        logging.info('Freq %15.2f is not defined in trace, '
                     'use default value %15.2f', x_pos, cls.DEFAULT_SIGNAL)
        signal = cls.DEFAULT_SIGNAL
      values.append('%+.11E' % signal)
      # Second is always 0 when the data format is not the Smith chart
      values.append('%+.11E' % 0)
    return ','.join(values) + '\n'

  @classmethod
  def SaveScreenshot(cls, input_str):
    match_obj = re.match(cls.RE_SAVE_SCREENSHOT, input_str)
    filename = match_obj.group(1)
    logging.info('Simulated screenshot saved under %r', filename)

  @classmethod
  def SetMarker(cls, input_str):
    match_obj = re.match(cls.RE_SET_MARKER, input_str)
    active_channel = int(match_obj.group(1))
    marker_num = int(match_obj.group(2))
    marker_freq = float(match_obj.group(3))
    logging.info('Simulated marker setting: channel[%d], '
                 'marker[%d] to freq[%15.2f]',
                 active_channel, marker_num, marker_freq)

  @classmethod
  def SetFrequencyStart(cls, input_str):
    match_obj = re.match(cls.RE_SET_FREQ_START, input_str)
    freq = float(match_obj.group(1))
    logging.info('Simulated spectrum to start at [%15.2f]', freq)

  @classmethod
  def SetFrequencyStop(cls, input_str):
    match_obj = re.match(cls.RE_SET_FREQ_STOP, input_str)
    freq = float(match_obj.group(1))
    logging.info('Simulated spectrum to stop at [%15.2f]', freq)

  @classmethod
  def SetupLookupTable(cls):
    # Abbreviation for better readability
    AddLookup = MockServerHandler.AddLookup

    # Identification
    MODEL_NAME = 'Agilent Technologies,E5071C,MY99999999,A.09.30\n'
    AddLookup(r'\*IDN\?$', MODEL_NAME)
    # Error codes related responses
    AddLookup(r'\*CLS$', None)
    NORMAL_ESR_REGISTER = '+0\n'
    AddLookup(r'\*ESR\?$', NORMAL_ESR_REGISTER)
    NORMAL_ERR_RESPONSE = '+0,"No error"\n'
    AddLookup(r'SYST:ERR\?$', NORMAL_ERR_RESPONSE)
    NORMAL_OPC_RESPONSE = '+1\n'
    AddLookup(r'\*OPC\?$', NORMAL_OPC_RESPONSE)

    # Trigger related
    AddLookup(cls.RE_SET_TRIGGER_CONTINUOUS, cls.SetTriggerContinuous)
    AddLookup(cls.RE_TRIGGER_IMMEDIATEDLY, cls.TriggerImmediately)

    # Sweep type
    AddLookup(cls.RE_SET_SWEEP_TYPE, cls.SetSweepType)
    AddLookup(cls.RE_GET_SWEEP_TYPE, cls.GetSweepType)

    # Sweep segment
    AddLookup(cls.RE_SET_SWEEP_SEGMENT, cls.SetSweepSegment)
    AddLookup(cls.RE_GET_SWEEP_SEGMENT, cls.GetSweepSegment)

    # X-axis measure point query
    AddLookup(cls.RE_GET_X_AXIS, cls.GetXAxis)

    # Trace configuration
    AddLookup(cls.RE_SET_TRACE_COUNT, cls.SetTraceCount)
    AddLookup(cls.RE_GET_TRACE_COUNT, cls.GetTraceCount)
    AddLookup(cls.RE_SET_TRACE_CONFIG, cls.SetTraceConfig)
    AddLookup(cls.RE_GET_TRACE_CONFIG, cls.GetTraceConfig)

    # Trace measurement
    AddLookup(cls.RE_GET_TRACE, cls.GetTrace)

    # Screenshot
    AddLookup(cls.RE_SAVE_SCREENSHOT, cls.SaveScreenshot)

    # Marker
    AddLookup(cls.RE_SET_MARKER, cls.SetMarker)

    # Linear sweep related setting
    AddLookup(cls.RE_SET_FREQ_START, cls.SetFrequencyStart)
    AddLookup(cls.RE_SET_FREQ_STOP, cls.SetFrequencyStop)


def ServeHttpScreenshot():
  """Serves screenshot url requests.

  Only two URL will be handled:
    /image.asp
    /disp.png

  They will both return a valid, mocked PNG file.
  """
  # Switch current working directory to where PNG exist.
  os.chdir(os.path.join(
      os.path.dirname(os.path.realpath(__file__)), 'e5071c_mock_static'))

  # Starts a simple http server to serve for screenshot.
  httpd = SocketServer.TCPServer(('0.0.0.0', 80),
                                 SimpleHTTPServer.SimpleHTTPRequestHandler)
  httpd_thread = threading.Thread(target=httpd.serve_forever)
  httpd_thread.daemon = True
  httpd_thread.start()
  logging.info('Httpd served at port 80 for screenshot request')

if __name__ == '__main__':
  parser = argparse.ArgumentParser(
      description='Simulates an Agilent E5071C ENA for developing.')
  parser.add_argument('--httpd', action='store_true',
                      help='Mock the http server as well (fixed at port 80)')
  parser.add_argument('--port', action='store', default='5025',
                      help='The SCPI port bind in 0.0.0.0.')
  logging.basicConfig(level=logging.INFO)
  args = parser.parse_args()
  E5601CMock.SetupLookupTable()

  # Starts the servers
  if args.httpd:
    ServeHttpScreenshot()
  server_port = int(args.port)
  logging.info('Going to start E5071C mock at port %d', server_port)
  # pylint: disable=no-member
  ena_host = MockTestServer(('0.0.0.0', server_port), MockServerHandler)
  ena_host.serve_forever()
