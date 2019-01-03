#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import identity
from cros.factory.hwid.v3.identity import Identity


_BASE32 = common.ENCODING_SCHEME.base32
_BASE8192 = common.ENCODING_SCHEME.base8192


class GetImageIdFromBinaryString(unittest.TestCase):
  def testNormal(self):
    self.assertEqual(0, identity.GetImageIdFromBinaryString('000001'))
    self.assertEqual(1, identity.GetImageIdFromBinaryString('000011'))
    self.assertEqual(2, identity.GetImageIdFromBinaryString('000101'))

  def testStringTooShort(self):
    self.assertRaises(
        common.HWIDException, identity.GetImageIdFromBinaryString, '')

  def testBadChar(self):
    self.assertRaises(
        common.HWIDException, identity.GetImageIdFromBinaryString, '002112')


class GetImageIdFromEncodedStringTest(unittest.TestCase):
  def testNormal(self):
    self.assertEqual(0, identity.GetImageIdFromEncodedString('PROJ ACK'))
    self.assertEqual(1, identity.GetImageIdFromEncodedString('PROJ BCK'))
    self.assertEqual(2, identity.GetImageIdFromEncodedString('PROJ CCK'))
    self.assertEqual(
        2, identity.GetImageIdFromEncodedString('PROJ 0-8-40-0 CCK'))

  def testStringTooShort(self):
    self.assertRaises(
        common.HWIDException, identity.GetImageIdFromEncodedString, '')
    self.assertRaises(
        common.HWIDException, identity.GetImageIdFromEncodedString, 'PROJ')


class _Sample(dict):
  _ARGS = ['encoded_string', 'project', 'encoding_pattern_index', 'image_id',
           'components_bitset', 'encoding_scheme', 'encoded_configless']

  def __init__(self, *args):
    super(_Sample, self).__init__({attr_name: args[idx]
                                   for idx, attr_name in enumerate(self._ARGS)})


_SAMPLES = [
    _Sample('PROJ ERVY-5O', 'PROJ', 0, 4, '100011010111', _BASE32, None),
    _Sample('PROJ GR3L-QK4', 'PROJ', 0, 6, '1000111011010111', _BASE32, None),
    _Sample('PROJ E6N-O42', 'PROJ', 0, 4, '100011010111', _BASE8192, None),
    _Sample('PROJ G6O-29A-A8M', 'PROJ', 0, 6, '1000111011010111', _BASE8192,
            None),
    _Sample('PROJ 0-8-3A-80 G6O-29A-A5F', 'PROJ', 0, 6, '1000111011010111',
            _BASE8192,
            '0-8-3A-80')]

class _IdentityGeneratorTestBase(object):
  NEEDED_ARGS = []

  def testSuccess(self):
    for sample in _SAMPLES:
      self.CheckMatch(sample)

  def doTestInvalid(self, reference_sample, **kwargs):
    sample = {key: reference_sample[key]
              for key in reference_sample if key in self.NEEDED_ARGS}
    sample.update(kwargs)
    self.assertRaises(common.HWIDException, self.GenerateIdentity, **sample)

  def CheckMatch(self, sample):
    reference_identity = Identity(
        **{key: sample[key] for key in sample if key != 'encoding_scheme'})

    generated_identity = self.GenerateIdentity(
        **{key: sample[key] for key in sample if key in self.NEEDED_ARGS})

    self.assertEqual(reference_identity, generated_identity)

  def GenerateIdentity(self, **kwargs):
    raise NotImplementedError


class IdentityGenerateFromBinaryStringTest(unittest.TestCase,
                                           _IdentityGeneratorTestBase):
  NEEDED_ARGS = ['encoding_scheme', 'project', 'encoding_pattern_index',
                 'image_id', 'components_bitset', 'encoded_configless']

  def GenerateIdentity(self, **kwargs):
    return Identity.GenerateFromBinaryString(**kwargs)

  def testBadEncodingScheme(self):
    # Either base32 or base8192.
    self.doTestInvalid(_SAMPLES[0], encoding_scheme='xxx')

  def testBadProject(self):
    # Should be a non-empty string contains only alphanumerics in upper case.
    self.doTestInvalid(_SAMPLES[0], project='')
    self.doTestInvalid(_SAMPLES[0], project='proj')

  def testBadEncodePatternIndex(self):
    # The encoding_pattern_index is either 0 or 1.
    self.doTestInvalid(_SAMPLES[0], encoding_pattern_index=-1)
    self.doTestInvalid(_SAMPLES[0], encoding_pattern_index=2)
    self.doTestInvalid(_SAMPLES[0], encoding_pattern_index=3)

  def testBadImageId(self):
    # The range of the image_id is 0~15.
    self.doTestInvalid(_SAMPLES[0], image_id=16)
    self.doTestInvalid(_SAMPLES[0], image_id=99)

  def testBadComponentsBitset(self):
    # The last bit should be zero.
    self.doTestInvalid(_SAMPLES[0], components_bitset='0010100010')

    # The binary string should contains only '0's and '1's.
    self.doTestInvalid(_SAMPLES[0], components_bitset='0010200010')


class IdentityGenerateFromEncodedStringTest(unittest.TestCase,
                                            _IdentityGeneratorTestBase):
  NEEDED_ARGS = ['encoding_scheme', 'encoded_string']

  def GenerateIdentity(self, **kwargs):
    return Identity.GenerateFromEncodedString(**kwargs)

  def testBadEncodingScheme(self):
    # Either base32 or base8192.
    self.doTestInvalid(_SAMPLES[0], encoding_scheme='xxx')

  def testBadEncodedString(self):
    # Bad project name.
    self.doTestInvalid(_SAMPLES[0], encoded_string='PROj ERVY-AL')

    # No project name.
    self.doTestInvalid(_SAMPLES[0], encoded_string='ERVY-5O')

    # Bad checksum.
    self.doTestInvalid(_SAMPLES[0], encoded_string='PROJ ERVY-XX')

    # components_bitset not ends with 1.
    self.doTestInvalid(_SAMPLES[0], encoded_string='PROJ XACO')


if __name__ == '__main__':
  unittest.main()
