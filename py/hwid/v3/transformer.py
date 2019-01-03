# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of HWID v3 encoder and decoder."""

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.bom import BOM
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.identity import Identity


def BOMToIdentity(database, bom, encoded_configless=None):
  """Encodes the given BOM object to a binary string.

  Args:
    database: A Database object that is used to provide device-specific
        information for encoding.
    bom: A BOM object to be decoded.
    encoded_configless: None or a string of encoded configless fields.

  Returns:
    An Identity object.
  """
  if not database.can_encode:
    raise common.HWIDException(
        'The given HWID database is a legacy one and not works for encoding.')

  if bom.encoding_pattern_index not in database.encoding_patterns:
    raise common.HWIDException(
        'Invalid encoding pattern: %r' % bom.encoding_pattern_index)

  if bom.image_id not in database.image_ids:
    raise common.HWIDException('Invalid image id: %r' % bom.image_id)

  # Try to encode every field and fail if some fields are missing or
  # the bit length of a field recorded in the pattern is not enough.
  encoded_fields = {}
  for field_name, bit_length in database.GetEncodedFieldsBitLength(
      bom.image_id).iteritems():
    for index, components in database.GetEncodedField(field_name).iteritems():
      if all(comp_names == bom.components[comp_cls]
             for comp_cls, comp_names in components.iteritems()):
        encoded_fields[field_name] = index
        break

    else:
      raise common.HWIDException(
          'Encoded field %s has unknown indices' % field_name)

    if encoded_fields[field_name] >= (2 ** bit_length):
      raise common.HWIDException('Index overflow in field %r' % field_name)

  # Fill in each bit.
  components_bitset = ''
  for (field, bit_offset) in database.GetBitMapping(bom.image_id):
    components_bitset += '01'[(encoded_fields[field] >> bit_offset) & 1]

  # Set stop bit.
  components_bitset += '1'

  return Identity.GenerateFromBinaryString(
      database.GetEncodingScheme(bom.image_id), database.project,
      bom.encoding_pattern_index, bom.image_id, components_bitset,
      encoded_configless)


def IdentityToBOM(database, identity):
  """Decodes the given HWID Identity to a BOM object.

  Args:
    database: A Database object that is used to provide device-specific
        information for decoding.
    identity: The HWID Identity.

  Returns:
    A BOM object.
  """
  if identity.project != database.project:
    raise common.HWIDException('Invalid project: %r' % identity.project)

  if identity.encoding_pattern_index not in database.encoding_patterns:
    raise common.HWIDException(
        'Invalid encoding pattern index: %r' % identity.encoding_pattern_index)

  image_id = identity.image_id

  # Re-generate the identity by the encoding scheme specified in the HWID
  # database to verify whether the given identity is generated with the correct
  # encoding scheme.
  identity2 = Identity.GenerateFromEncodedString(
      database.GetEncodingScheme(image_id), identity.encoded_string)
  if identity != identity2:
    raise common.HWIDException(
        'The hwid %r was generated with wrong encoding scheme.' % identity)

  bit_length = len(identity.components_bitset) - 1
  total_bit_length = database.GetTotalBitLength(image_id)
  if bit_length > total_bit_length:
    raise common.HWIDException(
        'Invalid bit string length of %r. Expected length <= %d'
        % (identity.components_bitset[:-1], total_bit_length))

  # Construct the encoded fields dict.
  encoded_fields = {field_name: 0 for field_name
                    in database.GetEncodedFieldsBitLength(image_id)}
  bit_mapping = database.GetBitMapping(image_id=image_id,
                                       max_bit_length=bit_length)
  for i, (field, bit_offset) in enumerate(bit_mapping):
    encoded_fields[field] += int(identity.components_bitset[i], 2) << bit_offset

  # Construct the components dict.
  components = {comp_cls: [] for comp_cls in database.GetComponentClasses()}
  for field, index in encoded_fields.iteritems():
    database_encoded_field = database.GetEncodedField(field)
    if index not in database_encoded_field:
      raise common.HWIDException('Invalid encoded field index: {%r: %r}' %
                                 (field, index))
    components.update(database_encoded_field[index])

  return BOM(identity.encoding_pattern_index, image_id, components)
