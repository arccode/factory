#!/usr/bin/env python2
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import os
import shelve
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import shelve_utils


def WipeFiles(parent_dir):
  """Clear all files in a directory."""
  for f in os.listdir(parent_dir):
    path = os.path.join(parent_dir, f)
    if os.path.isfile(path):
      open(path, 'w').close()


class ShelveUtilsTest(unittest.TestCase):

  def setUp(self):
    # Use a whole temp directory, since some DB mechanisms use multiple files.
    self.tmp = tempfile.mkdtemp(prefix='shelve_utils_unittest.')
    self.shelf_path = os.path.join(self.tmp, 'shelf')

  def tearDown(self):
    shutil.rmtree(self.tmp)

  def testIsShelfValid(self):
    shelf = shelve.open(self.shelf_path, 'c')
    shelf['FOO'] = 'BAR'
    del shelf

    self.assertTrue(shelve_utils.IsShelfValid(self.shelf_path))
    self.assertTrue(shelve_utils.BackupShelfIfValid(self.shelf_path))

    # Corrupt the shelf by clearing all files in the temp directory.
    WipeFiles(self.tmp)

    self.assertFalse(shelve_utils.IsShelfValid(self.shelf_path))
    self.assertFalse(shelve_utils.BackupShelfIfValid(self.shelf_path))

    # No worries, we have a backup!
    shelf = shelve_utils.OpenShelfOrBackup(self.shelf_path)
    self.assertEquals('BAR', shelf['FOO'])
    shelf['FOO'] = 'BAZ'
    del shelf

    # Open and close the shelf with OpenShelfOrBackup.  Now 'BAZ' should
    # be backed up.
    shelve_utils.OpenShelfOrBackup(self.shelf_path).close()
    self.assertTrue(shelve_utils.IsShelfValid(self.shelf_path))
    WipeFiles(self.tmp)
    self.assertFalse(shelve_utils.IsShelfValid(self.shelf_path))
    shelf = shelve_utils.OpenShelfOrBackup(self.shelf_path)
    self.assertEquals('BAZ', shelf['FOO'])

  def testIsShelfValid_Nonexistent(self):
    self.assertFalse(shelve_utils.IsShelfValid(self.shelf_path))
    self.assertFalse(shelve_utils.BackupShelfIfValid(self.shelf_path))

  def testIsShelfValid_EmptyFile(self):
    open(self.shelf_path, 'w').close()
    self.assertFalse(shelve_utils.IsShelfValid(self.shelf_path))
    self.assertFalse(shelve_utils.BackupShelfIfValid(self.shelf_path))

  def testIsShelfValid_Corrupt(self):
    # This corrupt gdbm database causes the process to abort entirely.
    path = os.path.join(os.path.dirname(__file__),
                        'testdata', 'corrupt-gdbm-shelf')
    self.assertTrue(os.path.exists(path))
    self.assertFalse(shelve_utils.IsShelfValid(path))
    self.assertFalse(shelve_utils.BackupShelfIfValid(path))


