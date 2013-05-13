#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.db import models


# Example models for test.
class FooModel(models.Model):
  field_i = models.IntegerField(primary_key=True)
  field_r = models.FloatField()
  field_t = models.TextField()


class BarModel(models.Model):
  key1 = models.TextField(primary_key=True)
  key2 = models.TextField(primary_key=True)
  val1 = models.TextField()
  val2 = models.IntegerField()
  val3 = models.FloatField()


class ModelTest(unittest.TestCase):
  def setUp(self):
    self.foo_model = FooModel(field_i=5, field_r=3.0, field_t='foo_model')
    self.bar_model = BarModel(key1='KEY1', key2='KEY2')

  def testGetModelName(self):
    # GetModelName() is a class method.
    self.assertEqual('FooModel', FooModel.GetModelName())
    self.assertEqual('BarModel', self.bar_model.GetModelName())

  def testGetDbSchema(self):
    # GetDbSchema() is a class method.
    self.assertDictEqual({
      'field_i': 'INTEGER',
      'field_r': 'REAL',
      'field_t': 'TEXT',
    }, FooModel.GetDbSchema())
    self.assertDictEqual({
      'key1': 'TEXT',
      'key2': 'TEXT',
      'val1': 'TEXT',
      'val2': 'INTEGER',
      'val3': 'REAL',
    }, self.bar_model.GetDbSchema())

  def testGetPrimaryKey(self):
    # GetPrimaryKey() is a class method.
    self.assertItemsEqual(FooModel.GetPrimaryKey(), ['field_i'])
    self.assertItemsEqual(self.bar_model.GetPrimaryKey(), ['key1', 'key2'])

  def testIsValid(self):
    # IsValid() is a class method.
    self.assertTrue(FooModel.IsValid(self.foo_model))
    self.assertFalse(FooModel.IsValid(self.bar_model))

  def testGetFields(self):
    self.assertDictEqual({
      'field_i': 5,
      'field_r': 3.0,
      'field_t': 'foo_model',
    }, self.foo_model.GetFields())
    self.assertDictEqual({
      'key1': 'KEY1',
      'key2': 'KEY2',
      'val1': '',
      'val2': 0,
      'val3': 0.0,
    }, self.bar_model.GetFields())

  def testGetFieldNames(self):
    # GetFieldNames() is a class method.
    self.assertItemsEqual(('field_i', 'field_r', 'field_t'),
                          FooModel.GetFieldNames())
    self.assertItemsEqual(('key1', 'key2', 'val1', 'val2', 'val3'),
                          self.bar_model.GetFieldNames())

  def testGetFieldValues(self):
    self.assertItemsEqual(('KEY1', 'KEY2', '', 0, 0.0),
                          self.bar_model.GetFieldValues())

  def testGetNonEmptyFields(self):
    self.assertDictEqual({
      'key1': 'KEY1',
      'key2': 'KEY2',
    }, self.bar_model.GetNonEmptyFields())

  def testGetNonEmptyFieldNames(self):
    self.assertItemsEqual(('key1', 'key2'),
                          self.bar_model.GetNonEmptyFieldNames())

  def testGetNonEmptyFieldValues(self):
    self.assertItemsEqual(('KEY1', 'KEY2'),
                          self.bar_model.GetNonEmptyFieldValues())

  def testCloneOnlyPrimaryKey(self):
    self.assertDictEqual({
      'field_i': 5,
      'field_r': 0.0,
      'field_t': '',
    }, self.foo_model.CloneOnlyPrimaryKey().GetFields())

  def testInitFromTuple(self):
    new_foo_model = FooModel(self.foo_model.GetFieldValues())
    self.assertDictEqual(self.foo_model.GetFields(),
                         new_foo_model.GetFields())

  def testToModelSubclass(self):
    self.assertIs(models.ToModelSubclass(self.foo_model), FooModel)
    self.assertIs(models.ToModelSubclass(FooModel), FooModel)


if __name__ == "__main__":
  unittest.main()
