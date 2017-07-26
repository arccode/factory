# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import shelve_utils

_DEFAULT_NOT_SET = object()


class ISelector(object):
  """A wrapper to unify access style of different objects.

  A selector wraps an object and make it a recursive-dictionary-like object,
  supports implicit bool conversion.

  A selector should have the following behaviors.
  1. Support both attribute access and dictionary key access, and they should be
    equivalent:

      selector['xxx.yyy'].Get()
      selector['xxx']['yyy'].Get()
      selector.xxx.yyy.Get()
      selector.xxx['yyy'].Get()

  2. In the above case, if 'xxx' is not a valid key, exception should not be
    raised before a Get() is called.

      xxx = selector.xxx  # ok
      xxx.Get()  # KeyError
      yyy = xxx.yyy  # ok
      yyy.Get()  # KeyError

  3. Be able to convert to boolean implicitly, and if the key does not exists,
    'False' is the default value.

      xxx = selector.xxx  # ok, but xxx.Get() will raise KeyError
      bool(xxx)  # False
      yyy = xxx.yyy  # ok
      bool(yyy)  # False

  For example, if the data stored in the object is:

      {
        'a': {
          'b': {
            'c': 3
          }
        }
      }

  Then,

      selector.Get() shall return entire dictionary.

      selector['a'] shall return another selector rooted at 'a', thus
      selector['a'].Get() shall return {'b': {'c': 3}}.

      selector.GetValue('a') shall return {'b': {'c': 3}}
      selector['a'].GetValue('b') shall return {'c': 3}

      selector['a']['b'] and selector['a.b'] are equivalent, they both return a
      selector rooted at 'b'.
  """
  def __getattr__(self, attr):
    return self[attr]

  def __getitem__(self, key):
    raise NotImplementedError

  def Get(self, default=_DEFAULT_NOT_SET):
    raise NotImplementedError

  def GetValue(self, key, default=_DEFAULT_NOT_SET):
    return self[key].Get(default)

  def __nonzero__(self):
    return bool(self.Get(False))


class DataShelfSelector(ISelector):
  """Data selector for data_shelf of FactoryState.

  data_shelf behaves like a recursive dictionary structure.  The
  DataShelfSelector helps you get data from this dictionary.

  """
  def __init__(self, proxy, key=''):
    """Constructor

    Args:
      :type proxy: FactoryState
      :type key: basestring
    """
    self._proxy = proxy
    self._key = key

  def SetValue(self, key, value):
    key = shelve_utils.DictKey.Join(self._key, key)

    self._proxy.data_shelf_set_value(key, value)

  def GetValue(self, key, default=_DEFAULT_NOT_SET):
    key = shelve_utils.DictKey.Join(self._key, key)

    if default is _DEFAULT_NOT_SET or self._proxy.data_shelf_has_key(key):
      return self._proxy.data_shelf_get_value(key, False)
    else:
      return default

  def Set(self, value):
    self.SetValue('', value)

  def Get(self, default=_DEFAULT_NOT_SET):
    return self.GetValue('', default=default)

  def __getitem__(self, key):
    key = shelve_utils.DictKey.Join(self._key, key)
    return self.__class__(self._proxy, key)

  def __setitem__(self, key, value):
    self.SetValue(key, value)

  def __iter__(self):
    return iter(self._proxy.data_shelf_get_children(self._key))

  def __contains__(self, key):
    return key in self._proxy.data_shelf_get_children(self._key)

  def __nonzero__(self):
    return bool(self.Get(default=False))


class DictSelector(ISelector):
  def __init__(self, key='', value=_DEFAULT_NOT_SET):
    self.key = key
    self.value = value

  def __getitem__(self, key):
    parent, basename = shelve_utils.DictKey.Split(key)
    if parent:
      return self[parent][basename]
    new_key = shelve_utils.DictKey.Join(self.key, basename)
    if isinstance(self.value, collections.Mapping):
      return DictSelector(key=new_key,
                          value=self.value.get(basename, _DEFAULT_NOT_SET))
    else:
      return DictSelector(key=new_key)

  def Get(self, default=_DEFAULT_NOT_SET):
    if self.value is _DEFAULT_NOT_SET and default is _DEFAULT_NOT_SET:
      raise KeyError(self.key)
    return self.value if self.value is not _DEFAULT_NOT_SET else default
