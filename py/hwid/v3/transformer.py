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
  if bom.encoding_pattern_index not in database.encoding_patterns:
    raise common.HWIDException(
        'Invalid encoding pattern: %r' % bom.encoding_pattern_index)

  if bom.image_id not in database.image_id:
    raise common.HWIDException('Invalid image id: %r' % bom.image_id)

  extra_component_cls = (set(bom.components.keys())
                         - set(database.components.components_dict.keys()))
  if extra_component_cls:
    # It's ok for the BOM to contain more information than what we need.
    logging.warning(
        '%r will not be encoded into the HWID identity.', extra_component_cls)

  # Try to encode every field and fail if some fields are missing or some fields
  # are not listed in the encoding pattern.
  encoded_fields = {}
  for field_name, field_data in database.encoded_fields.iteritems():
    for index, components in field_data.iteritems():
      for comp_cls, comp_names in components.iteritems():
        if (comp_cls not in bom.components or
            sorted(comp_names) != bom.components[comp_cls]):
          break
      else:
        encoded_fields[field_name] = index
        break

  expected_field_names = database.pattern.GetFieldNames(bom.image_id)
  extra_field_names = set(encoded_fields.keys()) - expected_field_names
  if extra_field_names:
    raise common.HWIDException(
        'Extra fields for the pattern: %s' % ', '.join(extra_field_names))

  missing_field_names = expected_field_names - set(encoded_fields.keys())
  if missing_field_names:
    raise common.HWIDException('Encoded fields %s has unknown indices' %
                               ', '.join(sorted(missing_field_names)))

  for field_name, bit_length in database.pattern.GetFieldsBitLength(
      bom.image_id).iteritems():
    if encoded_fields[field_name] >= (2 ** bit_length):
      raise common.HWIDException('Index overflow in field %r' % field_name)

  encoding_scheme = database.pattern.GetEncodingScheme(bom.image_id)

  # TODO(yhong): Don't allocate the header part.
  bit_length = database.pattern.GetTotalBitLength(bom.image_id)
  binary_list = bit_length * [0]

  # Fill in each bit.
  bit_mapping = database.pattern.GetBitMapping(bom.image_id)
  for index, (field, bit_offset) in bit_mapping.iteritems():
    binary_list[index] = (encoded_fields[field] >> bit_offset) & 1

  # Set stop bit.
  binary_list[bit_length - 1] = 1

  # Skip the header.
  binary_list = binary_list[5:]

  components_bitset = ''.join(['%d' % bit for bit in binary_list])

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
  # TODO(yhong): Use identity.components_bitset directly.
  stripped_binary_string = '00000' + identity.components_bitset[:-1]

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
      database.pattern.GetEncodingScheme(image_id), identity.encoded_string)
  if identity != identity2:
    raise common.HWIDException(
        'The hwid %r was generated with wrong encoding scheme.' % identity)

  total_bit_length = database.pattern.GetTotalBitLength(image_id)
  if len(stripped_binary_string) > total_bit_length:
    raise common.HWIDException(
        'Invalid bit string length of %r. Expected length <= %d'
        % (stripped_binary_string, total_bit_length))

  # Construct the encoded fields dict.
  encoded_fields = collections.defaultdict(int)
  for field_name in database.pattern.GetFieldNames(image_id):
    encoded_fields[field_name] = 0
  bit_mapping = database.pattern.GetBitMapping(
      image_id=image_id, binary_string_length=len(stripped_binary_string))
  for i, (field, bit_offset) in bit_mapping.iteritems():
    if i >= len(stripped_binary_string):
      break
    encoded_fields[field] += int(stripped_binary_string[i], 2) << bit_offset

  # Check that all the encoded field indices are valid.
  expected_encoded_fields = database.pattern.GetFieldNames(image_id)
  missing_fields = set(expected_encoded_fields) - set(encoded_fields.keys())
  if missing_fields:
    raise common.HWIDException('Index of the fields are missing: %r' %
                               list(missing_fields))
  for field in encoded_fields:
    if encoded_fields[field] not in database.encoded_fields[field]:
      raise common.HWIDException('Invalid encoded field index: {%r: %r}' %
                                 (field, encoded_fields[field]))

  # Construct the components dict.
  components = {}
  for field, index in encoded_fields.iteritems():
    # pylint: disable=W0212
    attr_dict = database._GetAttributesByIndex(field, index)
    for comp_cls, attr_list in attr_dict.iteritems():
      components[comp_cls] = []
      for attrs in attr_list if attr_list is not None else []:
        components[comp_cls].append(attrs['name'])

  return BOM(identity.encoding_pattern_index, image_id, components)
