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


def VerifyBinaryString(database, binary_string):
  """Verifies the binary string.

  Args:
    binary_string: The binary string to verify.

  Raises:
    HWIDException if verification fails.
  """
  if set(binary_string) - set('01'):
    raise common.HWIDException('Invalid binary string: %r' % binary_string)

  if '1' not in binary_string:
    raise common.HWIDException('Binary string %r does not have stop bit set',
                               binary_string)
  # Truncate trailing 0s.
  string_without_paddings = binary_string[:binary_string.rfind('1') + 1]

  image_id = database.pattern.GetImageIdFromBinaryString(binary_string)
  total_bit_length = database.pattern.GetTotalBitLength(image_id)
  if len(string_without_paddings) > total_bit_length:
    raise common.HWIDException(
        'Invalid bit string length of %r. Expected length <= %d, got length %d'
        % (binary_string, total_bit_length, len(string_without_paddings)))


def VerifyEncodedStringFormat(encoded_string):
  """Verifies that the format of the given encoded string.

  Checks that the string matches either base32 or base8192 format.

  Args:
    encoded_string: The encoded string to verify.

  Raises:
    HWIDException if verification fails.
  """
  if not any(hwid_format.match(encoded_string) for hwid_format in
             common.HWID_FORMAT.itervalues()):
    raise common.HWIDException(
        'HWID string %r is neither base32 nor base8192 encoded' %
        encoded_string)


def VerifyEncodedString(database, encoded_string):
  """Verifies the given encoded string.

  Args:
    encoded_string: The encoded string to verify.

  Raises:
    HWIDException if verification fails.
  """
  try:
    image_id = database.pattern.GetImageIdFromEncodedString(encoded_string)
    encoding_scheme = database.pattern.GetPatternByImageId(
        image_id)['encoding_scheme']
    project, bom_checksum = common.HWID_FORMAT[encoding_scheme].findall(
        encoded_string)[0]
  except IndexError:
    raise common.HWIDException(
        'Invalid HWID string format: %r' % encoded_string)
  if len(bom_checksum) < 2:
    raise common.HWIDException(
        'Length of encoded string %r is less than 2 characters' %
        bom_checksum)
  if project != database.project.upper():
    raise common.HWIDException('Invalid project name: %r' % project)
  # Verify the checksum
  stripped = encoded_string.replace('-', '')
  hwid = stripped[:-2]
  checksum = stripped[-2:]
  if encoding_scheme == common.HWID.ENCODING_SCHEME.base32:
    expected_checksum = Base32.Checksum(hwid)
  elif encoding_scheme == common.HWID.ENCODING_SCHEME.base8192:
    expected_checksum = Base8192.Checksum(hwid)
  if checksum != expected_checksum:
    raise common.HWIDException('Checksum of %r mismatch (expected %r)' % (
        encoded_string, expected_checksum))

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


def BOMToBinaryString(database, bom):
  """Encodes the given BOM object to a binary string.

  Args:
    database: A Database object that is used to provide device-specific
        information for encoding.

  Returns:
    A binary string.
  """
  VerifyBOM(database, bom)
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
    An encoded string with project name, base32-encoded HWID, and checksum.
  """
  VerifyBinaryString(database, binary_string)
  image_id = database.pattern.GetImageIdFromBinaryString(binary_string)
  encoding_scheme = database.pattern.GetPatternByImageId(
      image_id)['encoding_scheme']
  encoder = _Encoder[encoding_scheme]
  encoded_string = encoder.Encode(binary_string)
  # Make project name part of the checksum.
  encoded_string += encoder.Checksum(
      database.project.upper() + ' ' + encoded_string)
  # Insert dashes to increase readibility.
  encoded_string = ('-'.join(
      [encoded_string[i:i + encoder.DASH_INSERTION_WIDTH]
       for i in xrange(0, len(encoded_string), encoder.DASH_INSERTION_WIDTH)]))
  return database.project.upper() + ' ' + encoded_string


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


def BinaryStringToBOM(database, binary_string):
  """Decodes the given binary string to a BOM object.

  Args:
    database: A Database object that is used to provide device-specific
        information for decoding.
    binary_string: A binary string.

  Returns:
    A BOM object
  """
  VerifyBinaryString(database, binary_string)
  stripped_binary_string = binary_string[:binary_string.rfind('1')]

  project = database.project
  encoding_pattern = int(stripped_binary_string[0], 2)
  image_id = database.pattern.GetImageIdFromBinaryString(binary_string)

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

  return BOM(project, encoding_pattern, image_id, components, encoded_fields)


def EncodedStringToBinaryString(database, encoded_string):
  """Decodes the given encoded HWID string to a binary string.

  Args:
    database: A Database object that is used to provide device-specific
        information for decoding.
    encoded_string: An encoded string (with or without dashed).

  Returns:
    A binary string.
  """
  VerifyEncodedStringFormat(encoded_string)
  image_id = database.pattern.GetImageIdFromEncodedString(encoded_string)
  encoding_scheme = database.pattern.GetPatternByImageId(
      image_id)['encoding_scheme']
  VerifyEncodedString(database, encoded_string)
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
  identity = Identity(database.project, binary_string, encoded_string)
  bom = BinaryStringToBOM(database, binary_string)
  return common.HWID(database, bom=bom, identity=identity, mode=mode)