class DictShelveViewTest(unittest.TestCase):

  def setUp(self):
    self.shelf = shelve_utils.InMemoryShelf()
    self.shelf_view = shelve_utils.DictShelfView(self.shelf)

  def testSetValueAndGetValue(self):
    self.shelf_view.SetValue('a.b.c', 1)
    self.assertEqual(self.shelf_view.GetValue('a.b.c'), 1)
    self.assertEqual(self.shelf_view.GetValue('a.b'), {'c': 1})
    self.assertEqual(self.shelf_view.GetValue('a'), {'b': {'c': 1}})
    self.shelf_view.SetValue('a.b.c', 2)
    self.assertEqual(self.shelf_view.GetValue('a.b.c'), 2)
    self.assertEqual(self.shelf_view.GetValue('a.b'), {'c': 2})
    self.assertEqual(self.shelf_view.GetValue('a'), {'b': {'c': 2}})

    self.shelf_view.Clear()
    self.shelf_view.SetValue('a.b.c.d', 3)
    self.shelf_view.SetValue('a.b', {})
    self.assertFalse(self.shelf_view.HasKey('a.b.c.d'))
    self.assertFalse(self.shelf_view.HasKey('a.b.c'))
    self.assertFalse(self.shelf_view.HasKey('a.b'))
    self.assertFalse(self.shelf_view.HasKey('a'))
    self.assertFalse(self.shelf_view.GetKeys())

    self.shelf_view.Clear()
    self.shelf_view.SetValue('', {'a': 1, 'b': {'c': 2, 'd': 3}})
    self.assertEqual(self.shelf_view.GetValue('a'), 1)
    self.assertEqual(self.shelf_view.GetValue('b.c'), 2)
    self.assertEqual(self.shelf_view.GetValue('b.d'), 3)
    self.assertEqual(self.shelf_view.GetValue('b'), {'c': 2, 'd': 3})
    self.assertEqual(self.shelf_view.GetValue(''),
                     {'a': 1, 'b': {'c': 2, 'd': 3}})

    self.shelf_view.Clear()
    self.shelf_view.SetValue('a', 0)
    self.shelf_view.SetValue('a.b', 1)
    self.shelf_view.SetValue('a.b.c', 2)
    self.assertItemsEqual(['a.b.c'], self.shelf_view.GetKeys())

  def testGetKeys(self):
    self.shelf_view.SetValue('a.b', {'c': 1, 'd': 2})
    self.assertItemsEqual(['a.b.c', 'a.b.d'], self.shelf_view.GetKeys())

  def testDeleteKeys(self):
    # delete everything
    self.shelf_view.SetValue('', {'a': 1, 'b': {'c': 2, 'd': 3}})
    self.shelf_view.DeleteKeys(['a', 'b', 'b.c', 'b.d'])
    self.assertFalse(self.shelf_view.GetKeys())

    self.shelf_view.Clear()

    # ignore KeyError if optional=True
    self.shelf_view.SetValue('', {'a': 1, 'b': {'c': 2, 'd': 3}})
    self.shelf_view.DeleteKeys(['a', 'b.c.d', 'b.d'], optional=True)
    self.assertEqual(self.shelf_view.GetValue(''), {'b': {'c': 2}})

    self.shelf_view.Clear()

    self.shelf_view.SetValue('a.b.c', 1)
    self.shelf_view.DeleteKeys(['a.b'])
    self.assertFalse(self.shelf_view.GetKeys())
    with self.assertRaises(KeyError):
      # since there is nothing under 'a', so a is deleted as well.
      self.shelf_view.DeleteKeys(['a'])

    self.shelf_view.Clear()
    self.shelf_view.SetValue('a.b', 1)
    with self.assertRaises(KeyError):
      self.shelf_view.DeleteKeys(['a', 'a.b.c'])
    self.assertItemsEqual([], self.shelf_view.GetKeys())

  def testGetChildren(self):
    self.shelf_view.SetValue('', {'a': 1, 'b': {'c': 2, 'd': 3}})
    self.assertItemsEqual(self.shelf_view.GetChildren(''), ['a', 'b'])


class DictKeyUnittest(unittest.TestCase):
  def testJoin(self):
    self.assertEqual('a.b.c', shelve_utils.DictKey.Join('a', 'b', 'c'))
    self.assertEqual('a.b.c', shelve_utils.DictKey.Join('a', 'b.c'))
    self.assertEqual('a.b.c', shelve_utils.DictKey.Join('a.b', 'c'))
    self.assertEqual('a.b.c', shelve_utils.DictKey.Join('', 'a', 'b', 'c'))
    self.assertEqual('a.c', shelve_utils.DictKey.Join('', 'a', '', 'c'))

  def testGetBasename(self):
    self.assertEqual('c', shelve_utils.DictKey.GetBasename('a.b.c'))
    self.assertEqual('c', shelve_utils.DictKey.GetBasename('c'))
    self.assertEqual('', shelve_utils.DictKey.GetBasename(''))

  def testGetParent(self):
    self.assertEqual('a.b', shelve_utils.DictKey.GetParent('a.b.c'))
    self.assertEqual('', shelve_utils.DictKey.GetParent('c'))
    self.assertEqual('', shelve_utils.DictKey.GetParent(''))

  def testSplit(self):
    self.assertEqual(('a.b', 'c'), shelve_utils.DictKey.Split('a.b.c'))
    self.assertEqual(('', 'c'), shelve_utils.DictKey.Split('c'))
    self.assertEqual(('', ''), shelve_utils.DictKey.Split(''))

  def testIsAncestor(self):
    self.assertTrue(shelve_utils.DictKey.IsAncestor('a', 'a.b.c'))
    self.assertTrue(shelve_utils.DictKey.IsAncestor('', 'a.b.c'))
    self.assertTrue(shelve_utils.DictKey.IsAncestor('a.b.c', 'a.b.c'))
    self.assertTrue(shelve_utils.DictKey.IsAncestor('', ''))

    self.assertFalse(shelve_utils.DictKey.IsAncestor('a.b.c', 'a.b'))
    self.assertFalse(shelve_utils.DictKey.IsAncestor('a.b', 'a.d'))
    self.assertFalse(shelve_utils.DictKey.IsAncestor('a.b', ''))


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
