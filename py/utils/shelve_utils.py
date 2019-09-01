# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import glob
import logging
import os
import shelve
import shutil

from . import file_utils
from . import process_utils


BACKUP_DIRECTORY = 'backup'


class RecoveryException(Exception):
  pass


def IsShelfValid(shelf):
  """Checks whether a shelf can be loaded and unshelved.

  This is done in a separate process, since some databases (like gdbm)
  may throw fatal errors if the shelf is not valid.

  Returns:
    True if valid, False if not valid.
  """
  process = process_utils.Spawn(['python2', '-c',
                                 'import factory_common, shelve, sys; '
                                 'shelve.open(sys.argv[1], "r").items(); '
                                 r'print "\nSHELF OK"',
                                 os.path.realpath(shelf)],
                                cwd=os.path.dirname(__file__), call=True,
                                log=True, read_stdout=True, read_stderr=True)
  if process.returncode == 0 and process.stdout_data.endswith('SHELF OK\n'):
    return True

  logging.warn('Unable to validate shelf %r: '
               'returncode=%r, stdout=%r, stderr=%r',
               shelf, process.returncode,
               process.stdout_data, process.stderr_data)
  return False


def FindShelfFiles(shelf):
  """Returns all files in shelf.

  We assume this to be files that have the same name as the shelf, or
  the shelf plus dot and a suffix."""
  shelf_files = glob.glob(shelf + '.*')
  if os.path.exists(shelf):
    shelf_files.append(shelf)
  return shelf_files


def BackupShelfIfValid(shelf):
  """Validates a shelf, and backs it up if it is valid.

  Files that have the same name as the shelf, or the shelf plus dot and a
  suffix, are backed up.

  Returns:
    True if the shelf was valid and is backed up.
  """
  shelf_files = FindShelfFiles(shelf)
  if not shelf_files:
    # Nothing to back up.
    logging.info('Shelf %s not present; not backing up', shelf)
    return False

  if not IsShelfValid(shelf):
    logging.warn('Shelf %s is invalid; not backing up', shelf)
    return False

  backup_dir = os.path.join(os.path.dirname(shelf), BACKUP_DIRECTORY)
  file_utils.TryMakeDirs(backup_dir)
  logging.info('Backing up %s to %s', shelf_files, backup_dir)
  for f in shelf_files:
    shutil.copyfile(f, os.path.join(backup_dir, os.path.basename(f)))
  return True


def RecoverShelf(shelf):
  """Recovers a shelf from its backup.

  Raises:
    RecoveryException if unable to recover and validate the shelf.
  """
  backup_shelf = os.path.join(os.path.dirname(shelf),
                              BACKUP_DIRECTORY,
                              os.path.basename(shelf))

  # Validate the backup
  if not IsShelfValid(backup_shelf):
    raise IOError('Backup shelf %s is invalid or missing' % backup_shelf)

  shelf_files = FindShelfFiles(backup_shelf)
  assert shelf_files

  for f in shelf_files:
    dest_path = os.path.join(os.path.dirname(shelf),
                             os.path.basename(f))
    logging.info('Recovering %s to %s', f, dest_path)
    shutil.copyfile(f, dest_path)


def OpenShelfOrBackup(shelf, flag='c', protocol=None, writeback=False):
  """Opens a shelf, or its backup if invalid.

  If the shelf is valid, it is backed up.

  Args:
    shelf: Path to the shelf.
    Other arguments: See shelve.open.
  """
  if not FindShelfFiles(shelf) and flag in ['c', 'n']:
    # No worries; just create a new shelf.
    pass
  elif BackupShelfIfValid(shelf):
    # The shelf is valid.
    pass
  else:
    # Attempt to recover the shelf, throwing an exception if we can't.
    RecoverShelf(shelf)
    # At this point the shelf is guaranteed to be valid.

  return shelve.open(shelf, flag, protocol, writeback)


