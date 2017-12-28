# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of HWID v3 encoder and decoder."""

import collections
import pprint

import factory_common  # pylint: disable=W0611

from cros.factory.hwid.v3.bom import BOM
from cros.factory.hwid.v3.bom import ProbedComponentResult
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.base32 import Base32
from cros.factory.hwid.v3.base8192 import Base8192
from cros.factory.hwid.v3 import identity as identity_utils
from cros.factory.hwid.v3.identity import Identity
from cros.factory.utils import type_utils


_Encoder = {
    common.HWID.ENCODING_SCHEME.base32: Base32,
    common.HWID.ENCODING_SCHEME.base8192: Base8192
}

_Decoder = {
    common.HWID.ENCODING_SCHEME.base32: Base32,
    common.HWID.ENCODING_SCHEME.base8192: Base8192
}


def VerifyBOM(database, bom, probeable_only=False):
  """Verifies the data contained in the given BOM object matches the settings
  and definitions in the database.

  Because the components for each image ID might be different, for example a
  component might be removed in later build. We only verify the components in
  the target image ID, not all components listed in the database.

  When the BOM is decoded by HWID string, it would contain the information of
  every component recorded in the pattern. But if the BOM object is created by
  the probed result, it does not contain the unprobeable component before
  evaluating the rule. We should verify the probeable components only.

  Args:
    bom: The BOM object to verify.
    probeable_only: True to verify the probeable component only.

  Raises:
    HWIDException if verification fails.
  """
  if bom.project != database.project:
    raise common.HWIDException('Invalid project name. Expected %r, got %r' %
                               (database.project, bom.project))

  if bom.encoding_pattern_index not in database.encoding_patterns:
    raise common.HWIDException('Invalid encoding pattern: %r' %
                               bom.encoding_pattern_index)
  if bom.image_id not in database.image_id:
    raise common.HWIDException('Invalid image id: %r' % bom.image_id)

  # All the classes encoded in the pattern should exist in BOM.
  # Ignore unprobeable components if probeable_only is True.
  missing_comp = []
  expected_encoded_fields = database.pattern.GetFieldNames(bom.image_id)
  for comp_cls in database.GetActiveComponents(bom.image_id):
    if (comp_cls not in bom.components and
        (comp_cls in database.components.probeable or not probeable_only)):
      missing_comp.append(comp_cls)
  if missing_comp:
    raise common.HWIDException('Missing component classes: %r',
                               ', '.join(sorted(missing_comp)))

  bom_encoded_fields = type_utils.MakeSet(bom.encoded_fields.keys())
  db_encoded_fields = type_utils.MakeSet(expected_encoded_fields)
  # Every encoded field defined in the database must present in BOM.
  if db_encoded_fields - bom_encoded_fields:
    raise common.HWIDException('Missing encoded fields in BOM: %r',
                               ', '.join(sorted(db_encoded_fields -
                                                bom_encoded_fields)))

  # All the probeable component values in the BOM should exist in the
  # database.
  unknown_values = []
  for comp_cls, probed_values in bom.components.iteritems():
    if comp_cls not in database.components.probeable:
      continue
    for element in probed_values:
      probed_values = element.probed_values
      if probed_values is None:
        continue
      found_comps = database.components.MatchComponentsFromValues(
          comp_cls, probed_values, include_default=True)
      if not found_comps:
        unknown_values.append('%s:%s' % (comp_cls, pprint.pformat(
            probed_values, indent=0, width=1024)))
  if unknown_values:
    raise common.HWIDException('Unknown component values: %r' %
                               ', '.join(sorted(unknown_values)))

  # All the encoded index should exist in the database.
  invalid_fields = []
  for field_name in expected_encoded_fields:
    # Ignore the field containing unprobeable component.
    if probeable_only and not all(
        [comp_cls in database.components.probeable
         for comp_cls in database.encoded_fields[field_name][0].keys()]):
      continue
    index = bom.encoded_fields[field_name]
    if index is None or index not in database.encoded_fields[field_name]:
      invalid_fields.append(field_name)

  if invalid_fields:
    raise common.HWIDException('Encoded fields %r have unknown indices' %
                               ', '.join(sorted(invalid_fields)))


def BOMToIdentity(database, bom):
  """Encodes the given BOM object to a binary string.

  Args:
    database: A Database object that is used to provide device-specific
        information for encoding.

  Returns:
    A binary string.
  """
  VerifyBOM(database, bom)

  encoding_scheme = database.pattern.GetEncodingScheme(bom.image_id)

  # TODO(yhong): Don't allocate the header part.
  bit_length = database.pattern.GetTotalBitLength(bom.image_id)
  binary_list = bit_length * [0]

  # Fill in each bit.
  bit_mapping = database.pattern.GetBitMapping(bom.image_id)
  for index, (field, bit_offset) in bit_mapping.iteritems():
    binary_list[index] = (bom.encoded_fields[field] >> bit_offset) & 1

  # Set stop bit.
  binary_list[bit_length - 1] = 1

  # Skip the header.
  binary_list = binary_list[5:]

  components_bitset = ''.join(['%d' % bit for bit in binary_list])

  return Identity.GenerateFromBinaryString(
      encoding_scheme, database.project, bom.encoding_pattern_index,
      bom.image_id, components_bitset)


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
  hwid = common.HWID(database, bom=bom, mode=mode, skip_check=skip_check)
  return hwid


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

  project = database.project
  encode_pattern_index = identity.encode_pattern_index
  image_id = identity.image_id

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
  components = collections.defaultdict(list)
  for field, index in encoded_fields.iteritems():
    # pylint: disable=W0212
    attr_dict = database._GetAttributesByIndex(field, index)
    for comp_cls, attr_list in attr_dict.iteritems():
      if attr_list is None:
        components[comp_cls].append(ProbedComponentResult(
            None, None, common.MISSING_COMPONENT_ERROR(comp_cls)))
      else:
        for attrs in attr_list:
          components[comp_cls].append(ProbedComponentResult(
              attrs['name'], attrs['values'], None))

  return BOM(project, encode_pattern_index, image_id, components,
             encoded_fields)


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
  image_id = identity_utils.GetImageIdFromEncodedString(encoded_string)
  encoding_scheme = database.pattern.GetEncodingScheme(image_id)
  identity = Identity.GenerateFromEncodedString(encoding_scheme, encoded_string)
  bom = IdentityToBOM(database, identity)
  return common.HWID(database, bom=bom, identity=identity, mode=mode)
