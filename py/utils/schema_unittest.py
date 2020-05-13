#!/usr/bin/env python3
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re
import unittest

from cros.factory.utils.schema import AnyOf
from cros.factory.utils.schema import Dict
from cros.factory.utils.schema import FixedDict
from cros.factory.utils.schema import List
from cros.factory.utils.schema import Optional
from cros.factory.utils.schema import RegexpStr
from cros.factory.utils.schema import Scalar
from cros.factory.utils.schema import SchemaException
from cros.factory.utils.schema import Tuple


class SchemaTest(unittest.TestCase):

  def testScalar(self):
    self.assertRaisesRegex(
        SchemaException,
        r'element_type .* of Scalar \'foo\' is not a scalar type',
        Scalar, 'foo', list)
    schema = Scalar('foo', int)
    self.assertEqual("Scalar('foo', <class 'int'>)", repr(schema))
    self.assertRaisesRegex(
        SchemaException, r'Type mismatch on .*: expected .*, got .*',
        schema.Validate, 'bar')
    self.assertEqual(None, schema.Validate(0))

  def testScalarChoices(self):
    schema = Scalar('foo', int, choices=[1, 2])
    self.assertEqual("Scalar('foo', <class 'int'>, choices=[1, 2])",
                     repr(schema))
    self.assertEqual(None, schema.Validate(1))
    self.assertEqual(None, schema.Validate(2))
    self.assertRaisesRegex(
        SchemaException, r'Value mismatch on 3: expected one of \[1, 2\]',
        schema.Validate, 3)

  def testRegexpStr(self):
    schema = RegexpStr('foo', re.compile(r'ab*a$'))
    schema.Validate('aa')
    schema.Validate('abbbba')
    self.assertRaises(SchemaException, schema.Validate, 123)
    self.assertRaises(SchemaException, schema.Validate, 'abbx')

  def testDict(self):
    self.assertRaisesRegex(
        SchemaException, r'key_type .* of Dict .* is not Scalar', Dict,
        'foo', 'key', Scalar('value', int))
    self.assertRaisesRegex(
        SchemaException, r'key_type .* of Dict .* is not Scalar', Dict,
        'foo', AnyOf([Scalar('key1', int), List('key2')], label='bar'),
        Scalar('value', int))
    self.assertRaisesRegex(
        SchemaException, r'value_type .* of Dict .* is not Schema object',
        Dict, 'foo', Scalar('key', str), 'value')
    schema = Dict('foo', Scalar('key', int), Scalar('value', str))
    self.assertEqual(
        "Dict('foo', key_type=Scalar('key', <class 'int'>), "
        "value_type=Scalar('value', <class 'str'>), size=[0, inf])",
        repr(schema))
    self.assertRaisesRegex(
        SchemaException, r'Type mismatch on .*: expected dict, got .*',
        schema.Validate, 'bar')
    self.assertRaisesRegex(
        SchemaException, r'Type mismatch on .*: expected .*int.*, got .*',
        schema.Validate, {'0': 'bar'})
    self.assertRaisesRegex(
        SchemaException, r'Type mismatch on .*: expected .*str.*, got .*',
        schema.Validate, {0: 1})
    self.assertEqual(None, schema.Validate({0: 'bar'}))
    schema = Dict('foo',
                  AnyOf([Scalar('key1', int), Scalar('key2', str)],
                        label='key'),
                  Scalar('value', str))
    self.assertEqual(None, schema.Validate({0: 'bar'}))
    self.assertEqual(None, schema.Validate({'foo': 'bar'}))

  def testFixedDict(self):
    self.assertRaisesRegex(
        SchemaException, r'items of FixedDict .* should be a dict',
        FixedDict, 'foo', 'items', 'optional_items')
    self.assertRaisesRegex(
        SchemaException,
        r'optional_items of FixedDict .* should be a dict', FixedDict, 'foo',
        {'items': 0}, 'optional_items')
    schema = FixedDict('foo',
                       {'required_item': Scalar('bar', int)},
                       {'optional_item': Scalar('buz', str)})
    self.assertEqual("FixedDict('foo', "
                     "items={'required_item': Scalar('bar', <class 'int'>)}, "
                     "optional_items={'optional_item': "
                     "Scalar('buz', <class 'str'>)})",
                     repr(schema))
    self.assertRaisesRegex(
        SchemaException, r'Type mismatch on .*: expected dict, got .*',
        schema.Validate, 'foo')
    self.assertRaisesRegex(
        SchemaException,
        r'Required item .* does not exist in FixedDict .*', schema.Validate,
        {'optional_item': 'buz'})
    self.assertRaisesRegex(
        SchemaException, r'Type mismatch on .*: expected .*, got .*',
        schema.Validate, {'required_item': 'buz'})
    self.assertRaisesRegex(
        SchemaException, r'Keys .* are undefined in FixedDict .*',
        schema.Validate, {'required_item': 0, 'unknown_item': 'buz'})
    self.assertRaisesRegex(
        SchemaException, r'Type mismatch on .*: expected .*, got .*',
        schema.Validate, {'required_item': 0, 'optional_item': 0})
    self.assertEqual(None, schema.Validate(
        {'required_item': 0, 'optional_item': 'foo'}))

    schema = FixedDict('foo', items={'required_item': Scalar('bar', int)},
                       optional_items={'optional_item': Scalar('buz', str)},
                       allow_undefined_keys=True)
    self.assertEqual(None, schema.Validate(
        {'required_item': 0, 'optional_item': 'foo', 'extra_key': 'extra_val'}))
    self.assertEqual(None, schema.Validate(
        {'required_item': 0, 'extra_key': 'extra_val'}))
    self.assertRaises(SchemaException, schema.Validate,
                      {'optional_item': 'foo', 'extra_key': 'extra_val'})

  def testList(self):
    self.assertRaisesRegex(
        SchemaException,
        r'element_type .* of List .* is not a Schema object', List, 'foo',
        {'foo': 'bar'})
    schema = List('foo', Scalar('buz', int), min_length=1)
    self.assertEqual("List('foo', Scalar('buz', <class 'int'>), [1, inf])",
                     repr(schema))
    self.assertRaisesRegex(
        SchemaException, r'Type mismatch on .*: expected list, got .*',
        schema.Validate, 'bar')
    self.assertRaisesRegex(
        SchemaException,
        r'Type mismatch on .*: expected .*int.*, got .*str.*', schema.Validate,
        [0, 1, 'foo'])
    self.assertRaisesRegex(
        SchemaException, r'Length mismatch.*', schema.Validate, [])
    self.assertEqual(None, schema.Validate([0, 1, 2]))

  def testTuple(self):
    self.assertRaisesRegex(
        SchemaException,
        r'element_types .* of Tuple .* is not a tuple or list', Tuple, 'foo',
        'foo')
    schema = Tuple('foo', (Scalar('bar', int), Scalar('buz', str)))
    self.assertEqual("Tuple('foo', (Scalar('bar', <class 'int'>), "
                     "Scalar('buz', <class 'str'>)))",
                     repr(schema))
    self.assertRaisesRegex(
        SchemaException, r'Type mismatch on .*: expected tuple, got .*',
        schema.Validate, 'bar')
    self.assertRaisesRegex(
        SchemaException,
        r'Number of elements in tuple .* does not match that '
        'defined in Tuple schema .*', schema.Validate, (0,))
    self.assertRaisesRegex(
        SchemaException, r'Type mismatch on .*: expected .*, got .*',
        schema.Validate, ('0', 'foo'))
    self.assertEqual(None, schema.Validate((0, 'foo')))

  def testAnyOf(self):
    self.assertRaisesRegex(
        SchemaException, r'types in AnyOf.* should be a list of Schemas',
        AnyOf, Scalar('bar', int))

    self.assertRaisesRegex(
        SchemaException, r'types in AnyOf.* should be a list of Schemas',
        AnyOf, [Scalar('bar', int), 'not a Schema'])

    schema = AnyOf([Scalar('bar', str), Scalar('buz', int)])
    self.assertEqual("AnyOf([Scalar('bar', <class 'str'>), "
                     "Scalar('buz', <class 'int'>)])",
                     repr(schema))
    self.assertRaisesRegex(
        SchemaException, r'.* does not match any type in .*',
        schema.Validate, {'a': 0})
    self.assertEqual(None, schema.Validate('foo'))
    self.assertEqual(None, schema.Validate(0))

    schema_label = AnyOf([Scalar('bar', str), Scalar('buz', int)],
                         label='bar_buz')
    self.assertEqual("AnyOf([Scalar('bar', <class 'str'>), "
                     "Scalar('buz', <class 'int'>)], label='bar_buz')",
                     repr(schema_label))

  def testOptional(self):
    self.assertRaisesRegex(
        SchemaException,
        r'types in Optional.* should be a Schema or a list of Schemas',
        Optional, 'not a Schema')

    schema1 = Optional(Scalar('bar', str))
    self.assertEqual("Optional([Scalar('bar', <class 'str'>)])", repr(schema1))
    self.assertRaisesRegex(
        SchemaException,
        r'.* is not None and does not match any type in .*', schema1.Validate,
        {'a': 0})
    self.assertEqual(None, schema1.Validate(None))
    self.assertEqual(None, schema1.Validate('foo'))

    schema2 = Optional([Scalar('bar', str), Scalar('buz', int)])
    self.assertRaisesRegex(
        SchemaException,
        r'.* is not None and does not match any type in .*', schema2.Validate,
        {'a': 0})
    self.assertEqual(None, schema2.Validate(None))
    self.assertEqual(None, schema2.Validate('foo'))
    self.assertEqual(None, schema2.Validate(0))

    schema_label = Optional([Scalar('bar', str), Scalar('buz', int)],
                            label='bar_buz')
    self.assertEqual("Optional([Scalar('bar', <class 'str'>), "
                     "Scalar('buz', <class 'int'>)], label='bar_buz')",
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
    self.assertEqual(None, schema1.Validate(data))
    self.assertEqual(None, schema2.Validate(data))

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
    self.assertEqual(None, schema.Validate(data))
    schema = (
        Dict('components', Scalar('component_class', str),
             Dict('component_names', Scalar('component_name', str),
                  FixedDict('component_attrs',
                            {'value': AnyOf([
                                List('value_list'), Scalar('value_str', str)])},
                            {'labels': List('labels_list',
                                            Scalar('label', str))}))))
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
    self.assertEqual(None, schema.Validate(data))


if __name__ == '__main__':
  unittest.main()
