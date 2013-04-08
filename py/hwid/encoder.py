#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of HWID v3 encoder."""

import factory_common # pylint: disable=W0611

from cros.factory.hwid import HWID
from cros.factory.hwid.base32 import Base32


def BOMToBinaryString(database, bom):
  """Encodes the given BOM object to a binary string.

  Args:
    database: A Database object that is used to provide device-specific
        information for encoding.

  Returns:
    A binary string.
  """
  database.VerifyBOM(bom)
  bit_length = database.pattern.GetTotalBitLength()
  size = ((bit_length + Base32.BASE32_BIT_WIDTH - 1) /
          Base32.BASE32_BIT_WIDTH * Base32.BASE32_BIT_WIDTH)
  binary_list = size * [0]

  # Fill in header.
  binary_list[0] = bom.encoding_pattern_index
  for i in xrange(1, 5):
    binary_list[i] = (bom.image_id >> (4 - i)) & 1
  # Fill in each bit.
  bit_mapping = database.pattern.GetBitMapping()
  for index, (field, bit_offset) in bit_mapping.iteritems():
    binary_list[index] = (bom.encoded_fields[field] >> bit_offset) & 1
  # Set stop bit.
  binary_list[bit_length - 1] = 1
  return ''.join(['%d' % bit for bit in binary_list])


def BinaryStringToEncodedString(database, binary_string):
  """Encodes the given binary string to a encoded string.

  Args:
    database: A Database object that is used to provide device-specific
        information for encoding.
    binary_string: A string of '0's and '1's.

  Returns:
    An encoded string with board name, base32-encoded HWID, and checksum.
  """
  database.VerifyBinaryString(binary_string)
  b32_string = Base32.Encode(binary_string)
  # Make board name part of the checksum.
  b32_string += Base32.Checksum(database.board.upper() + ' ' + b32_string)
  # Insert dashes to increase readibility.
  b32_string = (
      '-'.join([b32_string[i:i + 4] for i in xrange(0, len(b32_string), 4)]))
  return database.board.upper() + ' ' + b32_string


def Encode(database, bom):
  """Encodes all the given BOM object.

  Args:
    database: A Database object that is used to provide device-specific
        information for encoding.
    bom: A BOM object.

  Returns:
    A HWID object which contains the BOM, the binary string, and the encoded
    string derived from the given BOM object.
  """
  # Convert all encoded fields with None value to the default index 0.
  components_to_update = {}
  for field, index in bom.encoded_fields.iteritems():
    if index is None:
      for comp_cls, comp_name in database.encoded_fields[field][0].iteritems():
        components_to_update[comp_cls] = comp_name
  updated_bom = database.UpdateComponentsOfBOM(bom, components_to_update)

  binary_string = BOMToBinaryString(database, updated_bom)
  encoded_string = BinaryStringToEncodedString(database, binary_string)
  return HWID(database, binary_string, encoded_string, updated_bom)
