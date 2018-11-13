# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Identity class for the HWID v3 framework.

The identity for a Chromebook project is called HWID encoded strings.  The
format of a HWID encoded string is

```
<project_name> <encoded_body><encoded_checksum>
```

For human readibility, it's allowed to insert some dash to seperate
`<encoded_body><encoded_checksum>` into multiple parts, but the dash symbols
will be ignored by the program.

The `project_name` is a non-empty string of upper case alphanumeric.
The `encoded_checksum` is the checksum of `<project_name> <encoded_body>`
Given the encoding scheme, the `<encoded_body>` can be decoded into a binary
string which length is greater than 5.  The binary string contains 3 parts:

  1. The 1st (left most) digit is the `encoding_pattern_index`,
     which value can be either 0 or 1.
  2. The 2ed to the 5th digits is a 4-bit big-endian integer of the `image_id`.
  3. The reset of the digits is called `components_bitset`.  A
     `components_bitset`  is an arbitrary binary string which ends with '1'.
     A `components_bitset` can be decoded into a set of installed components
     according to the HWID `Database`.  But the actual format of this part is
     beyond `Identiy`'s business.

For example, if the binary string is `0 0010 0111010101011`, then we have:
  1. `encoding_pattern_index` = 0
  2. `image_id` = 2
  3. `components_bitset` = '0111010101011'

