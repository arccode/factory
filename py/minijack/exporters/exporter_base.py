# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

class ExporterBase(object):
  '''The base class of exporters.

  An exporter is a customized class which analyses event logs and dumps their
  knowledge into a database.

  All exporter classes should inherit this ExporterBase class and implement/reuse
  the following methods:
    Setup(self): This method is called on Minijack start-up.
    Cleanup(self): This method is called on Minijack shut-down.
    Handle_xxx(self, preamble, event): This method is called when an event,
        with event id == 'xxx', is received. The preamble and event arguments
        contain the Python dict of the preamble and the event. An exporter class
        contains multiple Handle_xxx(). The Handle_all() is special, which is
        called on every event. This method doesn't follow the naming conversion
        as we want to keep xxx the same as the event name.

  Note that all the exporter module should be added into __init__.py. Otherwise,
  they are not loaded by default.

  Some naming conversions:
    module file name: xxx_exporter.py
    module name: xxx_exporter
    class name: XxxExporter

  TODO(waihong): Unit tests.

  Properties:
    _database: The database object of the database.
    _table: The table object.
  '''
  def __init__(self, database):
    self._database = database

  def Setup(self):
    '''This method is called on Minijack start-up.'''
    pass

  def Cleanup(self):
    '''This method is called on Minijack shut-down.'''
    pass

def _FlattenAttr(attr):
  '''Generator of flattened attributes.

  Args:
    attr: The attr dict/list which may contains multi-level dicts/lists.

  Yields:
    A tuple (list_of_path, leaf_value).

  >>> attr = {'a': {'k1': 'v1',
  ...               'k2': {'dd1': 'vv1',
  ...                      'dd2': 'vv2'}},
  ...         'b': ['i1', 'i2', 'i3'],
  ...         'c': 'ss'}
  >>> (dict(('.'.join(k), v) for k, v in _FlattenAttr(attr)) ==
  ...     {'a.k1': 'v1',
  ...      'a.k2.dd1': 'vv1',
  ...      'a.k2.dd2': 'vv2',
  ...      'b.0': 'i1',
  ...      'b.1': 'i2',
  ...      'b.2': 'i3',
  ...      'c': 'ss'})
  True
  '''
  if isinstance(attr, dict):
    for key, val in attr.iteritems():
      for path, leaf in _FlattenAttr(val):
        yield [key] + path, leaf
  elif isinstance(attr, list):
    for index, val in enumerate(attr):
      for path, leaf in _FlattenAttr(val):
        yield [str(index)] + path, leaf
  else:
    # The leaf node.
    yield [], attr

# Join the path list using '.'.
FlattenAttr = lambda x: (('.'.join(k), v) for k, v in _FlattenAttr(x))

def FindContainingDictForKey(deep_dict, key):
  '''Finds the dict that contains the given key from the deep_dict.

  Args:
    deep_dict: The dict/list which may contains multi-level dicts/lists.
    key: A string of key.

  Returns:
    The dict that contains the given key.

  >>> attr = {'a': {'k1': 'v1',
  ...               'k2': {'dd1': 'vv1',
  ...                      'dd2': 'vv2'}},
  ...         'b': [{'ss': 'tt'},
  ...               {'uu': 'vv'}],
  ...         'c': 'ss'}
  >>> (FindContainingDictForKey(attr, 'dd2') ==
  ...     {'dd1': 'vv1',
  ...      'dd2': 'vv2'})
  True
  >>> (FindContainingDictForKey(attr, 'ss') ==
  ...     {'ss': 'tt'})
  True
  '''
  if isinstance(deep_dict, dict):
    if key in deep_dict.iterkeys():
      # Found, return its parent.
      return deep_dict
    else:
      # Try its children.
      for val in deep_dict.itervalues():
        result = FindContainingDictForKey(val, key)
        if result:
          return result
  elif isinstance(deep_dict, list):
    # Try its children.
    for val in deep_dict:
      result = FindContainingDictForKey(val, key)
      if result:
        return result
  # Not found.
  return None
