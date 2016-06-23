#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import unittest

import minijack_common  # pylint: disable=W0611
from minijack import db
from minijack.db import models


# Example models for test.
class FooModel(models.Model):
  field_i = models.IntegerField(primary_key=True)
  field_r = models.FloatField()
  field_t = models.TextField(db_index=True)


class FooChildModel(models.Model):
  field_i = models.IntegerField()
  field_t1 = models.TextField()
  nested_parent = FooModel
  # Not used, since BigQuery isn't tested.
  nested_name = 'child'


class BarModel(models.Model):
  key = models.IntegerField(primary_key=True, db_index=True)
  val = models.TextField()


class QueryTest(unittest.TestCase):

  def setUp(self):
    self.database = db.Database(':memory:')
    for i in xrange(1, 5):
      self.database.Insert(
          FooModel(field_i=i, field_r=i / 2.0, field_t='#%d' % (i % 2)))
    for j in xrange(1, 3):
      self.database.Insert(
          FooChildModel(field_i=2, field_t1='#2.%d' % j))
    texts = 'the quick brown fox jumps over a lazy dog'.split()
    for key, val in enumerate(texts, start=1):
      self.database.Insert(BarModel(key=key, val=val))

  def testValues(self):
    self.assertItemsEqual(
        [{'field_i': 1}, {'field_i': 2}, {'field_i': 3}, {'field_i': 4}],
        self.database(FooModel).Values('field_i').GetAll())
    self.assertItemsEqual(
        [{'field_r': 0.5, 'field_t': '#1'},
         {'field_r': 1.0, 'field_t': '#0'},
         {'field_r': 1.5, 'field_t': '#1'},
         {'field_r': 2.0, 'field_t': '#0'}],
        self.database(FooModel).Values('field_r', 'field_t').GetAll())

  def testValuesList(self):
    self.assertItemsEqual(
        [(0.5, '#1'), (1.0, '#0'), (1.5, '#1'), (2.0, '#0')],
        self.database(FooModel).ValuesList('field_r', 'field_t').GetAll())
    self.assertItemsEqual(
        [1, 2, 3, 4],
        self.database(FooModel).ValuesList('field_i', flat=True).GetAll())
    self.assertItemsEqual(
        ['#0', '#1'],
        self.database(FooModel).ValuesList('field_t', distinct=True).GetAll())

  def testOrderBy(self):
    self.assertEqual(
        ['#0', '#0', '#1', '#1'],
        self.database(FooModel).ValuesList('field_t', flat=True).OrderBy(
            'field_t').GetAll())
    self.assertEqual(
        ['#1', '#0', '#1', '#0'],
        self.database(FooModel).ValuesList('field_t', flat=True).OrderBy(
            'field_i').GetAll())
    self.assertEqual(
        [2.0, 1.5, 1.0, 0.5],
        self.database(FooModel).ValuesList('field_r', flat=True).OrderBy(
            '-field_i').GetAll())
    self.assertEqual(
        [0.5, 1.5, 1.0, 2.0],
        self.database(FooModel).ValuesList('field_r', flat=True).OrderBy(
            '-field_t', 'field_i').GetAll())

  def testFilter(self):
    self.assertItemsEqual(
        [1, 3],
        self.database(FooModel).Filter(field_t='#1').ValuesList(
            'field_i', flat=True).GetAll())
    self.assertItemsEqual(
        [1],
        self.database(FooModel).Filter(field_t='#1', field_r=0.5).ValuesList(
            'field_i', flat=True).GetAll())
    self.assertItemsEqual(
        [1],
        self.database(FooModel).Filter(field_t='#1').Filter(
            field_r=0.5).ValuesList('field_i', flat=True).GetAll())
    self.assertItemsEqual(
        [1],
        self.database(FooModel).Filter(field_t='#1', field_i__lt=2).ValuesList(
            'field_i', flat=True).GetAll())
    self.assertItemsEqual(
        [3, 4],
        self.database(FooModel).Filter(field_i__gt=2).ValuesList(
            'field_i', flat=True).GetAll())
    self.assertItemsEqual(
        [1],
        self.database(FooModel).Filter(field_i__lt=2).ValuesList(
            'field_i', flat=True).GetAll())
    self.assertItemsEqual(
        [2, 3, 4],
        self.database(FooModel).Filter(field_i__gte=2).ValuesList(
            'field_i', flat=True).GetAll())
    self.assertItemsEqual(
        [1, 2],
        self.database(FooModel).Filter(field_i__lte=2).ValuesList(
            'field_i', flat=True).GetAll())
    self.assertItemsEqual(
        [1, 4],
        self.database(BarModel).Filter(val__in=['the', 'fox']).ValuesList(
            'key', flat=True).GetAll())
    self.assertItemsEqual(
        [4, 9],
        self.database(BarModel).Filter(val__regex='^.o.$').ValuesList(
            'key', flat=True).GetAll())
    self.assertItemsEqual(
        [3, 4],
        self.database(BarModel).Filter(val__regex='^(br|f)o[n-z]+$').ValuesList(
            'key', flat=True).GetAll())
    self.assertItemsEqual(
        [5],
        self.database(BarModel).Filter(val__contains='um').ValuesList(
            'key', flat=True).GetAll())
    self.assertItemsEqual(
        [1],
        self.database(BarModel).Filter(val__startswith='th').ValuesList(
            'key', flat=True).GetAll())
    self.assertItemsEqual(
        [2],
        self.database(BarModel).Filter(val__endswith='ck').ValuesList(
            'key', flat=True).GetAll())
    self.assertItemsEqual(
        [],
        self.database(BarModel).Filter(val__startswith='u').ValuesList(
            'key', flat=True).GetAll())
    self.assertItemsEqual(
        [],
        self.database(BarModel).Filter(val__endswith='u').ValuesList(
            'key', flat=True).GetAll())

  def testExclude(self):
    self.assertItemsEqual(
        [2, 4],
        self.database(FooModel).Exclude(field_t='#1').ValuesList(
            'field_i', flat=True).GetAll())
    self.assertItemsEqual(
        [2, 3, 4],
        self.database(FooModel).Exclude(field_t='#1', field_r=0.5).ValuesList(
            'field_i', flat=True).GetAll())
    self.assertItemsEqual(
        [2, 4],
        self.database(FooModel).Exclude(field_t='#1').Exclude(
            field_r=0.5).ValuesList('field_i', flat=True).GetAll())
    self.assertItemsEqual(
        [3],
        self.database(FooModel).Filter(field_t='#1').Exclude(
            field_r=0.5).ValuesList('field_i', flat=True).GetAll())
    self.assertItemsEqual(
        [3],
        self.database(FooModel).Exclude(field_r=0.5).Filter(
            field_t='#1').ValuesList('field_i', flat=True).GetAll())

  def testJoin(self):
    subquery = self.database(FooModel).Filter(field_t='#1')
    query = self.database(BarModel).Join(
        subquery, key='field_i').ValuesList('val', flat=True)
    self.assertItemsEqual(['the', 'brown'], query.GetAll())

  def testAnnotate(self):
    self.assertItemsEqual(
        [{'field_t': '#0', 'max_i': 4}, {'field_t': '#1', 'max_i': 3}],
        self.database(FooModel).Values('field_t').Annotate(
            max_i=('max', 'field_i')).GetAll())
    self.assertItemsEqual(
        [{'field_t': '#0', 'avg_i': 3.0}, {'field_t': '#1', 'avg_i': 2.0}],
        self.database(FooModel).Values('field_t').Annotate(
            avg_i=('avg', 'field_i')).GetAll())

  def testIterFilterIn(self):
    self.assertItemsEqual(
        self.database(FooModel).Values('field_t', 'field_r').Filter(
            field_i__in=[1, 3, 4]).GetAll(),
        list(self.database(FooModel).Values('field_t', 'field_r').IterFilterIn(
            'field_i', [1, 3, 4])))

  def testQ(self):
    Q = self.database.Q
    self.assertItemsEqual(
        ['the', 'brown', 'fox'],
        self.database(BarModel).ValuesList('val', flat=True).Filter(
            ~Q(key__gt=5) & (Q(val__contains='o') | Q(val='the'))
        ).GetAll())

  def testDeepCopy(self):
    query = self.database(FooModel).ValuesList('field_i', flat=True).Filter(
        field_r__gt=1.2)
    query2 = copy.deepcopy(query)
    query.Filter(field_i__lte=3)
    self.assertItemsEqual(query.GetAll(), [3])
    self.assertItemsEqual(query2.GetAll(), [3, 4])

  def testGetRelated(self):
    foo1 = self.database(FooModel).Filter(field_i=1).GetOne()
    foo2 = self.database(FooModel).Filter(field_i=2).GetOne()
    self.assertItemsEqual([], self.database.GetRelated(FooChildModel, foo1))
    self.assertItemsEqual(
        ['#2.1', '#2.2'],
        [c.field_t1 for c in self.database.GetRelated(FooChildModel, foo2)])

  def tearDown(self):
    self.database.Close()


if __name__ == '__main__':
  unittest.main()
