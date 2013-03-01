#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common # pylint: disable=W0611
import unittest2

from cros.factory.schema import (
    SchemaException, Scalar, AnyOf, Dict, FixedDict, List)


class SchemaTest(unittest2.TestCase):
  def testScalar(self):
    self.assertRaisesRegexp(
        SchemaException, r'Scalar element type .* is iterable',
        Scalar, 'foo', list)
    schema = Scalar('foo', int)
    self.assertRaisesRegexp(
        SchemaException, r'Type mismatch on .*: expected .*, got .*',
        schema.Validate, 'bar')
    self.assertEquals(None, schema.Validate(0))

  def testDict(self):
    self.assertRaisesRegexp(
        SchemaException, r'key_type .* of Dict .* is not Scalar',
        Dict, 'foo', 'key', Scalar('value', int))
    self.assertRaisesRegexp(
        SchemaException, r'value_type .* of Dict .* is not Schema object',
        Dict, 'foo', Scalar('key', str), 'value')
    schema = Dict('foo', Scalar('key', int), Scalar('value', str))
    self.assertRaisesRegexp(
        SchemaException, r'Type mismatch on .*: expected dict, got .*',
        schema.Validate, 'bar')
    self.assertRaisesRegexp(
        SchemaException, r'Type mismatch on .*: expected .*int.*, got .*',
        schema.Validate, {'0': 'bar'})
    self.assertRaisesRegexp(
        SchemaException, r'Type mismatch on .*: expected .*str.*, got .*',
        schema.Validate, {0: 1})
    self.assertEquals(None, schema.Validate({0: 'bar'}))

  def testFixedDict(self):
    self.assertRaisesRegexp(
        SchemaException, r'items of FixedDict .* should be a dict',
        FixedDict, 'foo', 'items', 'optional_items')
    self.assertRaisesRegexp(
        SchemaException, r'optional_items of FixedDict .* should be a dict',
        FixedDict, 'foo', {'items': 0}, 'optional_items')
    schema = FixedDict('foo',
                       {'required_item': Scalar('bar', int)},
                       {'optional_item': Scalar('buz', str)})
    self.assertRaisesRegexp(
        SchemaException, r'Type mismatch on .*: expected dict, got .*',
        schema.Validate, 'foo')
    self.assertRaisesRegexp(
        SchemaException, r'Required item .* does not exist in FixedDict .*',
        schema.Validate, {'optional_item': 'buz'})
    self.assertRaisesRegexp(
        SchemaException, r'Type mismatch on .*: expected .*, got .*',
        schema.Validate, {'required_item': 'buz'})
    self.assertRaisesRegexp(
        SchemaException, r'Keys .* are undefined in FixedDict .*',
        schema.Validate, {'required_item': 0, 'unknown_item': 'buz'})
    self.assertRaisesRegexp(
        SchemaException, r'Type mismatch on .*: expected .*, got .*',
        schema.Validate, {'required_item': 0, 'optional_item': 0})
    self.assertEquals(None, schema.Validate(
        {'required_item': 0, 'optional_item': 'foo'}))

  def testList(self):
    self.assertRaisesRegexp(
        SchemaException, r'element_type .* of List .* is not a Schema object',
        List, 'foo', {'foo': 'bar'})
    schema = List('foo', Scalar('buz', int))
    self.assertRaisesRegexp(
        SchemaException, r'Type mismatch on .*: expected list, got .*',
        schema.Validate, 'bar')
    self.assertRaisesRegexp(
        SchemaException, r'Type mismatch on .*: expected .*int.*, got .*str.*',
        schema.Validate, [0, 1, 'foo'])
    self.assertEquals(None, schema.Validate([0, 1, 2]))

  def testAnyOf(self):
    self.assertRaisesRegexp(
        SchemaException, r'type_list of AnyOf .* should be a list of Schema '
        'types', AnyOf, 'foo', Scalar('bar', int))
    schema = AnyOf('foo', [Scalar('bar', str), Scalar('buz', int)])
    self.assertRaisesRegexp(
        SchemaException, r'.* does not match any type in .*',
        schema.Validate, {'a': 0})
    self.assertEquals(None, schema.Validate('foo'))
    self.assertEquals(None, schema.Validate(0))

  def testValidate(self):
    schema = (
        Dict('encoded_fields', Scalar('encoded_field', str),
          Dict('encoded_indices', Scalar('encoded_index', int),
            Dict('component_classes', Scalar('component_class', str),
              AnyOf('component_names', [
                Scalar('component_name', str),
                List('component_name_list'),
                Scalar('null', type(None))])))))
    data = {
      'audio_codec': {
        0: {
          'audio_codec': ['codec_0', 'hdmi_0']
        },
        1: {
          'audio_codec': ['codec_1', 'hdmi_1']
        }
      },
      'bluetooth': {
        0: {
          'bluetooth': 'bluetooth_0'
        }
      },
      'cellular': {
        0: {
          'cellular': None
        }
      },
      'firmware': {
        0: {
          'hash_gbb': 'hash_gbb_0',
          'key_recovery': 'key_recovery_0',
          'key_root': 'key_root_0',
          'ro_ec_firmware': 'ro_ec_firmware_0',
          'ro_main_firmware': 'ro_main_firmware_0'
        }
      }

    }
    self.assertEquals(None, schema.Validate(data))
    schema = (
        List('patterns',
          Dict('pattern', Scalar('encoded_field', str),
               Scalar('bit_length', int))))
    data = [
      {'audio_codec': 1},
      {'battery': 2},
      {'bluetooth': 2},
      {'camera': 0},
      {'cellular': 1}
    ]
    self.assertEquals(None, schema.Validate(data))
    schema = (
        Dict('components', Scalar('component_class', str),
          Dict('component_names', Scalar('component_name', str),
            FixedDict('component_attrs',
                      {'value': AnyOf('probed_value', [
                          List('value_list'), Scalar('value_str', str)])},
                      {'labels': List('labels_list', Scalar('label', str))}))))
    data = {
      'flash_chip': {
        'flash_chip_0': {
          'value': 'Flash Chip'
        }
      },
      'keyboard': {
        'keyboard_gb': {
          'value': 'xkb:gb:extd:eng',
          'labels': ['GB']
        },
        'keyboard_us': {
          'value': 'xkb:us::eng',
          'labels': ['US']
        }
      },
      'storage': {
        'storage_0': {
          'value': '16G SSD #123456',
          'labels': ['SSD', '16G']
        },
        'storage_1': {
          'value': '32G SSD #123456',
          'labels': ['SSD', '32G']
        }
      }
    }
    self.assertEquals(None, schema.Validate(data))


if __name__ == '__main__':
  unittest2.main()
