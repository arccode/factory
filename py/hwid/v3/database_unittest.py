#!/usr/bin/env python
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.common import HWIDException
from cros.factory.hwid.v3.database import Components
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3.database import EncodedFields
from cros.factory.hwid.v3.database import ImageId
from cros.factory.hwid.v3.database import Pattern
from cros.factory.hwid.v3.database import Rules
from cros.factory.utils import file_utils


_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


def Unordered(data):
  if isinstance(data, dict):
    return {k: Unordered(v) for k, v in data.iteritems()}
  elif isinstance(data, list):
    return [Unordered(a) for a in data]
  return data


class DatabaseTest(unittest.TestCase):
  def testLoadFile(self):
    Database.LoadFile(os.path.join(_TEST_DATA_PATH, 'test_database_db.yaml'))
    Database.LoadFile(
        os.path.join(_TEST_DATA_PATH, 'test_database_db_bad_checksum.yaml'),
        verify_checksum=False)

    self.assertRaises(HWIDException, Database.LoadFile,
                      os.path.join(_TEST_DATA_PATH,
                                   'test_database_db_bad_checksum.yaml'))
    for case in ['missing_pattern',
                 'missing_encoded_field',
                 'missing_component']:
      self.assertRaises(HWIDException, Database.LoadFile,
                        os.path.join(_TEST_DATA_PATH,
                                     'test_database_db_%s.yaml' % case),
                        verify_checksum=False)

  def testLoadDump(self):
    db = Database.LoadFile(
        os.path.join(_TEST_DATA_PATH, 'test_database_db.yaml'))
    db2 = Database.LoadData(db.DumpData(include_checksum=True))

    self.assertEquals(db, db2)

    db = Database.LoadFile(
        os.path.join(_TEST_DATA_PATH, 'test_database_db.yaml'))
    with file_utils.UnopenedTemporaryFile() as path:
      db.DumpFile(path, include_checksum=True)
      Database.LoadFile(path, verify_checksum=False)


class ImageIdTest(unittest.TestCase):
  def testExport(self):
    expr = {0: 'EVT', 1: 'DVT', 2: 'PVT'}
    self.assertEquals(Unordered(ImageId(expr).Export()),
                      {0: 'EVT', 1: 'DVT', 2: 'PVT'})

  def testSetItem(self):
    image_id = ImageId({0: 'EVT', 1: 'DVT', 2: 'PVT'})
    image_id[3] = 'XXYYZZ'
    image_id[5] = 'AABBCC'
    self.assertEquals(Unordered(image_id.Export()),
                      {0: 'EVT', 1: 'DVT', 2: 'PVT', 3: 'XXYYZZ', 5: 'AABBCC'})

    def func(a, b):
      image_id[a] = b
    self.assertRaises(HWIDException, func, 3, 'ZZZ')
    self.assertRaises(HWIDException, func, 4, 4)
    self.assertRaises(HWIDException, func, 'X', 'Y')
    self.assertRaises(HWIDException, func, -1, 'Y')

  def testGettingMethods(self):
    image_id = ImageId({0: 'EVT', 1: 'DVT', 2: 'PVT'})
    self.assertEquals(image_id.max_image_id, 2)
    self.assertEquals(image_id.rma_image_id, None)
    self.assertEquals(image_id[1], 'DVT')
    self.assertEquals(image_id.GetImageIdByName('EVT'), 0)

    image_id = ImageId({0: 'EVT', 1: 'DVT', 2: 'PVT', 15: 'RMA'})
    self.assertEquals(image_id.max_image_id, 2)
    self.assertEquals(image_id.rma_image_id, 15)
    self.assertEquals(image_id[1], 'DVT')
    self.assertEquals(image_id.GetImageIdByName('EVT'), 0)


