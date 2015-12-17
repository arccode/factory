# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for data types."""

import collections
import Queue


class Error(Exception):
  """Generic fatal error."""
  pass


class TimeoutError(Error):
  """Timeout error."""
  def __init__(self, message, output=None):
    Error.__init__(self)
    self.message = message
    self.output = output

  def __str__(self):
    return repr(self.message)


class Obj(object):
  """Generic wrapper allowing dot-notation dict access."""

  def __init__(self, **field_dict):
    self.__dict__.update(field_dict)

  def __repr__(self):
    return repr(self.__dict__)


class Enum(frozenset):
  """An enumeration type.

  Usage:
    To create a enum object:
      dummy_enum = type_utils.Enum(['A', 'B', 'C'])

    To access a enum object, use:
      dummy_enum.A
      dummy_enum.B
  """

  def __getattr__(self, name):
    if name in self:
      return name
    raise AttributeError


def DrainQueue(queue):
  """Returns as many elements as can be obtained from a queue without blocking.

  (This may be no elements at all.)
  """
  ret = []
  while True:
    try:
      ret.append(queue.get_nowait())
    except Queue.Empty:
      break
  return ret


def FlattenList(lst):
  """Flattens a list, recursively including all items in contained arrays.

  For example:

    FlattenList([1,2,[3,4,[]],5,6]) == [1,2,3,4,5,6]
  """
  return sum((FlattenList(x) if isinstance(x, list) else [x] for x in lst),
             [])


def MakeList(value):
  """Converts the given value to a list.

  Returns:
    A list of elements from "value" if it is iterable (except string);
    otherwise, a list contains only one element.
  """
  if (isinstance(value, collections.Iterable) and
      not isinstance(value, basestring)):
    return list(value)
  return [value]


def MakeSet(value):
  """Converts the given value to a set.

  Returns:
    A set of elements from "value" if it is iterable (except string);
    otherwise, a set contains only one element.
  """
  if (isinstance(value, collections.Iterable) and
      not isinstance(value, basestring)):
    return set(value)
  return set([value])


def CheckDictKeys(dict_to_check, allowed_keys):
  """Makes sure that a dictionary's keys are valid.

  Args:
    dict_to_check: A dictionary.
    allowed_keys: The set of allowed keys in the dictionary.
  """
  if not isinstance(dict_to_check, dict):
    raise TypeError('Expected dict but found %s' % type(dict_to_check))

  extra_keys = set(dict_to_check) - set(allowed_keys)
  if extra_keys:
    raise ValueError('Found extra keys: %s' % list(extra_keys))


class AttrDict(dict):
  """Attribute dictionary.

  Use subclassed dict to store attributes. On __init__, the values inside
  initial iterable will be converted to AttrDict if its type is a builtin
  dict or builtin list.

  Example:
    foo = AttrDict()
    foo['xyz'] = 'abc'
    assertEqual(foo.xyz, 'abc')

    bar = AttrDict({'x': {'y': 'value_x_y'},
                    'z': [{'m': 'value_z_0_m'}]})
    assertEqual(bar.x.y, 'value_x_y')
    assertEqual(bar.z[0].m, 'value_z_0_m')
  """

  def _IsBuiltinDict(self, item):
    return (isinstance(item, dict) and
            item.__class__.__module__ == '__builtin__' and
            item.__class__.__name__ == 'dict')

  def _IsBuiltinList(self, item):
    return (isinstance(item, list) and
            item.__class__.__module__ == '__builtin__' and
            item.__class__.__name__ == 'list')

  def _ConvertList(self, itemlist):
    converted = []
    for item in itemlist:
      if self._IsBuiltinDict(item):
        converted.append(AttrDict(item))
      elif self._IsBuiltinList(item):
        converted.append(self._ConvertList(item))
      else:
        converted.append(item)
    return converted

  def __init__(self, *args, **kwargs):
    super(AttrDict, self).__init__(*args, **kwargs)
    for key, value in self.iteritems():
      if self._IsBuiltinDict(value):
        self[key] = AttrDict(value)
      elif self._IsBuiltinList(value):
        self[key] = self._ConvertList(value)
    self.__dict__ = self


class Singleton(type):
  """Singleton metaclass.

  Set __metaclass__ to Singleton to make it a singleton class. The instances
  are stored in:
    Singleton._instances[CLASSNAME]

  Example:
    class C(object):
      __metaclass__ = Singleton

    foo = C()
    bar = C()  # foo == bar
  """
  _instances = {}

  def __call__(cls, *args, **kwargs):
    if cls not in cls._instances:
      cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
    return cls._instances[cls]


class LazyProperty(object):
  """A decorator for lazy loading properties.

  Example:
    class C(object):
      @LazyProperty
      def m(self):
        print 'init!'
        return 3

    c = C()
    print c.m  # see 'init!' then 3
    print c.m  # only see 3
  """
  PROP_NAME_PREFIX = '_lazyprop_'

  def __init__(self, prop):
    self._init_func = prop
    self._prop_name = self.PROP_NAME_PREFIX + prop.__name__

  def __get__(self, obj, ignored_obj_type):
    if obj is None:
      return self
    if not hasattr(obj, self._prop_name):
      setattr(obj, self._prop_name, self._init_func(obj))
    return getattr(obj, self._prop_name)

  def __set__(self, obj, value):
    raise AttributeError('cannot set attribute, use %s.Override instead' %
                         type(self).__name__)

  @classmethod
  def Override(cls, obj, prop_name, value):
    obj_props = type(obj).__dict__
    if prop_name not in obj_props:
      raise AttributeError('%s has no attribute named %s' % (obj, prop_name))
    if not isinstance(obj_props[prop_name].__get__(None, None), cls):
      raise AttributeError('%s is not a %s' % (prop_name, cls.__name__))
    setattr(obj, cls.PROP_NAME_PREFIX + prop_name, value)


class UniqueStack(object):
  """ A data structure very similar to a stack, but objects inside are unique.

  - If an object is in the stack already, adding it again to the stack won't
    change anything.

  - One can remove any object from the stack, no matter where it is.

  - One can always get the latest added object that haven't been removed.
  """
  def __init__(self):
    import threading
    self._lock = threading.Lock()
    self._set = set([])
    self._list = list([])

  def Add(self, x):
    """Add an object on the top of the stack.
    If the object is already in the stack, nothing will happen.

    This function should run in O(1)
    """
    if x not in self._set:
      with self._lock:
        if x not in self._set:
          self._set.add(x)
          self._list.append(x)

  def Del(self, x):
    """Remove @x from the stack, no matter where it is.
    If @x is not in the stack, nothing will happen.

    This function should run in O(1)
    """
    if x in self._set:
      with self._lock:
        if x in self._set:
          self._set.remove(x)

  def Get(self):
    """Returns element at top of the stack.

    This function should run in amortized O(1)
    """
    with self._lock:
      while len(self._list) > 0:
        if self._list[-1] in self._set:
          return self._list[-1]
        else:
          self._list.pop()
      return None
