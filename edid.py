#!/usr/bin/env python
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""EDID Parser (light-weight parse-edid replacement)

This module provides simple parsing of EDID (
http://en.wikipedia.org/wiki/Extended_display_identification_data ) because the
full-feature parser (parse-edid) has too much dependency.

TODO(hungte) Use parse-edid if available.
"""


import sys


# EDID Constants
EDID_VERSION = 0x01
EDID_MAGIC = '\x00\xff\xff\xff\xff\xff\xff\x00'

EDID_MAGIC_OFFSET = 0
EDID_MANUFACTURER_ID_OFFSET = 8
EDID_PRODUCT_ID_OFFSET = 10
EDID_VERSION_OFFSET = 18
EDID_REVISION_OFFSET = 19
EDID_PIXEL_CLOCK_OFFSET = 54
EDID_HORIZONTAL_OFFSET = 56
EDID_HORIZONTAL_HIGH_OFFSET = 58
EDID_VERTICAL_OFFSET = 59
EDID_VERTICAL_HIGH_OFFSET = 61
EDID_CHECKSUM_OFFSET = 127
EDID_MINIMAL_SIZE = 128
EDID_MANUFACTURER_ID_BITS = 5

EDID_MANUFACTURER_ID = 'manufactuer_id'
EDID_PRODUCT_ID = 'product_id'
EDID_WIDTH = 'width'
EDID_HEIGHT = 'height'


def parse_edid(blob):
  """Parses a in-memory EDID blob.

  Args:
    blob: a binary blob with encoded EDID.

  Returns:
    A dictionary of extracted information, or raise ValueError if the blob is
    not a valid EDID record.
  """

  def read_short(offset):
    return ((ord(blob[offset]) << 8) | ord(blob[offset + 1]))

  data = {}

  # Check size, magic, and version
  if len(blob) < EDID_MINIMAL_SIZE:
    raise ValueError("Length too small")
  if (blob[EDID_MAGIC_OFFSET:(EDID_MAGIC_OFFSET + len(EDID_MAGIC))] !=
      EDID_MAGIC):
    raise ValueError("Incorrect header")
  if ord(blob[EDID_VERSION_OFFSET]) != EDID_VERSION:
    raise ValueError("Unsupported EDID version")

  # Verify checksum
  if sum([ord(char) for char in blob[:EDID_CHECKSUM_OFFSET+1]]) % 0x100 != 0:
    raise ValueError("Checksum error.")

  # Currently we don't support EDID not using pixel clock
  pixel_clock = read_short(EDID_PIXEL_CLOCK_OFFSET)
  if not pixel_clock:
    raise ValueError("Non-pixel clock format is not supported yet")

  # Extract manufactuer
  vendor_name = ''
  vendor_code = read_short(EDID_MANUFACTURER_ID_OFFSET)

  # vendor_code: [0 | char1 | char2 | char3]
  for i in range(2, -1, -1):
    vendor_char = (vendor_code >> (i * EDID_MANUFACTURER_ID_BITS)) & 0x1F
    vendor_char = chr(vendor_char + ord('@'))
    vendor_name += vendor_char
  data[EDID_MANUFACTURER_ID] = vendor_name

  product_id = read_short(EDID_PRODUCT_ID_OFFSET)
  data[EDID_PRODUCT_ID] = product_id

  width = (ord(blob[EDID_HORIZONTAL_OFFSET]) |
           ((ord(blob[EDID_HORIZONTAL_HIGH_OFFSET]) >> 4) << 8))
  height = (ord(blob[EDID_VERTICAL_OFFSET]) |
            ((ord(blob[EDID_VERTICAL_HIGH_OFFSET]) >> 4) << 8))
  data[EDID_WIDTH] = width
  data[EDID_HEIGHT] = height
  return data


def parse_edid_file(file_name):
  with open(file_name, 'r') as edid_handle:
    return parse_edid(edid_handle.read(EDID_MINIMAL_SIZE))


if __name__ == '__main__':
  if len(sys.argv) < 2:
    print parse_edid(sys.stdin.read())
  else:
    for edid_file in sys.argv[1:]:
      print parse_edid_file(edid_file)
