#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common # pylint: disable=W0611
import unittest

from cros.factory.schema import (AnyOf, Dict, FixedDict, List, Optional, Scalar,
                                 SchemaException, Tuple)


class SchemaTest(unittest.TestCase):
  def testScalar(self):
    self.assertRaisesRegexp(
        SchemaException,
        r'element_type .* of Scalar \'foo\' is not a scalar type',
        Scalar, 'foo', list)
    schema = Scalar('foo', int)
    self.assertEquals("Scalar('foo', <type 'int'>)", repr(schema))
    self.assertRaisesRegexp(
        SchemaException, r'Type mismatch on .*: expected .*, got .*',
        schema.Validate, 'bar')
    self.assertEquals(None, schema.Validate(0))

  def testDict(self):
    self.assertRaisesRegexp(
        SchemaException, r'key_type .* of Dict .* is not Scalar',
        Dict, 'foo', 'key', Scalar('value', int))
    self.assertRaisesRegexp(
        SchemaException, r'key_type .* of Dict .* is not Scalar',
        Dict, 'foo', AnyOf([Scalar('key1', int), List('key2')], label='bar'),
        Scalar('value', int))
    self.assertRaisesRegexp(
        SchemaException, r'value_type .* of Dict .* is not Schema object',
        Dict, 'foo', Scalar('key', str), 'value')
    schema = Dict('foo', Scalar('key', int), Scalar('value', str))
    self.assertEquals("Dict('foo', key_type=Scalar('key', <type 'int'>), "
                      "value_type=Scalar('value', <type 'str'>))",
                      repr(schema))
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
    schema = Dict('foo',
                  AnyOf([Scalar('key1', int), Scalar('key2', str)],
                        label='key'),
                  Scalar('value', str))
    self.assertEquals(None, schema.Validate({0: 'bar'}))
    self.assertEquals(None, schema.Validate({'foo': 'bar'}))

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
    self.assertEquals("FixedDict('foo', "
                      "items={'required_item': Scalar('bar', <type 'int'>)}, "
                      "optional_items={'optional_item': "
                      "Scalar('buz', <type 'str'>)})",
                      repr(schema))
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
    self.assertEquals("List('foo', Scalar('buz', <type 'int'>))", repr(schema))
    self.assertRaisesRegexp(
        SchemaException, r'Type mismatch on .*: expected list, got .*',
        schema.Validate, 'bar')
    self.assertRaisesRegexp(
        SchemaException, r'Type mismatch on .*: expected .*int.*, got .*str.*',
        schema.Validate, [0, 1, 'foo'])
    self.assertEquals(None, schema.Validate([0, 1, 2]))

  def testTuple(self):
    self.assertRaisesRegexp(
        SchemaException, r'element_types .* of Tuple .* is not a tuple or list',
        Tuple, 'foo', 'foo')
    schema = Tuple('foo', (Scalar('bar', int), Scalar('buz', str)))
    self.assertEquals("Tuple('foo', (Scalar('bar', <type 'int'>), "
                      "Scalar('buz', <type 'str'>)))",
                      repr(schema))
    self.assertRaisesRegexp(
        SchemaException, r'Type mismatch on .*: expected tuple, got .*',
        schema.Validate, 'bar')
    self.assertRaisesRegexp(
        SchemaException, r'Number of elements in tuple .* does not match that '
        'defined in Tuple schema .*', schema.Validate, (0,))
    self.assertRaisesRegexp(
        SchemaException, r'Type mismatch on .*: expected .*, got .*',
        schema.Validate, ('0', 'foo'))
    self.assertEquals(None, schema.Validate((0, 'foo')))

  def testAnyOf(self):
    self.assertRaisesRegexp(
        SchemaException,
        r'types in AnyOf.* should be a list of Schemas',
        AnyOf, Scalar('bar', int))

    self.assertRaisesRegexp(
        SchemaException,
        r'types in AnyOf.* should be a list of Schemas',
        AnyOf, [Scalar('bar', int), 'not a Schema'])

    schema = AnyOf([Scalar('bar', str), Scalar('buz', int)])
    self.assertEqual("AnyOf([Scalar('bar', <type 'str'>), "
                     "Scalar('buz', <type 'int'>)])",
                     repr(schema))
    self.assertRaisesRegexp(
        SchemaException, r'.* does not match any type in .*',
        schema.Validate, {'a': 0})
    self.assertEquals(None, schema.Validate('foo'))
    self.assertEquals(None, schema.Validate(0))

    schema_label = AnyOf([Scalar('bar', str), Scalar('buz', int)],
                         label='bar_buz')
    self.assertEqual("AnyOf([Scalar('bar', <type 'str'>), "
                     "Scalar('buz', <type 'int'>)], label='bar_buz')",
                     repr(schema_label))

  def testOptional(self):
    self.assertRaisesRegexp(
        SchemaException,
        r'types in Optional.* should be a Schema or a list of Schemas',
        Optional, 'not a Schema')

    schema1 = Optional(Scalar('bar', str))
    self.assertEqual("Optional([Scalar('bar', <type 'str'>)])", repr(schema1))
    self.assertRaisesRegexp(
        SchemaException, r'.* is not None and does not match any type in .*',
        schema1.Validate, {'a': 0})
    self.assertEquals(None, schema1.Validate(None))
    self.assertEquals(None, schema1.Validate('foo'))

    schema2 = Optional([Scalar('bar', str), Scalar('buz', int)])
    self.assertRaisesRegexp(
        SchemaException, r'.* is not None and does not match any type in .*',
        schema2.Validate, {'a': 0})
    self.assertEquals(None, schema2.Validate(None))
    self.assertEquals(None, schema2.Validate('foo'))
    self.assertEquals(None, schema2.Validate(0))

    schema_label = Optional([Scalar('bar', str), Scalar('buz', int)],
                            label='bar_buz')
    self.assertEqual("Optional([Scalar('bar', <type 'str'>), "
                     "Scalar('buz', <type 'int'>)], label='bar_buz')",
                     repr(schema_label))

  def testValidate(self):
    # schema1 and schema2 are equivalent. schema2 uses Optional to replace
    # AnyOf type.
    schema1 = (
        Dict('encoded_fields', Scalar('encoded_field', str),
             Dict('encoded_indices', Scalar('encoded_index', int),
                  Dict('component_classes', Scalar('component_class', str),
                       AnyOf([Scalar('component_name', str),
                              List('component_name_list'),
                              Scalar('null', type(None))])))))
    schema2 = (
        Dict('encoded_fields', Scalar('encoded_field', str),
             Dict('encoded_indices', Scalar('encoded_index', int),
                  Dict('component_classes', Scalar('component_class', str),
                       Optional([Scalar('component_name', str),
                                 List('component_name_list')])))))

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
    self.assertEquals(None, schema1.Validate(data))
    self.assertEquals(None, schema2.Validate(data))

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
                      {'value': AnyOf([
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
  unittest.main()
