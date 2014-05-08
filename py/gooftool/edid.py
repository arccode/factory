#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrapper for EDID data parsing and loading.

  See for more info:
  http://en.wikipedia.org/wiki/Extended_display_identification_data
"""


import binascii
import logging
import os
import re

from fcntl import ioctl
from time import sleep

import factory_common  # pylint: disable=W0611
from cros.factory.hwdb import hwid_tool
from cros.factory.common import Shell


# Constants lifted from EDID documentation.
VERSION = 0x01
MAGIC = '\x00\xff\xff\xff\xff\xff\xff\x00'
MAGIC_OFFSET = 0
MANUFACTURER_ID_OFFSET = 8
PRODUCT_ID_OFFSET = 10
VERSION_OFFSET = 18
REVISION_OFFSET = 19
PIXEL_CLOCK_OFFSET = 54
HORIZONTAL_OFFSET = 56
HORIZONTAL_HIGH_OFFSET = 58
VERTICAL_OFFSET = 59
VERTICAL_HIGH_OFFSET = 61
CHECKSUM_OFFSET = 127
MINIMAL_SIZE = 128
MANUFACTURER_ID_BITS = 5

PREFIX_TEGRA = 'edid[000]'


def Parse(content):
  """Public interface of EDID parser.

  Args:
    content: EDID data retrieved from device.
  """
  # Check if it's from Tegra.
  if content.startswith(PREFIX_TEGRA):
    return _ParseTegra(content)
  else:
    return _ParseBinaryBlob(content)

def _ParseTegra(content):
  """Parser for EDID data exported by tegra_edid driver.

  When tegra_edid driver is used, the exported EDID is in text format, ex:

    edid[000] = 00 ff ff ff ff ff ff 00 06 af 2c 13 00 00 00 00
    edid[010] = 00 18 01 03 80 1d 10 78 0a bb f5 94 55 54 90 27
    edid[020] = 23 50 54 00 00 00 01 01 01 01 01 01 01 01 01 01
    edid[030] = 01 01 01 01 01 01 26 1b 56 64 50 00 16 30 30 20
    edid[040] = 36 00 25 a4 10 00 00 18 00 00 00 0f 00 00 00 00
    edid[050] = 00 00 00 00 00 00 00 00 00 20 00 00 00 fe 00 41
    edid[060] = 55 4f 0a 20 20 20 20 20 20 20 20 20 00 00 00 fe
    edid[070] = 00 42 31 33 33 58 54 4e 30 31 2e 33 20 0a 00 4b

  Thus, we have to strip the first 12 characters, all white spaces, and all
  newline characters, then transform the rest from hex code into a binary blob.

  Args:
    content: EDID file content from a Tegra device.
  """
  return _ParseBinaryBlob(binascii.unhexlify(
      re.sub(r'\s|(edid\[\d{3}\] = )', '', content)))

def _ParseBinaryBlob(blob):
  """Binary EDID Parser (light-weight parse-edid replacement).

  Simple parsing of EDID.  The full-feature parser (parse-edid) has
  many more dependencies, and so is too heavy-weight for use here.

  TODO(hungte) Use parse-edid if it becomes practical/available.
  Specifically once we know that it will be available on all of our
  systems.

  Args:
    blob: a binary blob with encoded EDID.

  Returns:
    A dict of extracted keys to extracted EDID fields.  Return None if
    the blob is not a valid EDID record, and also log warning messages
    indicating the reason for parsing failure.
  """
  def read_short(offset):
    return ((ord(blob[offset]) << 8) | ord(blob[offset + 1]))
  # Check size, magic, and version
  if len(blob) < MINIMAL_SIZE:
    logging.warning("EDID parsing error: length too small.")
    return None
  if (blob[MAGIC_OFFSET:(MAGIC_OFFSET + len(MAGIC))] !=
      MAGIC):
    logging.warning("EDID parse error: incorrect header.")
    return None
  if ord(blob[VERSION_OFFSET]) != VERSION:
    logging.warning("EDID parse error: unsupported EDID version.")
    return None
  # Verify checksum
  if sum([ord(char) for char in blob[:CHECKSUM_OFFSET+1]]) % 0x100 != 0:
    logging.warning("EDID parse error: checksum error.")
    return None
  # Currently we don't support EDID not using pixel clock
  pixel_clock = read_short(PIXEL_CLOCK_OFFSET)
  if not pixel_clock:
    logging.warning("EDID parse error: "
                    "non-pixel clock format is not supported yet.")
    return None
  # Extract manufactuer
  vendor_name = ''
  vendor_code = read_short(MANUFACTURER_ID_OFFSET)
  # vendor_code: [0 | char1 | char2 | char3]
  for i in range(2, -1, -1):
    vendor_char = (vendor_code >> (i * MANUFACTURER_ID_BITS)) & 0x1F
    vendor_char = chr(vendor_char + ord('@'))
    vendor_name += vendor_char
  product_id = read_short(PRODUCT_ID_OFFSET)
  width = (ord(blob[HORIZONTAL_OFFSET]) |
           ((ord(blob[HORIZONTAL_HIGH_OFFSET]) >> 4) << 8))
  height = (ord(blob[VERTICAL_OFFSET]) |
            ((ord(blob[VERTICAL_HIGH_OFFSET]) >> 4) << 8))
  return {'vendor': vendor_name, 'product_id': '%04x' % product_id,
          'width': str(width), 'height': str(height),
          hwid_tool.COMPACT_PROBE_STR: (
              '%s:%04x [%dx%d]' % (vendor_name, product_id, width, height))}


def _I2cDump(bus, address, size):
  """Reads binary dump from i2c bus."""
  if isinstance(bus, int):
    bus = '/dev/i2c-%d' % bus
  fd = -1
  I2C_SLAVE = 0x0703
  blob = None
  try:
    fd = os.open(bus, os.O_RDWR)
    if ioctl(fd, I2C_SLAVE, address) != 0:
      return blob
    sleep(0.05)  # Wait i2c to get ready
    if os.write(fd, chr(0)) == 1:
      blob = os.read(fd, size)
  except:  # pylint: disable=W0702
    pass
  finally:
    if fd >= 0:
      os.close(fd)
  return blob


def LoadFromI2c(path):
  """Run Parse against the output of _I2cDump on the specified path."""
  I2C_LVDS_ADDRESS = 0x50
  command = 'i2cdetect -y -r %s %d %d' % (
      path.split('-')[1], I2C_LVDS_ADDRESS, I2C_LVDS_ADDRESS)
  # Make sure there is a device in I2C_LVDS_ADDRESS
  blob = None
  if not '--' in Shell(command).stdout:
    blob = _I2cDump(path, I2C_LVDS_ADDRESS, MINIMAL_SIZE)
  return Parse(blob) if blob is not None else None


if __name__ == '__main__':
  # For debugging, print parse result for specified i2c bus.
  import sys
  if len(sys.argv) != 2:
    sys.exit('You must provide the i2c bus number as an argument.')
  print repr(LoadFromI2c(int(sys.argv[1])))
