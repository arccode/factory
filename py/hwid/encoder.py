#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of HWID v3 encoder."""

import factory_common # pylint: disable=W0611

from cros.factory.hwid import common
from cros.factory.hwid.base32 import Base32
from cros.factory.hwid.base8192 import Base8192

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


def Encode(database, bom, skip_check=False, rma_mode=False):
  """Encodes all the given BOM object.

  Args:
    database: A Database object that is used to provide device-specific
        information for encoding.
    bom: A BOM object.
    skip_check: A bool value to skip the verification when constructing the HWID
        object. Needed when creating a HWID skelton to be further processed.
    rma_mode: If set to True, deprecated components will be allowed.

  Returns:
    A HWID object which contains the BOM, the binary string, and the encoded
    string derived from the given BOM object.
  """
  # Convert all encoded fields with None value to the default index 0.
  components_to_update = {}
  for field, index in bom.encoded_fields.iteritems():
    if index is None:
      for comp_cls, comp_name in database.encoded_fields[field][0].iteritems():
        # Check every component classes that this encoded field consists of.
        for probed_comp in bom.components[comp_cls]:
          if probed_comp.component_name is not None:
            continue
          if comp_cls not in database.components.probeable:
            # Only convert unprobeable components.
            components_to_update[comp_cls] = comp_name
          else:
            raise common.HWIDException(probed_comp.error)
  updated_bom = database.UpdateComponentsOfBOM(bom, components_to_update)

  for field, index in updated_bom.encoded_fields.iteritems():
    if index is None:
      err_msg = ('Unable to determine index for encoded field %r. Probed '
          'components are:\n') % field
      for comp_cls in database.encoded_fields[field][0].iterkeys():
        for probed_comp in bom.components[comp_cls]:
          err_msg += '  %r: %r\n' % (comp_cls, probed_comp.component_name)
      raise common.HWIDException(err_msg)

  binary_string = BOMToBinaryString(database, updated_bom)
  encoded_string = BinaryStringToEncodedString(database, binary_string)
  hwid = common.HWID(database, binary_string, encoded_string, updated_bom,
                     skip_check=skip_check)
  hwid.VerifyComponentStatus(rma_mode)
  return hwid