class ComponentsTest(unittest.TestCase):
  def testExport(self):
    expr = {'cls1': {'items': {'comp11': {'values': {'p1': 'v1', 'p2': 'v2'},
                                          'status': 'unsupported'}}},
            'cls2': {'items': {'comp21': {'values': {'p2': 'v3', 'p4': 'v5'},
                                          'default': True}}},
            'cls3': {'items': {'comp31': {'values': None},
                               'comp41': {'values': {'a': 'b'}}}},
            'cls4': {'items': {'comp41': {'values': None}}, 'probeable': False}}
    c = Components(expr)
    self.assertEquals(Unordered(c.Export()), expr)

  def testSyntaxError(self):
    self.assertRaises(Exception, Components,
                      {'cls1': {}})
    self.assertRaises(Exception, Components,
                      {'cls1': {'items': {'comp1': {'status': 'supported'}}}})
    self.assertRaises(Exception, Components,
                      {'cls1': {'items': {'comp1': {'values': {}}}}})
    self.assertRaises(Exception, Components,
                      {'cls1': {'items': {'comp1': {'values': {'a': 'b'},
                                                    'status': '???'}}}})

  def testCanEncode(self):
    self.assertTrue(Components(
        {'cls1': {'items': {'c1': {'values': {'a': 'b'}}}}}).can_encode)
    self.assertTrue(
        Components({'cls1': {'items': {'c1': {'values': None}}}}).can_encode)

    self.assertTrue(
        Components({'cls1': {'items': {'c1': {'values': {'a': 'b'},
                                              'default': True}}}}).can_encode)
    self.assertFalse(
        Components({'cls1': {'items': {'c1': {'values': {'a': 'b'}}},
                             'probeable': False}}).can_encode)

    self.assertTrue(
        Components({
            'cls1': {
                'items': {
                    'c1': {
                        'values': {'a': 'b'}
                    },
                    # 'c2' is a subset of 'c1', this is allowed, and 'c1' will
                    # have higher priority when encoding.
                    'c2': {
                        'values': {'a': 'b', 'x': 'y'}
                    },
                }}}).can_encode)

    self.assertFalse(
        Components({
            'cls1': {
                'items': {
                    'c1': {
                        'values': {'a': 'b'}
                    },
                    'c2': {
                        'values': {'a': 'b'}
                    },
                }}}).can_encode)
    self.assertTrue(
        Components({
            'cls1': {
                'items': {
                    'c1': {
                        'values': {'a': 'b'}
                    },
                    'c2': {
                        'values': {'a': 'b'},
                        'status': 'duplicate'
                    },
                }}}).can_encode)


  def testAddComponent(self):
    c = Components({})
    c.AddComponent('cls1', 'comp1', {'a': 'b', 'c': 'd'}, 'supported')
    c.AddComponent('cls1', 'comp2', {'a': 'x', 'c': 'd'}, 'unsupported')
    c.AddComponent('cls2', 'comp1', {'a': 'b', 'c': 'd'}, 'deprecated')
    c.AddComponent('cls1', 'comp_default', None, 'supported')
    self.assertEquals(
        Unordered(c.Export()), {
            'cls1': {
                'items': {
                    'comp1': {'values': {'a': 'b', 'c': 'd'}},
                    'comp2': {'values': {'a': 'x', 'c': 'd'},
                              'status': 'unsupported'},
                    'comp_default': {'values': None}}},
            'cls2': {
                'items': {
                    'comp1': {'values': {'a': 'b', 'c': 'd'},
                              'status': 'deprecated'}}}})

    self.assertRaises(HWIDException, c.AddComponent,
                      'cls1', 'comp1', {'aa': 'bb'}, 'supported')
    c.AddComponent('cls1', 'compX1', {'a': 'b', 'c': 'd'}, 'supported')
    self.assertFalse(c.can_encode)

  def testSetComponentStatus(self):
    c = Components({'cls1': {'items': {'comp1': {'values': {'a': 'b'}}}}})
    c.SetComponentStatus('cls1', 'comp1', 'deprecated')
    self.assertEquals(
        Unordered(c.Export()),
        {'cls1': {'items': {'comp1': {'values': {'a': 'b'},
                                      'status': 'deprecated'}}}})

  def testGettingMethods(self):
    c = Components({'cls1': {'items': {'comp1': {'values': {'a': 'b'},
                                                 'status': 'unqualified'},
                                       'comp2': {'values': {'a': 'c'}}}},
                    'cls2': {'items': {'comp3': {'values': {'x': 'y'}}}}})
    self.assertEquals(sorted(c.component_classes), ['cls1', 'cls2'])
    self.assertEquals(len(c.GetComponents('cls1')), 2)
    self.assertEquals(sorted(c.GetComponents('cls1').keys()),
                      ['comp1', 'comp2'])
    self.assertEquals(c.GetComponents('cls1')['comp1'].values, {'a': 'b'})
    self.assertEquals(c.GetComponents('cls1')['comp1'].status, 'unqualified')
    self.assertEquals(c.GetComponents('cls1')['comp2'].values, {'a': 'c'})
    self.assertEquals(c.GetComponents('cls1')['comp2'].status, 'supported')

    self.assertEquals(len(c.GetComponents('cls2')), 1)


