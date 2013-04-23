#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.minijack import db

# Example models for test.
class FooModel(db.Model):
  field_i = db.IntegerField(primary_key=True)
  field_r = db.RealField()
  field_t = db.TextField()

class BarModel(db.Model):
  key1 = db.TextField(primary_key=True)
  key2 = db.TextField(primary_key=True)
  val1 = db.TextField()
  val2 = db.IntegerField()
  val3 = db.RealField()

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
    self.assertIs(db.ToModelSubclass(self.foo_model), FooModel)
    self.assertIs(db.ToModelSubclass(FooModel), FooModel)

class DatabaseTest(unittest.TestCase):
  def setUp(self):
    self.database = db.Database()
    self.database.Init(':memory:')

  def testGetOrCreateTable(self):
    foo_table = self.database.GetOrCreateTable(FooModel)
    foo_table_by_name = self.database.GetOrCreateTable('FooModel')
    self.assertIs(foo_table, foo_table_by_name)

    bar_table = self.database.GetOrCreateTable(BarModel)
    bar_table_by_instance = self.database.GetOrCreateTable(BarModel())
    self.assertIs(bar_table, bar_table_by_instance)
    self.assertIsNot(foo_table, bar_table)

    with self.assertRaises(db.DatabaseException):
      self.database.GetOrCreateTable('NotExist')

  def testTableExists(self):
    self.database.GetOrCreateTable(FooModel)
    self.database.GetOrCreateTable(BarModel)

    # Verify the tables exist by querying the sqlite_master table.
    executor_factory = self.database.GetExecutorFactory()
    executor = executor_factory.NewExecutor()
    executor.Execute('SELECT name FROM sqlite_master WHERE type = "table"')
    results = executor.FetchAll()
    self.assertItemsEqual([('FooModel',), ('BarModel',)], results)

  def testTableSchema(self):
    self.database.GetOrCreateTable(FooModel)

    # Verify the table schema by querying the sqlite_master table.
    executor_factory = self.database.GetExecutorFactory()
    executor = executor_factory.NewExecutor()
    executor.Execute('SELECT sql FROM sqlite_master '
                     'WHERE type = "table" AND name = "FooModel"')
    (sql,) = executor.FetchOne()
    pattern = 'CREATE TABLE FooModel \( (.*), PRIMARY KEY \( (.*) \) \)'
    self.assertRegexpMatches(sql, pattern)
    matches = re.match(pattern, sql)
    self.assertItemsEqual(['field_i INTEGER', 'field_r REAL', 'field_t TEXT'],
                          matches.group(1).split(', '))
    self.assertItemsEqual(['field_i'],
                          matches.group(2).split(', '))

  def testInsertRow(self):
    foo_table = self.database.GetOrCreateTable(FooModel)
    foo_table.InsertRow(FooModel(field_i=56, field_t='Five Six'))

    # Verify the table content by querying the table.
    executor_factory = self.database.GetExecutorFactory()
    executor = executor_factory.NewExecutor()
    executor.Execute('SELECT * FROM FooModel')
    result = executor.FetchOne()
    self.assertItemsEqual((56, None, 'Five Six'), result)

  def testUpdateRow(self):
    foo_table = self.database.GetOrCreateTable(FooModel)
    foo_table.InsertRow(FooModel(field_i=56, field_t='Five Six'))
    foo_table.UpdateRow(FooModel(field_i=56, field_r=5.6))

    # Verify the table content by querying the table.
    executor_factory = self.database.GetExecutorFactory()
    executor = executor_factory.NewExecutor()
    executor.Execute('SELECT * FROM FooModel')
    result = executor.FetchOne()
    self.assertItemsEqual((56, 5.6, 'Five Six'), result)

  def testDoesRowExists(self):
    foo_table = self.database.GetOrCreateTable(FooModel)
    foo_table.InsertRow(FooModel(field_i=56, field_t='Five Six'))
    self.assertTrue(foo_table.DoesRowExist(FooModel(field_i=56)))
    self.assertFalse(foo_table.DoesRowExist(FooModel(field_i=78)))

  def testGetOneRow(self):
    foo_table = self.database.GetOrCreateTable(FooModel)
    foo_table.InsertRow(FooModel(field_i=56, field_t='Five Six'))
    foo_table.InsertRow(FooModel(field_i=78, field_r=7.8))
    row = foo_table.GetOneRow(FooModel(field_i=78))
    self.assertDictEqual({
      'field_i': 78,
      'field_r': 7.8,
      'field_t': '',
    }, row.GetFields())
    # Get not-matched.
    self.assertIs(None, foo_table.GetOneRow(FooModel(field_i=34)))

  def testGetRows(self):
    foo_table = self.database.GetOrCreateTable(FooModel)
    foo_table.InsertRow(FooModel(field_i=56, field_t='Five Six'))
    foo_table.InsertRow(FooModel(field_i=78, field_r=7.8))
    # Get all rows.
    rows = foo_table.GetRows(FooModel())
    self.assertEqual(2, len(rows))
    self.assertDictEqual({
      'field_i': 56,
      'field_r': 0.0,
      'field_t': 'Five Six',
    }, rows[0].GetFields())
    self.assertDictEqual({
      'field_i': 78,
      'field_r': 7.8,
      'field_t': '',
    }, rows[1].GetFields())
    # Get one row matched.
    rows = foo_table.GetRows(FooModel(field_i=78))
    self.assertEqual(1, len(rows))
    # Get not-matched.
    rows = foo_table.GetRows(FooModel(field_i=90))
    self.assertEqual(0, len(rows))

  def testUpdateOrInsertRow(self):
    foo_table = self.database.GetOrCreateTable(FooModel)
    foo_table.UpdateOrInsertRow(FooModel(field_i=56, field_t='Five Six'))
    foo_table.UpdateOrInsertRow(FooModel(field_i=78, field_r=7.8))
    foo_table.UpdateOrInsertRow(FooModel(field_i=56, field_r=5.6))
    rows = foo_table.GetRows(FooModel())
    self.assertEqual(2, len(rows))
    self.assertDictEqual({
      'field_i': 56,
      'field_r': 5.6,
      'field_t': 'Five Six',
    }, rows[0].GetFields())
    self.assertDictEqual({
      'field_i': 78,
      'field_r': 7.8,
      'field_t': '',
    }, rows[1].GetFields())
    # Update or insert a row without a primary key.
    with self.assertRaises(db.DatabaseException):
      foo_table.UpdateOrInsertRow(FooModel(field_r=3.4, field_t='Three Four'))

  def tearDown(self):
    self.database.Close()

if __name__ == "__main__":
  unittest.main()
