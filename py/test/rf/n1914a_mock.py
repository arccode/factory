#!/usr/bin/env python3
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

from cros.factory.test.rf.scpi_mock import MockServerHandler
from cros.factory.test.rf.scpi_mock import MockTestServer


def SetupLookupTable():
  # Abbreviation for better readability
  AddLookup = MockServerHandler.AddLookup

  # Responses for normal commands
  NORMAL_ERR_RESPONSE = b'+0,"No error"\n'
  NORMAL_ESR_REGISTER = b'+0\n'
  NORMAL_OPC_RESPONSE = b'+1\n'
  AddLookup(br'\*CLS', None)
  AddLookup(br'\*OPC\?', NORMAL_OPC_RESPONSE)
  AddLookup(br'\*ESR\?', NORMAL_ESR_REGISTER)
  AddLookup(br'SYST:ERR\?', NORMAL_ERR_RESPONSE)
  # Identification
  MODEL_NAME = b'Agilent Technologies,N1914A,MY50001187,A2.01.06\n'
  MOCK_MAC_ADDRESS = b'"00:30:d3:20:54:64"\n'
  AddLookup(br'\*IDN\?', MODEL_NAME)
  AddLookup(br'SYST:COMM:LAN:MAC\?', MOCK_MAC_ADDRESS)
  # Measurement format related command
  AddLookup(br'FORM ASCii', None)
  AddLookup(br'FORM REAL', None)
  # Measurement speed related command
  AddLookup(br'SENSe\d:MRATe NORMal', None)
  AddLookup(br'SENSe\d:MRATe DOUBle', None)
  AddLookup(br'SENSe\d:MRATe FAST', None)
  # Trigger related command
  AddLookup(br'TRIGger\d:SOURce IMMediate', None)
  AddLookup(br'INITiate\d:CONTinuous ON', None)
  # Range related command
  AddLookup(br'SENSe\d:POWer:AC:RANGe:AUTO \d', None)
  AddLookup(br'SENSe\d:POWer:AC:RANGe \d', None)
  # Frequency related command
  AddLookup(br'SENSe\d:FREQuency [\d\.]+', None)
  # Average related command
  AddLookup(br'SENSe\d:AVERage:STATe \d', None)
  AddLookup(br'SENSe\d:AVERage:COUNt \d', None)
  # Fetch command in binary format
  # FETCH_EXPECTED_RESPONSE is the IEEE 754 64 bit floating
  # point representation of -65.05119874255999
  FETCH_EXPECTED_RESPONSE = bytes(bytearray([192, 80, 67, 70, 215, 23, 57, 14]))
  AddLookup(br'FETCh\d?', FETCH_EXPECTED_RESPONSE + b'\n')
  # Other command
  AddLookup(br'SENSe\d:CORRection:GAIN\d:STATe \d', None)

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  SetupLookupTable()
  # Starts the server
  SERVER_PORT = 5025
  MockTestServer(('0.0.0.0', SERVER_PORT), MockServerHandler).serve_forever()