class EncodedFieldsTest(unittest.TestCase):
  def testExport(self):
    expr = {'aaa': {0: {'x': [], 'y': 'y', 'z': ['z1', 'z2']},
                    1: {'x': 'xx', 'y': [], 'z': []}},
            'bbb': {0: {'b': ['b1', 'b2', 'b3']}}}
    encoded_fields = EncodedFields(expr)
    self.assertEquals(Unordered(encoded_fields.Export()), expr)

    expr = {'aaa': {0: {'x': [], 'y': 'y', 'z': ['z1', 'z2']},
                    2: {'x': 'xx', 'y': [], 'z': []}}}
    encoded_fields = EncodedFields(expr)
    self.assertEquals(Unordered(encoded_fields.Export()), expr)

  def testSyntaxError(self):
    self.assertRaises(Exception, EncodedFields,
                      {'a': {'bad_index': {'a': None}}})
    self.assertRaises(Exception, EncodedFields,
                      {'a': {0: {}}})
    self.assertRaises(Exception, EncodedFields,
                      {'a': {0: {'a': '3'}, 1: {'c': '9'}}})

  def testCannotEncode(self):
    self.assertFalse(
        EncodedFields({'a': {0: {'a': '3'}, 1: {'a': '3'}}}).can_encode)

  def testAddFieldComponents(self):
    e = EncodedFields({'e1': {0: {'a': 'A', 'b': 'B'}}})
    e.AddFieldComponents('e1', {'a': ['AA'], 'b': ['BB']})
    e.AddFieldComponents('e1', {'a': ['AA', 'AX'], 'b': ['BB']})

    self.assertEquals(Unordered(e.Export()),
                      {'e1': {0: {'a': 'A', 'b': 'B'},
                              1: {'a': 'AA', 'b': 'BB'},
                              2: {'a': ['AA', 'AX'], 'b': 'BB'}}})

    # `e1` should encode only component class `a` and `b`.
    self.assertRaises(HWIDException, e.AddFieldComponents,
                      'e1', {'c': ['CC'], 'a': ['AAAAAA'], 'b': ['BB']})

  def testAddNewField(self):
    e = EncodedFields({'e1': {0: {'a': 'A', 'b': 'B'}}})
    e.AddNewField('e2', {'c': ['CC'], 'd': ['DD']})

    self.assertEquals(Unordered(e.Export()),
                      {'e1': {0: {'a': 'A', 'b': 'B'}},
                       'e2': {0: {'c': 'CC', 'd': 'DD'}}})

    # `e2` already exists.
    self.assertRaises(HWIDException, e.AddNewField,
                      'e2', {'xxx': ['yyy']})
    self.assertRaises(HWIDException, e.AddNewField, 'e3', {})

  def testGettingMethods(self):
    e = EncodedFields({'e1': {0: {'a': 'A', 'b': 'B'},
                              1: {'a': ['AA', 'AAA'], 'b': 'B'}},
                       'e2': {0: {'c': None, 'd': []},
                              2: {'c': ['C2', 'C1', 'C3'], 'd': 'D'}}})
    self.assertEquals(set(e.encoded_fields), set(['e1', 'e2']))
    self.assertEquals(e.GetField('e1'),
                      {0: {'a': ['A'], 'b': ['B']},
                       1: {'a': ['AA', 'AAA'], 'b': ['B']}})
    self.assertEquals(e.GetField('e2'),
                      {0: {'c': [], 'd': []},
                       2: {'c': ['C1', 'C2', 'C3'], 'd': ['D']}})
    self.assertEquals(e.GetComponentClasses('e1'), {'a', 'b'})
    self.assertEquals(e.GetComponentClasses('e2'), {'c', 'd'})
    self.assertEquals(e.GetFieldForComponent('c'), 'e2')
    self.assertEquals(e.GetFieldForComponent('x'), None)