This package implements the encoding/decoding logic between the 3 parts of the
binary string and the encoded string.
"""

import re

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import base32
from cros.factory.hwid.v3 import base8192
from cros.factory.hwid.v3 import common


_Converters = {
    common.ENCODING_SCHEME.base32: base32.Base32,
    common.ENCODING_SCHEME.base8192: base8192.Base8192
}


_HEADER_FORMAT_STR = '{0:01b}{1:0%db}' % common.IMAGE_ID_BIT_LENGTH


def _VerifyPart(condition, part, value):
  if not condition(value):
    raise common.HWIDException('The given %s %r is invalid.' % (part, value))


def _VerifyProjectPart(project):
  _VerifyPart(lambda val: re.match(r'^[A-Z0-9]+$', val), 'project', project)


def _VerifyEncodingSchemePart(encoding_scheme):
  _VerifyPart(lambda val: val in _Converters,
              'encoding_scheme', encoding_scheme)


def GetImageIdFromBinaryString(binary_string):
  """Obtains the image id from a HWID binary string without actually decode it.

  This function will not verify whether the given HWID binary string is valid
  or not.

  Args:
    binary_string: The HWID binary string to parse.

  Returns:
    An integer of the image id.
  """
  _VerifyPart(lambda val: (len(val) > common.HEADER_BIT_LENGTH and
                           not set(val) - set('01')),
              'binary_string', binary_string)

  return int(binary_string[1:common.HEADER_BIT_LENGTH], 2)


def GetImageIdFromEncodedString(encoded_string):
  """Obtains the image id from a HWID encoded string without actually decode it.

  This function will not verify whether the given HWID encoded string is valid
  or not.

  Args:
    encoded_string: The HWID encoded string to parse.

  Returns:
    An integer of the image id.
  """
  project, _, encoded_body_and_checksum = encoded_string.partition(' ')
  _VerifyProjectPart(project)
  _VerifyPart(lambda val: len(val) > 2,
              'encoded_body+checksum', encoded_body_and_checksum)

  return common.HEADER_ALPHABET.index(encoded_body_and_checksum[0]) & 0x0f


class Identity(object):
  """A class to hold the identity of a Chromebook project.

  Properties:
    project: A string of the name of the Chromebook project.
    encoded_string: A string of the HWID encoded string.
    encoding_pattern_index: A integer of the encode pattern index.
    image_id: A integer of the image id.
    components_bitset: A binary string ends with '1'.
  """
  def __init__(self, project, encoded_string, encoding_pattern_index, image_id,
               components_bitset):
    """Constructor.

    This constructor shouldn't be called by the user directly.  The user should
    get the instance of Identity by calling either
    `Identity.GenerateFromBinaryString` or `Identity.GenerateFromEncodedString`.
    """
    self.project = project
    self.encoded_string = encoded_string
    self.encoding_pattern_index = encoding_pattern_index
    self.image_id = image_id
    self.components_bitset = components_bitset

    self.binary_string = _HEADER_FORMAT_STR.format(
        encoding_pattern_index, image_id) + components_bitset

  def __eq__(self, rhs):
    return isinstance(rhs, Identity) and self.__dict__ == rhs.__dict__

  def __ne__(self, rhs):
    return not self.__eq__(rhs)

  def __repr__(self):
    return 'Identity(%r)' % self.__dict__

  @staticmethod
  def GenerateFromBinaryString(encoding_scheme, project,
                               encoding_pattern_index, image_id,
                               components_bitset):
    """Generates an instance of Identity from the given 3 parts of the binary
    string.

    This function also verifies whether the given HWID binary string matches
    the format or not.

    Args:
      encoding_scheme: The encoding scheme used when this HWID was generated.
      project: A string of the Chromebook project name.
      encoding_pattern_index: An integer of the encode pattern index.
      image_id: An integer of the image id.
      compoents_bitset: A binary string ends with '1'.

    Returns:
      An instance of Identity.
    """
    _VerifyEncodingSchemePart(encoding_scheme)
    converter = _Converters[encoding_scheme]

    _VerifyProjectPart(project)
    _VerifyPart(lambda val: val in [0, 1],
                'encoding_pattern_index', encoding_pattern_index)
    _VerifyPart(lambda val: val in range(1 << common.IMAGE_ID_BIT_LENGTH),
                'image_id', image_id)
    _VerifyPart(lambda val: val and not set(val) - set('01') and val[-1] == '1',
                'components_bitset', components_bitset)

    # Generate the binary string with paddings.
    binary_string = _HEADER_FORMAT_STR.format(
        encoding_pattern_index, image_id) + components_bitset
    binary_string += '0' * converter.GetPaddingLength(len(binary_string))

    encoded_body = converter.Encode(binary_string)
    checksum = converter.Checksum(project + ' ' + encoded_body)
    encoded_body_with_checksum = encoded_body + checksum
    encoded_string = project + ' ' + '-'.join(
        [encoded_body_with_checksum[idx:idx + converter.DASH_INSERTION_WIDTH]
         for idx in xrange(0, len(encoded_body_with_checksum),
                           converter.DASH_INSERTION_WIDTH)])

    return Identity(project, encoded_string, encoding_pattern_index, image_id,
                    components_bitset)

  @staticmethod
  def GenerateFromEncodedString(encoding_scheme, encoded_string):
    """Generates an instance of Identity from the given HWID encoded string.

    This function also verifies whether the given HWID encoded string matches
    the format or not.

    Args:
      encoding_scheme: The encoding scheme used when this HWID was generated.
      encoded_string: A string of HWID encoded string.

    Returns:
      An instance of Identity.
    """
    _VerifyEncodingSchemePart(encoding_scheme)
    converter = _Converters[encoding_scheme]

    project, _, encoded_body_and_checksum = encoded_string.partition(' ')
    _VerifyProjectPart(project)
    encoded_body_and_checksum = encoded_body_and_checksum.replace('-', '')
    _VerifyPart(lambda val: len(val) > converter.ENCODED_CHECKSUM_SIZE,
                'encoded_body+checksum', encoded_body_and_checksum)
    encoded_body = encoded_body_and_checksum[:-converter.ENCODED_CHECKSUM_SIZE]
    checksum = encoded_body_and_checksum[-converter.ENCODED_CHECKSUM_SIZE:]

    _VerifyPart(
        lambda val: val == converter.Checksum(project + ' ' + encoded_body),
        'checksum', checksum)

    # Decode and remove the padding.
    binary_string = converter.Decode(encoded_body).rstrip('0')

    _VerifyPart(lambda val: len(val) > common.HEADER_BIT_LENGTH,
                'binary_string', binary_string)

    encoding_pattern_index = int(binary_string[0], 2)
    image_id = int(binary_string[1:common.HEADER_BIT_LENGTH], 2)
    components_bitset = binary_string[common.HEADER_BIT_LENGTH:]

    return Identity(project, encoded_string, encoding_pattern_index, image_id,
                    components_bitset)
