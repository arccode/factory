#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of HWID v3 decoder."""

import collections
import factory_common # pylint: disable=W0611

from cros.factory.hwid import common
from cros.factory.hwid.base32 import Base32
from cros.factory.hwid.base8192 import Base8192

_Decoder = {
    common.HWID.ENCODING_SCHEME.base32: Base32,
    common.HWID.ENCODING_SCHEME.base8192: Base8192
}


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
  stripped_binary_string = binary_string[:binary_string.rfind('1')]

  board = database.board
  encoding_pattern = int(stripped_binary_string[0], 2)
  image_id = database.pattern.GetImageIdFromBinaryString(binary_string)

  # Construct the encoded fields dict.
  encoded_fields = collections.defaultdict(int)
  bit_mapping = database.pattern.GetBitMapping(
      image_id=image_id, binary_string_length=len(stripped_binary_string))
  # Hack for Spring EVT
  # TODO(jcliang): Remove this hack when we no longer need it.
  if database.board == 'SPRING' and image_id == 0:
    bit_mapping = database.pattern.GetBitMappingSpringEVT(image_id=image_id)
  for i, (field, bit_offset) in bit_mapping.iteritems():
    if i >= len(stripped_binary_string):
      break
    encoded_fields[field] += int(stripped_binary_string[i], 2) << bit_offset
  for field in (set(database.encoded_fields.keys()) -
                set(encoded_fields.keys())):
    # If a field is not encoded in the binary string but is specified in
    # the pattern of the given database, defaults its value to 0.
    encoded_fields[field] = 0

  # Check that all the encoded field indices are valid.
  for field in encoded_fields:
    if encoded_fields[field] not in database.encoded_fields[field]:
      raise common.HWIDException('Invalid encoded field index: {%r: %r}' %
                                 (field, encoded_fields[field]))

  # Construct the components dict.
  components = collections.defaultdict(list)
  for field, index in encoded_fields.iteritems():
    # pylint: disable=W0212
    attr_dict = database._GetAttributesByIndex(field, index)
    for comp_cls, attr_list in attr_dict.iteritems():
      if attr_list is None:
        components[comp_cls].append(common.ProbedComponentResult(
            None, None, common.MISSING_COMPONENT_ERROR(comp_cls)))
      else:
        for attrs in attr_list:
          components[comp_cls].append(common.ProbedComponentResult(
              attrs['name'], attrs['values'], None))

  return common.BOM(board, encoding_pattern, image_id, components,
                    encoded_fields)


def EncodedStringToBinaryString(database, encoded_string):
  """Decodes the given encoded HWID string to a binary string.

  Args:
    database: A Database object that is used to provide device-specific
        information for decoding.
    encoded_string: An encoded string (with or without dashed).

  Returns:
    A binary string.
  """
  database.VerifyEncodedStringFormat(encoded_string)
  image_id = database.pattern.GetImageIdFromEncodedString(encoded_string)
  encoding_scheme = database.pattern.GetPatternByImageId(
      image_id)['encoding_scheme']
  database.VerifyEncodedString(encoded_string)
  _, hwid_string = encoded_string.split(' ')
  hwid_string = hwid_string.replace('-', '')
  return _Decoder[encoding_scheme].Decode(
      hwid_string)[:-_Decoder[encoding_scheme].CHECKSUM_SIZE].rstrip('0')


def Decode(database, encoded_string, mode=common.HWID.OPERATION_MODE.normal):
  """Decodes the given encoded string to a HWID object.

  Args:
    database: A Database object that is used to provide device-specific
        information for decoding.
    encoded_string: An encoded string.
    mode: The operation mode of the generated HWID object. Valid values are:
        ('normal', 'rma')

  Returns:
    A HWID object which contains the BOM, the binary string, and the encoded
    string derived from the given encoded string.
  """
  binary_string = EncodedStringToBinaryString(database, encoded_string)
  bom = BinaryStringToBOM(database, binary_string)
  return common.HWID(database, binary_string, encoded_string, bom, mode=mode)