class PatternTest(unittest.TestCase):
  def testExport(self):
    expr = [{'image_ids': [1, 2],
             'encoding_scheme': 'base32',
             'fields': [{'aaa': 1}, {'ccc': 2}]},
            {'image_ids': [3],
             'encoding_scheme': 'base8192',
             'fields': []}]
    pattern = Pattern(expr)
    self.assertEquals(Unordered(pattern.Export()), expr)

  def testGetImageId(self):
    expr = [{'image_ids': [1, 2],
             'encoding_scheme': 'base32',
             'fields': [{'aaa': 1}, {'ccc': 2}]},
            {'image_ids': [15],
             'encoding_scheme': 'base8192',
             'fields': []}]
    pattern = Pattern(expr)
    # pylint: disable=protected-access
    self.assertEquals(pattern._max_image_id, 2)

  def testSyntaxError(self):
    # missing "image_ids" field
    self.assertRaises(
        Exception, Pattern,
        [{'image_id': [3], 'encoding_scheme': 'base32', 'fields': []}])

    # extra field "extra"
    self.assertRaises(
        Exception, Pattern,
        [{'image_ids': [3], 'extra': 'xxx',
          'encoding_scheme': 'base32', 'fields': []}])
    self.assertRaises(
        Exception, Pattern,
        [{'image_ids': [], 'encoding_scheme': 'base32', 'fields': []}])

    # encoding scheme is either "base32" or "base8192"
    self.assertRaises(
        Exception, Pattern,
        [{'image_ids': [3], 'encoding_scheme': 'base31', 'fields': []}])

    self.assertRaises(
        Exception, Pattern,
        [{'image_ids': [3], 'encoding_scheme': 'base32',
          'fields': [{'aaa': -1}]}])

    # value of the "fields" field should be a list of dict of size 1
    self.assertRaises(
        Exception, Pattern,
        [{'image_ids': [3], 'encoding_scheme': 'base32',
          'fields': [{'aaa': 3, 'bbb': 4}]}])

  def testAddEmptyPattern(self):
    pattern = Pattern(
        [{'image_ids': [0], 'encoding_scheme': 'base32', 'fields': []}])

    pattern.AddEmptyPattern(2, 'base8192')
    self.assertEquals(
        Unordered(pattern.Export()),
        [{'image_ids': [0], 'encoding_scheme': 'base32', 'fields': []},
         {'image_ids': [2], 'encoding_scheme': 'base8192', 'fields': []}])
    self.assertEquals(pattern.GetEncodingScheme(), 'base8192')

    # Image id `2` already exists.
    self.assertRaises(HWIDException, pattern.AddEmptyPattern, 2, 'base8192')

  def testAddImageIdTo(self):
    pattern = Pattern(
        [{'image_ids': [0], 'encoding_scheme': 'base32', 'fields': []}])

    pattern.AddImageId(0, 3)
    self.assertEquals(
        Unordered(pattern.Export()),
        [{'image_ids': [0, 3], 'encoding_scheme': 'base32', 'fields': []}])

    # `reference_image_id` should exist.
    self.assertRaises(HWIDException, pattern.AddImageId, 2, 4)

    # New `image_id` already exists.
    self.assertRaises(HWIDException, pattern.AddImageId, 3, 0)

  def testAppendField(self):
    pattern = Pattern(
        [{'image_ids': [0], 'encoding_scheme': 'base32', 'fields': []}])

    pattern.AppendField('aaa', 3)
    pattern.AppendField('bbb', 0)
    pattern.AppendField('aaa', 1)
    self.assertEquals(
        Unordered(pattern.Export()),
        [{'image_ids': [0], 'encoding_scheme': 'base32',
          'fields': [{'aaa': 3}, {'bbb': 0}, {'aaa': 1}]}])

  def testGettingMethods(self):
    pattern = Pattern(
        [{'image_ids': [0], 'encoding_scheme': 'base32',
          'fields': [{'a': 3}, {'b': 0}, {'a': 1}, {'c': 5}]}])

    self.assertEquals(pattern.GetTotalBitLength(), 9)
    self.assertEquals(pattern.GetFieldsBitLength(), {'a': 4, 'b': 0, 'c': 5})
    self.assertEquals(pattern.GetBitMapping(),
                      [('a', 2), ('a', 1), ('a', 0),
                       ('a', 3),
                       ('c', 4), ('c', 3), ('c', 2), ('c', 1), ('c', 0)])
    self.assertEquals(pattern.GetBitMapping(max_bit_length=7),
                      [('a', 2), ('a', 1), ('a', 0),
                       ('a', 3),
                       ('c', 2), ('c', 1), ('c', 0)])


