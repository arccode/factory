#!/usr/bin/env python2
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Mock the N1914A power meter.

This program is mainly for developing software locally without physically have
a N1914A power meter. A local TCP server that simulate the behavior of a N1914A
will be started.
"""

import logging

from scpi_mock import MockServerHandler
from scpi_mock import MockTestServer


def SetupLookupTable():
  # Abbreviation for better readability
  AddLookup = MockServerHandler.AddLookup

  # Responses for normal commands
  NORMAL_ERR_RESPONSE = '+0,"No error"\n'
  NORMAL_ESR_REGISTER = '+0\n'
  NORMAL_OPC_RESPONSE = '+1\n'
  AddLookup(r'\*CLS', None)
  AddLookup(r'\*OPC\?', NORMAL_OPC_RESPONSE)
  AddLookup(r'\*ESR\?', NORMAL_ESR_REGISTER)
  AddLookup(r'SYST:ERR\?', NORMAL_ERR_RESPONSE)
  # Identification
  MODEL_NAME = 'Agilent Technologies,N1914A,MY50001187,A2.01.06\n'
  MOCK_MAC_ADDRESS = '"00:30:d3:20:54:64"\n'
  AddLookup(r'\*IDN\?', MODEL_NAME)
  AddLookup(r'SYST:COMM:LAN:MAC\?', MOCK_MAC_ADDRESS)
  # Measurement format related command
  AddLookup(r'FORM ASCii', None)
  AddLookup(r'FORM REAL', None)
  # Measurement speed related command
  AddLookup(r'SENSe\d:MRATe NORMal', None)
  AddLookup(r'SENSe\d:MRATe DOUBle', None)
  AddLookup(r'SENSe\d:MRATe FAST', None)
  # Trigger related command
  AddLookup(r'TRIGger\d:SOURce IMMediate', None)
  AddLookup(r'INITiate\d:CONTinuous ON', None)
  # Range related command
  AddLookup(r'SENSe\d:POWer:AC:RANGe:AUTO \d', None)
  AddLookup(r'SENSe\d:POWer:AC:RANGe \d', None)
  # Frequency related command
  AddLookup(r'SENSe\d:FREQuency [\d\.]+', None)
  # Average related command
  AddLookup(r'SENSe\d:AVERage:STATe \d', None)
  AddLookup(r'SENSe\d:AVERage:COUNt \d', None)
  # Fetch command in binary format
  # FETCH_EXPECTED_RESPONSE is the IEEE 754 64 bit floating
  # point representation of -65.05119874255999
  FETCH_EXPECTED_RESPONSE = str(bytearray([192, 80, 67, 70, 215, 23, 57, 14]))
  AddLookup(r'FETCh\d?', FETCH_EXPECTED_RESPONSE + '\n')
  # Other command
  AddLookup(r'SENSe\d:CORRection:GAIN\d:STATe \d', None)

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  SetupLookupTable()
  # Starts the server
  SERVER_PORT = 5025
  MockTestServer(('0.0.0.0', SERVER_PORT), MockServerHandler).serve_forever()