class DictShelfView(object):
  """Wrapper for shelf.

  Turns a shelf object into recursive dictionary data structure.
  For example::

    shelf_view.SetValue('a.b.c', True)
    assert shelf_view.GetChildren('a') == ['b']
    assert shelf_view.GetChildren('a.b') == ['c']

  Key used in shelf is treated as a path on tree that seperated by dot ('.').
  """
  def __init__(self, shelf):
    """Constructor

    Args
      :type shelf: shelve.Shelf
    """
    self._shelf = shelf
    self._cached_children = {}
    self._InitCache()

  def GetValue(self, key, optional=False):
    """Retrives a shared data item, recursively.

    For example::
      shelf_view.SetValue('a.b.c', 1)
      assert shelf_view.GetValue('a') == {'b': {'c': 1}}
    Args:
      key: The key whose value to retrieve.
      optional: True to return None if not found; False to raise a KeyError.
    """
    if key not in self._cached_children:
      if optional:
        return None
      else:
        raise KeyError(key)

    def walk(path):
      children = self._cached_children[path]
      if children:
        retval = {}
        for c in children:
          retval[c] = walk(DictKey.Join(path, c))
        return retval
      return self._shelf[path]
    return walk(key)

  def SetValue(self, key, value, sync=True):
    """Set key with value. `d[key] = value`

    Args:
      key: key that will be replaced.
      value: new value.
    """
    if self.HasKey(key):
      self._DeleteOneKey(key)

    def _SetValue(key, value):
      if isinstance(value, collections.Mapping):
        for k in value:
          _SetValue(DictKey.Join(key, k), value[k])
      else:
        self._AddCache(key)
        self._shelf[key] = value

    _SetValue(key, value)
    if sync:
      self._shelf.sync()

  def UpdateValue(self, key, value, sync=True):
    def _UpdateValue(key, value):
      if isinstance(value, collections.Mapping):
        for k in value:
          _UpdateValue(DictKey.Join(key, k), value[k])
      else:
        self.SetValue(key, value, sync=False)

    _UpdateValue(key, value)
    if sync:
      self._shelf.sync()

  def DeleteKeys(self, keys, optional=False):
    """Delete each key in `keys`, recursively.

    For example::
      shelf_view.SetValue('a.b.c', 1)
      shelf_view.SetValue('a.b.d', 1)
      shelf_view.DeleteKeys(['a'])  # shelf will become empty

    If there are keys cannot be found in shelf, a KeyError exception will be
    raised for those keys, but other keys which are valid will be deleted first.
    """
    # sort keys, so we will always delete children before deleting parent.
    keys.sort(reverse=True)
    last_deleted_key = None
    invalid_keys = set()

    for key in keys:
      # trying to delete a key which is ancestor of previous deleted key.
      try:
        self._DeleteOneKey(key)
      except KeyError:
        # if key is ancestor of last deleted key, it is possible that current
        # key is invalid now (because last deleted key is the last descendant).
        if not (last_deleted_key is not None and
                DictKey.IsAncestor(key, last_deleted_key)):
          invalid_keys.add(key)
      else:
        last_deleted_key = key

    self._shelf.sync()
    if not optional and invalid_keys:
      raise KeyError(' '.join(invalid_keys))

  def GetChildren(self, key):
    """Returns children of node `key`.

    For example::
      shelf_view.SetValue('a.b.c', 1)
      shelf_view.SetValue('a.b.d', 1)
      assert shelf_view.GetChildren('a') == {'b'}
      assert shelf_view.GetChildren('a.b') == {'c', 'd'}

    Returns:
      the return value will be an iterable the contains all children of `key`
      :rtype: collections.Iterable
    """
    return self._cached_children[key]

  def GetKeys(self):
    """List of shelf's keys.

    For example::
      shelf_view.SetValue('a.b.c', 1)
      shelf_view.GetKeys() == ['a.b.c']  # note there is no 'a' and 'a.b'
    """
    return self._shelf.keys()

  def Close(self):
    """Closes the shelf."""
    self._shelf.close()

  def Clear(self):
    """Removes everything in shelf."""
    self._shelf.clear()
    self._cached_children.clear()

  def HasKey(self, key):
    """Check if shelf has `key` or has a key that is desendant of `key`.

    For example::
      shelf_view.SetValue('a.b.c', 1)
      assert shelf_view.HasKey('a') == True
      assert shelf_view.HasKey('a.b') == True
      assert shelf_view.HasKey('a.b.c') == True
      assert shelf_view.HasKey('b') == False
      assert shelf_view.HasKey('a.b.c.d') == False
    """
    return key in self._cached_children

  def _DeleteOneKey(self, key, update_parent=True):
    assert isinstance(key, str)
    if key == '':  # '' is the root node, delete it will delete everything
      self.Clear()
      return

    # remove my children
    for child in self._cached_children[key]:
      self._DeleteOneKey(DictKey.Join(key, child), update_parent=False)

    if key in self._shelf:
      # key might be an intermediate node which has no data
      del self._shelf[key]
    del self._cached_children[key]

    if update_parent:
      # remove pointer from my parent
      parent, tail = DictKey.Split(key)
      self._cached_children[parent].remove(tail)
      if not self._cached_children[parent]:
        self._DeleteOneKey(parent, update_parent=True)

  def _InitCache(self):
    keys = self._shelf.keys()
    for key in keys:
      self._AddCache(key)

  def _AddCache(self, key):
    assert isinstance(key, basestring)
    if key:
      parent, tail = DictKey.Split(key)
      self._AddCache(parent)
      # parent should not map to anything, force a pop
      self._shelf.pop(parent, None)
      self._cached_children[parent].add(tail)
    if key not in self._cached_children:
      self._cached_children[key] = set()


class DictKey(object):
  """A namespace of functions to manipulate dict keys.

  Dictionary keys look very similar to domain name addresses, each components of
  key are separated by '.' (dots).  The root node will be represented by an
  empty string ''.  (Direct) Children of root shall access by `key` directly,
  such as 'device'.  A child node 'factory' of node 'device' shall be access by
  'device.factory'.  All keys shall not contain dots (just like you cannot have
  slashes '/' in linux filename).
  """
  @staticmethod
  def Join(parent, *keys):
    """Joins two or more pathname components, '.' will be inserted."""
    path = parent.strip('.')
    for key in keys:
      key = key.strip('.')
      if not key:
        continue
      if path == '':
        path = key
      else:
        path += '.' + key
    return path

  @staticmethod
  def GetBasename(path):
    """Returns the final component."""
    i = path.rfind('.') + 1
    return path[i:]

  @staticmethod
  def GetParent(path):
    """Returns the path whose final component is removed."""
    i = path.rfind('.') + 1
    head = path[:i]
    return head.rstrip('.')

  @staticmethod
  def Split(path):
    """Returns (GetParent(path), GetBasename(path))."""
    i = path.rfind('.') + 1
    head, tail = path[:i], path[i:]
    return head.rstrip('.'), tail

  @staticmethod
  def IsAncestor(a, b):
    """Returns True if `a` is an ancestor of `b` or `a` == `b`"""
    if not isinstance(a, basestring) or not isinstance(b, basestring):
      raise ValueError('`a` and `b` must be strings')
    return (not a) or (a == b) or b.startswith(a + '.')


# for unittest
class InMemoryShelf(dict):
  def sync(self):
    pass

  def close(self):
    pass