class RulesTest(unittest.TestCase):
  def testNormal(self):
    rules = Rules([{'name': 'verify.1',
                    'evaluate': 'a = 3',
                    'when': 'True'},
                   {'name': 'device_info.1',
                    'evaluate': ['a = 3', 'b = 5']},
                   {'name': 'verify.2',
                    'evaluate': 'c = 7',
                    'when': 'True',
                    'otherwise': 'False'}])

    self.assertEquals(len(rules.verify_rules), 2)
    self.assertEquals(rules.verify_rules[0].ExportToDict(),
                      {'name': 'verify.1', 'evaluate': 'a = 3', 'when': 'True'})
    self.assertEquals(rules.verify_rules[1].ExportToDict(),
                      {'name': 'verify.2', 'evaluate': 'c = 7',
                       'when': 'True', 'otherwise': 'False'})

    self.assertEquals(len(rules.device_info_rules), 1)
    self.assertEquals(rules.device_info_rules[0].ExportToDict(),
                      {'name': 'device_info.1', 'evaluate': ['a = 3', 'b = 5']})

  def testAddDeviceInfoRule(self):
    rules = Rules([])
    rules.AddDeviceInfoRule('rule1', 'eval1')
    rules.AddDeviceInfoRule('rule3', 'eval3')
    rules.AddDeviceInfoRule('rule2', 'eval2', position=1)
    rules.AddDeviceInfoRule('rule0', 'eval0', position=0)
    self.assertEquals(Unordered(rules.Export()),
                      [{'name': 'device_info.rule0', 'evaluate': 'eval0'},
                       {'name': 'device_info.rule1', 'evaluate': 'eval1'},
                       {'name': 'device_info.rule2', 'evaluate': 'eval2'},
                       {'name': 'device_info.rule3', 'evaluate': 'eval3'}])

  def testSyntaxError(self):
    self.assertRaises(Exception, Rules, 'abc')

    # Missing "name", "evaluate".
    self.assertRaises(Exception, Rules, [{'namr': '123'}])

    # The prefix of the value of name should be either "verify." or
    # "device_info."
    self.assertRaises(Exception, Rules, [{'name': 'xxx', 'evaluate': 'a'}])


if __name__ == '__main__':
  unittest.main()
