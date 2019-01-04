#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.bom import BOM
from cros.factory.hwid.v3.common import HWIDException
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3.identity import Identity
from cros.factory.hwid.v3 import transformer


_TEST_DATABASE_FILENAME = os.path.join(
    os.path.dirname(__file__), 'testdata', 'test_transformer_db.yaml')


class _TransformerTestBase(unittest.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(_TEST_DATABASE_FILENAME,
                                      verify_checksum=False)
    self.test_data = [
        # Simplest case.
        ('001', BOM(0, 0, dict(cpu=['cpu_0'], audio=[], video=[], battery=[])),
         None, None),

        # battery_field is 0.
        ('0001', BOM(0, 2, dict(cpu=['cpu_0'], audio=[], video=[],
                                battery=['battery_0'])), None, None),

        # battery_field is 2.
        ('00000000101', BOM(0, 3, dict(cpu=['cpu_0'], audio=[], video=[],
                                       battery=['battery_2'] * 2)), None, None),

        # audio_and_video_field is 2
        ('1001', BOM(0, 2, dict(cpu=['cpu_0'], audio=['audio_1', 'audio_0'],
                                video=[], battery=['battery_0'])), None, None),

        # audio_and_video_field is 4
        ('00000100001', BOM(0, 3, dict(cpu=['cpu_0'], audio=['audio_0'],
                                       video=['video_0'],
                                       battery=['battery_0'])), None, None),

        # audio_and_video_field is 7, battery_field is 2
        ('00000111101', BOM(0, 3, dict(cpu=['cpu_0'],
                                       audio=['audio_0'],
                                       video=['video_0', 'video_1'],
                                       battery=['battery_2'] * 2)), None, None),
        # with configless fields
        ('001', BOM(0, 0, dict(cpu=['cpu_0'], audio=[], video=[], battery=[])),
         'BRAND', '0-8-74-80')]


class BOMToIdentityTest(_TransformerTestBase):
  def testInvalidEncodingPatternIndex(self):
    for invalid_encoding_pattern_index in [1, 2, 3, -1]:
      bom = self.test_data[0][1]
      bom.encoding_pattern_index = invalid_encoding_pattern_index
      self.assertRaises(HWIDException,
                        transformer.BOMToIdentity, self.database, bom)

  def testInvalidImageId(self):
    for invalid_image_id in [4, 5, 6, -1]:
      bom = self.test_data[0][1]
      bom.image_id = invalid_image_id
      self.assertRaises(HWIDException,
                        transformer.BOMToIdentity, self.database, bom)

  def testEncodedNumberOutOfRange(self):
    bom = self.test_data[5][1]
    bom.image_id = 2
    self.assertRaises(HWIDException,
                      transformer.BOMToIdentity, self.database, bom)

  def testNormal(self):
    def _VerifyTransformer(components_bitset, bom, brand_code,
                           encoded_configless):
      identity = transformer.BOMToIdentity(self.database, bom, brand_code,
                                           encoded_configless)
      self.assertEqual(identity.project, 'CHROMEBOOK')
      self.assertEqual(identity.encoding_pattern_index, 0)
      self.assertEqual(identity.image_id, bom.image_id)
      self.assertEqual(identity.components_bitset, components_bitset)
      self.assertEqual(identity.brand_code, brand_code)
      self.assertEqual(identity.encoded_configless, encoded_configless)

    for (components_bitset, bom, brand_code,
         encoded_configless) in self.test_data:
      _VerifyTransformer(components_bitset, bom, brand_code, encoded_configless)

      # Extra components shouldn't fail the transformer.
      bom.SetComponent('cool', 'meow')
      _VerifyTransformer(components_bitset, bom, None, None)


class IdentityToBOMTest(_TransformerTestBase):
  def _GenerateIdentityFromTestData(self, test_data_idx,
                                    encoding_scheme=None, project=None,
                                    encoding_pattern_index=None,
                                    image_id=None, components_bitset=None,
                                    brand_code=None, encoded_configless=None):
    test_data = self.test_data[test_data_idx]

    project = project or self.database.project
    encoding_pattern_index = (
        encoding_pattern_index or test_data[1].encoding_pattern_index)
    image_id = image_id or test_data[1].image_id
    components_bitset = components_bitset or test_data[0]

    encoding_scheme = (
        encoding_scheme or self.database.GetEncodingScheme(image_id))

    brand_code = brand_code or test_data[2]
    encoded_configless = encoded_configless or test_data[3]

    return Identity.GenerateFromBinaryString(
        encoding_scheme, project, encoding_pattern_index, image_id,
        components_bitset, brand_code, encoded_configless)

  def testInvalidEncodingScheme(self):
    identity = self._GenerateIdentityFromTestData(0, encoding_scheme='base8192')
    self.assertRaises(HWIDException,
                      transformer.IdentityToBOM, self.database, identity)

  def testInvalidProject(self):
    identity = self._GenerateIdentityFromTestData(0, project='CHROMEBOOK123')
    self.assertRaises(HWIDException,
                      transformer.IdentityToBOM, self.database, identity)

  def testInvalidEncodingPattern(self):
    identity = self._GenerateIdentityFromTestData(0, encoding_pattern_index=1)
    self.assertRaises(HWIDException,
                      transformer.IdentityToBOM, self.database, identity)

  def testInvalidImageId(self):
    for invalid_image_id in [4, 5, 6]:
      identity = self._GenerateIdentityFromTestData(
          0, image_id=invalid_image_id, encoding_scheme='base8192')
      self.assertRaises(HWIDException,
                        transformer.IdentityToBOM, self.database, identity)

  def testComponentsBitsetTooLong(self):
    # Adds some useless bits.
    identity = self._GenerateIdentityFromTestData(
        0, components_bitset=self.test_data[0][0] + '010101')
    self.assertRaises(HWIDException,
                      transformer.IdentityToBOM, self.database, identity)

  def testEncodedFieldIndexOutOfRange(self):
    # Modify the bits for cpu field to 31.
    identity = self._GenerateIdentityFromTestData(
        5, components_bitset='11111' + self.test_data[5][0][5:])
    self.assertRaises(HWIDException,
                      transformer.IdentityToBOM, self.database, identity)

  def testComponentsBitsetTooShort(self):
    # In real case, this case is confusing.  But in theory this is acceptable.

    # Removes the bits for the battery field.
    identity = self._GenerateIdentityFromTestData(
        4, components_bitset=self.test_data[4][0][:-3] + '1')
    self.assertEquals(self.test_data[4][1],
                      transformer.IdentityToBOM(self.database, identity))

  def testNormal(self):
    for idx, test_data in enumerate(self.test_data):
      identity = self._GenerateIdentityFromTestData(idx)
      self.assertEquals(test_data[1],
                        transformer.IdentityToBOM(self.database, identity))


if __name__ == '__main__':
  unittest.main()
