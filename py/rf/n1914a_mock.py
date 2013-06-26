#!/usr/bin/env python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Mock the N1914A power meter.

This program is mainly for developing software locally without physically have
a N1914A power meter. A local TCP server that simulate the behavior of a N1914A
will be started.
"""

import logging

from scpi_mock import MockServerHandler, MockTestServer

def SetupLookupTable():
  # Responses for normal commands
  NORMAL_ERR_RESPONSE = '+0,"No error"\n'
  NORMAL_ESR_REGISTER = '+0\n'
  NORMAL_OPC_RESPONSE = '+1\n'
  MockServerHandler.AddLookup(r'\*CLS', None)
  #MockServerHandler.AddLookup(r'SYST:ERR\?', NORMAL_ERR_RESPONSE)
  MockServerHandler.AddLookup(r'\*OPC\?', NORMAL_OPC_RESPONSE)
  MockServerHandler.AddLookup(r'\*ESR\?', NORMAL_ESR_REGISTER)
  MockServerHandler.AddLookup(r'SYST:ERR\?', NORMAL_ERR_RESPONSE)
  # Identification
  MODEL_NAME = 'Agilent Technologies,N1914A,MY50001187,A2.01.06\n'
  MockServerHandler.AddLookup(r'\*IDN\?', MODEL_NAME)
  # Measurement format related command
  MockServerHandler.AddLookup(r'FORM ASCii', None)
  MockServerHandler.AddLookup(r'FORM REAL', None)
  # Measurement speed related command
  MockServerHandler.AddLookup(r'SENSe\d:MRATe NORMal', None)
  MockServerHandler.AddLookup(r'SENSe\d:MRATe DOUBle', None)
  MockServerHandler.AddLookup(r'SENSe\d:MRATe FAST', None)
  # Trigger related command
  MockServerHandler.AddLookup(r'TRIGger\d:SOURce IMMediate', None)
  MockServerHandler.AddLookup(r'INITiate\d:CONTinuous ON', None)
  # Range related command
  MockServerHandler.AddLookup(r'SENSe\d:POWer:AC:RANGe:AUTO \d', None)
  MockServerHandler.AddLookup(r'SENSe\d:POWer:AC:RANGe \d', None)
  # Frequency related command
  MockServerHandler.AddLookup(r'SENSe\d:FREQuency [\d\.]+', None)
  # Average related command
  MockServerHandler.AddLookup(r'SENSe\d:AVERage:STATe \d', None)
  MockServerHandler.AddLookup(r'SENSe\d:AVERage:COUNt \d', None)
  # Fetch command in binary format
  # FETCH_EXPECTED_RESPONSE is the IEEE 754 64 bit floating
  # point representation of -65.05119874255999
  FETCH_EXPECTED_RESPONSE = str(bytearray([192, 80, 67, 70, 215, 23, 57, 14]))
  MockServerHandler.AddLookup(r'FETCh\d?', FETCH_EXPECTED_RESPONSE + '\n')
  # Other command
  MockServerHandler.AddLookup(r'SENSe\d:CORRection:GAIN\d:STATe \d', None)

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  SetupLookupTable()
  # Starts the server
  SERVER_PORT = 5025
  # pylint: disable=E1101
  MockTestServer(('0.0.0.0', SERVER_PORT), MockServerHandler).serve_forever()
