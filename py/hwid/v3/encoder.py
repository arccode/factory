#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of HWID v3 encoder."""

import factory_common  # pylint: disable=W0611

from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.base32 import Base32
from cros.factory.hwid.v3.base8192 import Base8192

_Encoder = {
    common.HWID.ENCODING_SCHEME.base32: Base32,
    common.HWID.ENCODING_SCHEME.base8192: Base8192
}


def BOMToBinaryString(database, bom):
  """Encodes the given BOM object to a binary string.

  Args:
    database: A Database object that is used to provide device-specific
        information for encoding.

  Returns:
    A binary string.
  """
  database.VerifyBOM(bom)
  bit_length = database.pattern.GetTotalBitLength(bom.image_id)
  binary_list = bit_length * [0]

  # Fill in header.
  binary_list[0] = bom.encoding_pattern_index
  for i in xrange(1, 5):
    binary_list[i] = (bom.image_id >> (4 - i)) & 1
  # Fill in each bit.
  bit_mapping = database.pattern.GetBitMapping(bom.image_id)
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
  image_id = database.pattern.GetImageIdFromBinaryString(binary_string)
  encoding_scheme = database.pattern.GetPatternByImageId(
      image_id)['encoding_scheme']
  encoder = _Encoder[encoding_scheme]
  encoded_string = encoder.Encode(binary_string)
  # Make board name part of the checksum.
  encoded_string += encoder.Checksum(
      database.board.upper() + ' ' + encoded_string)
  # Insert dashes to increase readibility.
  encoded_string = ('-'.join(
      [encoded_string[i:i + encoder.DASH_INSERTION_WIDTH]
       for i in xrange(0, len(encoded_string), encoder.DASH_INSERTION_WIDTH)]))
  return database.board.upper() + ' ' + encoded_string


def Encode(database, bom, mode=common.HWID.OPERATION_MODE.normal,
           skip_check=False):
  """Encodes all the given BOM object.

  Args:
    database: A Database object that is used to provide device-specific
        information for encoding.
    bom: A BOM object.
    mode: The operation mode of the generated HWID object. Valid values are:
        ('normal', 'rma')
    skip_check: Whether to skip HWID verification checks. Set to True when
        generating HWID skeleton objects for further processing.

  Returns:
    A HWID object which contains the BOM, the binary string, and the encoded
    string derived from the given BOM object.
  """
  hwid = common.HWID(database, bom, mode=mode, skip_check=skip_check)
  return hwid
