#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of HWID v3 decoder."""

import collections
import factory_common # pylint: disable=W0611

from cros.factory.hwid import HWID, BOM, ProbedComponentResult, HWIDException
from cros.factory.hwid.base32 import Base32


def BinaryStringToBOM(database, binary_string):
  """Decodes the given binary string to a BOM object.

  Args:
    database: A Database object that is used to provide device-specific
        information for decoding.
    binary_string: A binary string.

  Returns:
    A BOM object
  """
  database.VerifyBinaryString(binary_string)

  board = database.board
  encoding_pattern = int(binary_string[0], 2)
  image_id = int(binary_string[1:5], 2)

  # Construct the encoded fields dict.
  encoded_fields = collections.defaultdict(int)
  bit_mapping = database.pattern.GetBitMapping()
  for i, (field, bit_offset) in bit_mapping.iteritems():
    encoded_fields[field] += int(binary_string[i], 2) << bit_offset
  for field in (set(database.encoded_fields.keys()) -
                set(encoded_fields.keys())):
    # If a field is not encoded in the binary string but is specified in
    # the pattern of the given database, defaults its value to 0.
    encoded_fields[field] = 0

  # Check that all the encoded field indices are valid.
  for field in encoded_fields:
    if encoded_fields[field] not in database.encoded_fields[field]:
      raise HWIDException('Invalid encoded field index: {%r: %r}' %
                          (field, encoded_fields[field]))

  # Construct the components dict.
  components = collections.defaultdict(list)
  for field, index in encoded_fields.iteritems():
    # pylint: disable=W0212
    attr_dict = database._GetAttributesByIndex(field, index)
    for comp_cls, attr_list in attr_dict.iteritems():
      if attr_list is None:
        components[comp_cls].append(ProbedComponentResult(None, None, None))
      else:
        for attrs in attr_list:
          components[comp_cls].append(
              ProbedComponentResult(attrs['name'], attrs['value'], None))

  return BOM(board, encoding_pattern, image_id, components, encoded_fields)


def EncodedStringToBinaryString(database, encoded_string):
  """Decodes the given encoded HWID string to a binary string.

  Args:
    database: A Database object that is used to provide device-specific
        information for decoding.
    encoded_string: An encoded string (with or without dashed).

  Returns:
    A binary string.
  """
  database.VerifyEncodedString(encoded_string)
  # TODO(jcliang): Change back in R27.
  #_, hwid_string = encoded_string.split(' ')
  _, hwid_string, _ = encoded_string.split(' ')
  hwid_string = hwid_string.replace('-', '')
  # Remove the 10-bit checksum at tail
  hwid_string = hwid_string[0:-2]
  return Base32.Decode(hwid_string)


def Decode(database, encoded_string):
  """Decodes the given encoded string to a HWID object.

  Args:
    database: A Database object that is used to provide device-specific
        information for decoding.
    encoded_string: An encoded string.

  Returns:
    A HWID object which contains the BOM, the binary string, and the encoded
    string derived from the given encoded string.
  """
  binary_string = EncodedStringToBinaryString(database, encoded_string)
  bom = BinaryStringToBOM(database, binary_string)
  return HWID(database, binary_string, encoded_string, bom)
