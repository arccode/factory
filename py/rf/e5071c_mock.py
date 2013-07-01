#!/usr/bin/env python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
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

import logging
import re

from scpi_mock import MockServerHandler, MockTestServer

class E5601CMock(object):
  # Class level variable to keep current status
  _sweep_type = None
  _sweep_segment = None
  _x_axis = None
  _trace_config = None

  # regular expression of SCPI command
  RE_SET_SWEEP_TYPE = r':SENS:SWE.*:TYPE (SEGM.*)$'
  RE_GET_SWEEP_TYPE = r':SENS:SWE.*:TYPE\?$'
  RE_SET_SWEEP_SEGMENT = r':SENS:SEGM.*:DATA (.*)$'
  RE_GET_SWEEP_SEGMENT = r':SENS:SEGM.*:DATA\?$'
  RE_GET_X_AXIS = r':CALC.*:SEL.*:DATA:XAX.*\?$'
  RE_SET_TRACE_COUNT = r':CALC:PAR:COUN.* (.*)$'
  RE_GET_TRACE_COUNT = r':CALC:PAR:COUN.*\?$'

  # Constants
  SWEEP_SEGMENT_PREFIX = ['5', '0', '0', '0', '0', '0']
  SWEEP_SEGMENT_PREFIX_LEN = len(SWEEP_SEGMENT_PREFIX)
  # A typical tuple is (start_freq, end_freq, num_of_points)
  SEGMENT_TUPLE_LEN = 3

  @classmethod
  def SetSweepType(cls, input_str):
    match_obj = re.match(cls.RE_SET_SWEEP_TYPE, input_str)
    cls._sweep_type = match_obj.group(1)

  @classmethod
  def GetSweepType(cls, input_str): # pylint: disable=W0613
    return cls._sweep_type + '\n'

  @classmethod
  def SetSweepSegment(cls, input_str):
    match_obj = re.match(cls.RE_SET_SWEEP_SEGMENT, input_str)
    data = match_obj.group(1)
    parameters = data.split(',')
    assert (
        cls.SWEEP_SEGMENT_PREFIX ==
        parameters[:cls.SWEEP_SEGMENT_PREFIX_LEN]), (
        "Only specific prefix is support for command SENS:SEGM:DATA")
    # Parse and store the segments
    num_of_segments = int(parameters[cls.SWEEP_SEGMENT_PREFIX_LEN])
    assert len(parameters) == (
        cls.SEGMENT_TUPLE_LEN*num_of_segments +
        len(cls.SWEEP_SEGMENT_PREFIX) + 1), (
        "Length of parameters is %d, not supported") % len(parameters)

    cls._sweep_segment = list()
    x_axis_points = list()
    for idx in xrange(cls.SWEEP_SEGMENT_PREFIX_LEN + 1, len(parameters), 3):
      start_freq = float(parameters[idx])
      end_freq = float(parameters[idx+1])
      sample_points = int(parameters[idx+2])
      assert sample_points == 2, (
          'sample points only support two (start and end)')

      x_axis_points.append(start_freq)
      x_axis_points.append(end_freq)
      cls._sweep_segment.append((start_freq, end_freq, sample_points))

    # Construct the X-axis
    cls._x_axis = sorted(x_axis_points)

  @classmethod
  def GetSweepSegment(cls, input_str): # pylint: disable=W0613
    return_strings = list()
    return_strings.extend(cls.SWEEP_SEGMENT_PREFIX)
    return_strings.append(str(len(cls._sweep_segment)))
    for start_freq, end_freq, sample_points in cls._sweep_segment:
      return_strings.extend(
        ['%.1f' % start_freq, '%.1f' % end_freq, str(sample_points)])
    return ','.join(return_strings) + '\n'

  @classmethod
  def GetXAxis(cls, input_str): # pylint: disable=W0613
    return ','.join(['%+.11E' % x for x in cls._x_axis]) + '\n'

  @classmethod
  def SetTraceCount(cls, input_str):
    match_obj = re.match(cls.RE_SET_TRACE_COUNT, input_str)
    lens = int(match_obj.group(1))
    # Prepare equal length of list for further trace setting
    # pylint: disable=W0612
    cls._trace_config = ['UndefinedTrace' for idx in xrange(lens)]

  @classmethod
  def GetTraceCount(cls, input_str): # pylint: disable=W0613
    return str(len(cls._trace_config)) + '\n'

  @classmethod
  def SetupLookupTable(cls):
    # Abbreviation for better readability
    AddLookup = MockServerHandler.AddLookup

    # Identification
    MODEL_NAME = 'Agilent Technologies,E5071C,MY46107723,A.09.30\n'
    AddLookup(r'\*IDN\?$', MODEL_NAME)
    # Error codes related responses
    AddLookup(r'\*CLS$', None)
    NORMAL_ESR_REGISTER = '+0\n'
    AddLookup(r'\*ESR\?$', NORMAL_ESR_REGISTER)
    NORMAL_ERR_RESPONSE = '+0,"No error"\n'
    AddLookup(r'SYST:ERR\?$', NORMAL_ERR_RESPONSE)
    NORMAL_OPC_RESPONSE = '+1\n'
    AddLookup(r'\*OPC\?$', NORMAL_OPC_RESPONSE)

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

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  E5601CMock.SetupLookupTable()
  # Starts the server
  SERVER_PORT = 5025
  # pylint: disable=E1101
  MockTestServer(('0.0.0.0', SERVER_PORT), MockServerHandler).serve_forever()
