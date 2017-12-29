# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of HWID v3 encoder and decoder."""

import collections
import logging

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.bom import BOM
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.identity import Identity


def BOMToIdentity(database, bom):
  """Encodes the given BOM object to a binary string.

  Args:
    database: A Database object that is used to provide device-specific
        information for encoding.
    bom: A BOM object to be decoded.

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

  extra_component_cls = (
      set(bom.components.keys()) - set(database.component_classes))
  if extra_component_cls:
    # It's ok for the BOM to contain more information than what we need.
    logging.warning(
        '%r will not be encoded into the HWID identity.', extra_component_cls)

  # Try to encode every field and fail if some fields are missing or some fields
  # are not listed in the encoding pattern.
  encoded_fields = {}
  for field_name in database.encoded_fields:
    for index, components in database.GetEncodedField(field_name).iteritems():
      for comp_cls, comp_names in components.iteritems():
        if (comp_cls not in bom.components or
            sorted(comp_names) != bom.components[comp_cls]):
          break
      else:
        encoded_fields[field_name] = index
        break

  expected_field_names = set(
      database.GetEncodedFieldsBitLength(bom.image_id).keys())
  extra_field_names = set(encoded_fields.keys()) - expected_field_names
  if extra_field_names:
    raise common.HWIDException(
        'Extra fields for the pattern: %s' % ', '.join(extra_field_names))

  missing_field_names = expected_field_names - set(encoded_fields.keys())
  if missing_field_names:
    raise common.HWIDException('Encoded fields %s has unknown indices' %
                               ', '.join(sorted(missing_field_names)))

  for field_name, bit_length in database.GetEncodedFieldsBitLength(
      bom.image_id).iteritems():
    if encoded_fields[field_name] >= (2 ** bit_length):
      raise common.HWIDException('Index overflow in field %r' % field_name)

  encoding_scheme = database.GetEncodingScheme(bom.image_id)

  # Fill in each bit.
  components_bitset = ''
  for (field, bit_offset) in database.GetBitMapping(bom.image_id):
    components_bitset += '01'[(encoded_fields[field] >> bit_offset) & 1]

  # Set stop bit.
  components_bitset += '1'

  return Identity.GenerateFromBinaryString(
      encoding_scheme, database.project, bom.encoding_pattern_index,
      bom.image_id, components_bitset)


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
  encoded_fields = collections.defaultdict(int)
  for field_name in database.GetEncodedFieldsBitLength(image_id).keys():
    encoded_fields[field_name] = 0
  bit_mapping = database.GetBitMapping(image_id=image_id,
                                       max_bit_length=bit_length)
  for i, (field, bit_offset) in enumerate(bit_mapping):
    encoded_fields[field] += int(identity.components_bitset[i], 2) << bit_offset

  # Check that all the encoded field indices are valid.
  expected_encoded_fields = database.GetEncodedFieldsBitLength(image_id).keys()
  missing_fields = set(expected_encoded_fields) - set(encoded_fields.keys())
  if missing_fields:
    raise common.HWIDException('Index of the fields are missing: %r' %
                               list(missing_fields))

  # Construct the components dict.
  components = {}
  for field, index in encoded_fields.iteritems():
    encoded_field = database.GetEncodedField(field)
    if index not in encoded_field:
      raise common.HWIDException('Invalid encoded field index: {%r: %r}' %
                                 (field, encoded_fields[field]))
    components.update(encoded_field[index])

  return BOM(identity.encoding_pattern_index, image_id, components)
