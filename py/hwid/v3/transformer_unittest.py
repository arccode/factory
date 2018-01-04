#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

import factory_common  # pylint: disable=W0611

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
        ('001', BOM(0, 0, dict(cpu=['cpu_0'], audio=[], video=[]))),

        # battery_field is 0.
        ('0001', BOM(0, 2, dict(cpu=['cpu_0'], audio=[], video=[],
                                battery=['battery_0']))),

        # battery_field is 3.
        ('00000000111', BOM(0, 3, dict(cpu=['cpu_0'], audio=[], video=[],
                                       battery=['battery_3'] * 3))),

        # audio_and_video_field is 2
        ('1001', BOM(0, 2, dict(cpu=['cpu_0'], audio=['audio_1', 'audio_0'],
                                video=[], battery=['battery_0']))),

        # audio_and_video_field is 4
        ('00000100001', BOM(0, 3, dict(cpu=['cpu_0'], audio=['audio_0'],
                                       video=['video_0'],
                                       battery=['battery_0']))),

        # audio_and_video_field is 7, battery_field is 3
        ('00000111111', BOM(0, 3, dict(cpu=['cpu_0'],
                                       audio=['audio_0'],
                                       video=['video_0', 'video_1'],
                                       battery=['battery_3'] * 3)))]


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

  def testMissingEncodedField(self):
    bom = self.test_data[1][1]
    bom.RemoveComponent('battery')
    self.assertRaises(HWIDException,
                      transformer.BOMToIdentity, self.database, bom)

    # `audio_and_video_field` needs both audio and video components.
    bom = self.test_data[2][1]
    bom.RemoveComponent('audio')
    self.assertRaises(HWIDException,
                      transformer.BOMToIdentity, self.database, bom)

  def testTooManyEncodedField(self):
    bom = self.test_data[0][1]
    bom.SetComponent('battery', self.test_data[1][1].components['battery'])
    self.assertRaises(HWIDException,
                      transformer.BOMToIdentity, self.database, bom)

  def testEncodedNumberOutOfRange(self):
    bom = self.test_data[5][1]
    bom.image_id = 2
    self.assertRaises(HWIDException,
                      transformer.BOMToIdentity, self.database, bom)

  def testNormal(self):
    def _VerifyTransformer(components_bitset, bom):
      identity = transformer.BOMToIdentity(self.database, bom)
      self.assertEqual(identity.project, 'CHROMEBOOK')
      self.assertEqual(identity.encoding_pattern_index, 0)
      self.assertEqual(identity.image_id, bom.image_id)
      self.assertEqual(identity.components_bitset, components_bitset)

    for components_bitset, bom in self.test_data:
      _VerifyTransformer(components_bitset, bom)

      # Extra components shouldn't fail the transformer.
      bom.SetComponent('cool', 'meow')
      _VerifyTransformer(components_bitset, bom)


class IdentityToBOMTest(_TransformerTestBase):
  def _GenerateIdentityFromTestData(self, test_data_idx,
                                    encoding_scheme=None, project=None,
                                    encoding_pattern_index=None,
                                    image_id=None, components_bitset=None):
    test_data = self.test_data[test_data_idx]

    project = project or self.database.project
    encoding_pattern_index = (
        encoding_pattern_index or test_data[1].encoding_pattern_index)
    image_id = image_id or test_data[1].image_id
    components_bitset = components_bitset or test_data[0]

    encoding_scheme = (
        encoding_scheme or self.database.pattern.GetEncodingScheme(image_id))

    return Identity.GenerateFromBinaryString(
        encoding_scheme, project, encoding_pattern_index, image_id,
        components_bitset)

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
