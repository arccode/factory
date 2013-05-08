#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.minijack import db
from cros.factory.minijack.db import models


# Example models for test.
class FooModel(models.Model):
  field_i = models.IntegerField(primary_key=True)
  field_r = models.RealField()
  field_t = models.TextField()


class BarModel(models.Model):
  key1 = models.TextField(primary_key=True)
  key2 = models.TextField(primary_key=True)
  val1 = models.TextField()
  val2 = models.IntegerField()
  val3 = models.RealField()


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

    # Verify the tables exist by querying the sqlite_master table.
    executor_factory = self.database.GetExecutorFactory()
    executor = executor_factory.NewExecutor()
    executor.Execute('SELECT name FROM sqlite_master WHERE type = "table"')
    results = executor.FetchAll()
    self.assertItemsEqual([('FooModel',), ], results)

    # Verify the DoesTableExist method.
    self.assertTrue(self.database.DoesTableExist(FooModel))
    self.assertFalse(self.database.DoesTableExist(BarModel))

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

    # Verify the VerifySchema method.
    self.assertTrue(self.database.VerifySchema(FooModel))
    self.assertFalse(self.database.VerifySchema(BarModel))

  # Define the same FooModel but has a different field type for testWrongSchema.
  class FooModel(models.Model):
    field_i = models.TextField(primary_key=True)  # Used to be IntegerField
    field_r = models.RealField()
    field_t = models.TextField()

  def testWrongSchema(self):
    self.database.GetOrCreateTable(FooModel)
    self.assertFalse(self.database.VerifySchema(DatabaseTest.FooModel))

  def testInsert(self):
    self.database.Insert(FooModel(field_i=56, field_t='Five Six'))

    # Verify the table content by querying the table.
    executor_factory = self.database.GetExecutorFactory()
    executor = executor_factory.NewExecutor()
    executor.Execute('SELECT * FROM FooModel')
    result = executor.FetchOne()
    self.assertItemsEqual((56, 0.0, 'Five Six'), result)

  def testUpdate(self):
    self.database.Insert(FooModel(field_i=56, field_t='Five Six'))
    self.database.Update(FooModel(field_i=56, field_r=5.6))

    # Verify the table content by querying the table.
    executor_factory = self.database.GetExecutorFactory()
    executor = executor_factory.NewExecutor()
    executor.Execute('SELECT * FROM FooModel')
    result = executor.FetchOne()
    self.assertItemsEqual((56, 5.6, 'Five Six'), result)

  def testCheckExists(self):
    self.database.Insert(FooModel(field_i=56, field_t='Five Six'))
    self.assertTrue(self.database.CheckExists(FooModel(field_i=56)))
    self.assertFalse(self.database.CheckExists(FooModel(field_i=78)))

  def testGetOne(self):
    self.database.Insert(FooModel(field_i=56, field_t='Five Six'))
    self.database.Insert(FooModel(field_i=78, field_r=7.8))
    row = self.database.GetOne(FooModel(field_i=78))
    self.assertDictEqual({
      'field_i': 78,
      'field_r': 7.8,
      'field_t': '',
    }, row.GetFields())
    # Get not-matched.
    self.assertIs(None, self.database.GetOne(FooModel(field_i=34)))

  def testGetAll(self):
    self.database.Insert(FooModel(field_i=56, field_t='Five Six'))
    self.database.Insert(FooModel(field_i=78, field_r=7.8))
    # Get all rows.
    rows = self.database.GetAll(FooModel())
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
    rows = self.database.GetAll(FooModel(field_i=78))
    self.assertEqual(1, len(rows))
    # Get not-matched.
    rows = self.database.GetAll(FooModel(field_i=90))
    self.assertEqual(0, len(rows))

  def testDeleteAll(self):
    row_a = FooModel(field_i=111, field_t='One')
    row_b = FooModel(field_i=222, field_r=1.23)
    row_c = FooModel(field_i=333, field_r=1.23)
    self.database.InsertMany([row_a, row_b, row_c])
    self.assertTrue(self.database.CheckExists(row_a))
    self.assertTrue(self.database.CheckExists(row_b))
    self.assertTrue(self.database.CheckExists(row_c))

    condition = FooModel(field_r=1.23)
    self.database.DeleteAll(condition)
    self.assertTrue(self.database.CheckExists(row_a))
    self.assertFalse(self.database.CheckExists(row_b))
    self.assertFalse(self.database.CheckExists(row_c))

    # Delete all rows, no condition given.
    condition = FooModel()
    self.database.DeleteAll(condition)
    self.assertFalse(self.database.CheckExists(row_a))

  def testUpdateOrInsertRow(self):
    self.database.UpdateOrInsert(FooModel(field_i=56, field_t='Five Six'))
    self.database.UpdateOrInsert(FooModel(field_i=78, field_r=7.8))
    self.database.UpdateOrInsert(FooModel(field_i=56, field_r=5.6))
    rows = self.database.GetAll(FooModel())
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
      self.database.UpdateOrInsert(FooModel(field_r=3.4, field_t='Three Four'))

  def testFetchBeforeExecute(self):
    self.database.GetOrCreateTable(FooModel)
    executor_factory = self.database.GetExecutorFactory()
    executor = executor_factory.NewExecutor()
    result = executor.FetchOne()
    self.assertIs(None, result)
    results = executor.FetchAll()
    self.assertEqual([], results)

  def tearDown(self):
    self.database.Close()


if __name__ == "__main__":
  unittest.main()
