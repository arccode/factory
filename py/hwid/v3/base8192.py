#!/usr/bin/env python2
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of base8192 utilities."""

import argparse

from zlib import crc32

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import common


class Base8192(object):
  """A utility class for encoding binary string to base8192 string, decoding
  base8192 string to binary string, and calculating 8-bit checksum.

  The base32 encoding used here is not identical to the standard as described
  in: http://tools.ietf.org/html/rfc4648.

  The base8 encoding uses '23456789' to represent the 8 possible values of a
  3-bit binary string.
  """
  BASE8_ALPHABET = '23456789'
  BASE8_REVERSED = dict([v, k] for k, v in enumerate(BASE8_ALPHABET))
  BASE8_BIT_WIDTH = 3
  BASE32_ALPHABET = common.HEADER_ALPHABET
  BASE32_REVERSED = dict([v, k] for k, v in enumerate(BASE32_ALPHABET))
  BASE32_BIT_WIDTH = 5
  BASE8192_BIT_WIDTH = 13
  DASH_INSERTION_WIDTH = 3
  CHECKSUM_SIZE = 8
  ENCODED_CHECKSUM_SIZE = 2

  @classmethod
  def GetPaddingLength(cls, orig_length):
    """Returns the minimum padding length for a given length.

    Args:
      orig_length: The length to be calculated.

    Returns:
      A number.
    """
    return (cls.BASE32_BIT_WIDTH - orig_length) % cls.BASE8192_BIT_WIDTH

  @classmethod
  def Encode(cls, binary_string):
    """Converts the given binary string to a base8192-encoded string. Add
    paddings if necessary.

    The last group of the encoded string contains only one base-32 encoded
    alphabet, so that concatenating the 8-bit checksum results in a 13-bit
    string.

    Args:
      binary_string: A binary string.

    Returns:
      A base8192-encoded string.
    """
    assert cls.GetPaddingLength(len(binary_string)) == 0

    result = []
    for index in xrange(0, len(binary_string), cls.BASE8192_BIT_WIDTH):
      i = index
      result.append(cls.BASE32_ALPHABET[
          int(binary_string[i:i + cls.BASE32_BIT_WIDTH], 2)])
      i += 5

      # The last group is only 5-bit long.
      if i == len(binary_string):
        break

      result.append(cls.BASE8_ALPHABET[
          int(binary_string[i:i + cls.BASE8_BIT_WIDTH], 2)])
      i += 3
      result.append(cls.BASE32_ALPHABET[
          int(binary_string[i:i + cls.BASE32_BIT_WIDTH], 2)])

    return ''.join(result)

  @classmethod
  def Decode(cls, base8192_string):
    """Converts the given base8192-encoded string to a binary string.

    Args:
      base8192_string: A base8192-encoded string.

    Returns:
      A binary string.
    """
    assert len(base8192_string) % 3 == 1

    result = []
    for index in xrange(0, len(base8192_string), 3):
      try:
        result.append('{0:05b}'.format(cls.BASE32_REVERSED[
            base8192_string[index].upper()]))
        if index == len(base8192_string) - 1:
          break
        result.append('{0:03b}'.format(cls.BASE8_REVERSED[
            base8192_string[index + 1].upper()]))
        result.append('{0:05b}'.format(cls.BASE32_REVERSED[
            base8192_string[index + 2].upper()]))
      except KeyError:
        raise KeyError(
            'Encoded string should be of format: ([A-Z2-7][2-9][A-Z2-7])+: %r' %
            base8192_string)
    return ''.join(result)

  @classmethod
  def Checksum(cls, string):
    """Calculate a 8-bit checksum for the given string.

    Args:
      string: A string to generate checksum for.

    Returns:
      A string with one base8-encoded alphabet and one base32-encoded alphabet
      representing the 8-bit checksum.
    """
    # Get the last 8 bits
    c = crc32(string) & (2 ** 8 - 1)
    return (cls.BASE8_ALPHABET[c >> cls.BASE32_BIT_WIDTH] +
            cls.BASE32_ALPHABET[c & (2 ** cls.BASE32_BIT_WIDTH - 1)])


if __name__ == '__main__':
  option_parser = argparse.ArgumentParser(
      description='Command-line interface for base8192 encoding.')
  option_parser.add_argument('hwid', metavar='HWID', help='HWID to operate on.')
  option_parser.add_argument('--checksum', '-c', action='store_true',
                             help='Calculate checksum of the given HWID.')
  option_parser.add_argument('--verify-checksum', '-v', action='store_true',
                             help='Verify checksum of the given HWID.')
  options = option_parser.parse_args()
  stripped_hwid = options.hwid.upper().replace('-', '')
  if options.checksum:
    print Base8192.Checksum(stripped_hwid)
  elif options.verify_checksum:
    expected_checksum = Base8192.Checksum(stripped_hwid[:-2])
    given_checksum = stripped_hwid[-2:]
    if expected_checksum == given_checksum:
      print 'Success.'
    else:
      print 'Checksum should be: %r' % expected_checksum
  else:
    option_parser.print_help()
