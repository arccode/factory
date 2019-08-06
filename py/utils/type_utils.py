# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for data types."""

import collections
import functools
import inspect
import Queue
import re


# The regular expression used by Overrides.
_OVERRIDES_CLASS_RE = re.compile(r'^\s*class[^#]+\(\s*([^\s#]+)\s*\)\s*\:')


class Error(Exception):
  """Generic fatal error."""
  pass


class TestFailure(Exception):
  """Failure of a test."""


class TestListError(Exception):
  """TestList exception"""
  pass


class TimeoutError(Error):
  """Timeout error."""
  def __init__(self, message='Timed out', output=None):
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

  def __eq__(self, rhs):
    return isinstance(rhs, Obj) and self.__dict__ == rhs.__dict__

  def __ne__(self, rhs):
    return not self.__eq__(rhs)


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


def FlattenTuple(tupl):
  """Flattens a tuple, recursively including all items in contained tuples.

  For example:

    FlattenList((1,2,(3,4,()),5,6)) == (1,2,3,4,5,6)
  """
  return sum((FlattenTuple(x) if isinstance(x, tuple) else (x, ) for x in tupl),
             ())


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


def MakeTuple(value):
  """Converts the given value to a tuple recursively.

  This is helpful for using an iterable argument as dict keys especially
  that arguments from JSON will always be list instead of tuple.

  Returns:
    A tuple of elements from "value" if it is iterable (except string)
    recursively; otherwise, a tuple with only one element.
  """
  def ShouldExpand(v):
    return (isinstance(v, collections.Iterable) and
            not isinstance(v, basestring))

  def Expand(v):
    return tuple(Expand(e) if ShouldExpand(e) else e for e in v)

  if ShouldExpand(value):
    return Expand(value)
  return (value,)


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


def GetDict(data, key_path, default_value=None):
  """A simplified getter function to retrieve values inside dictionary.

  This function is very similar to `dict.get`, except it accepts a key path
  (can be a list or string delimited by dot, for example ['a', 'b'] or 'a.b')

  Args:
    data: A dictionary that may contain sub-dictionaries.
    key_path: A list of keys, or one simple string delimited by dot.
    default_value: The value to return if key_path does not exist.
  """
  if isinstance(key_path, basestring):
    key_path = key_path.split('.')
  for key in key_path:
    if key not in data:
      return default_value
    data = data[key]
  return data


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

  @classmethod
  def _Convert(cls, obj):
    if isinstance(obj, list):
      return [cls._Convert(val) for val in obj]
    if isinstance(obj, dict):
      return cls(obj)
    return obj

  def __init__(self, *args, **kwargs):
    super(AttrDict, self).__init__(*args, **kwargs)
    for key, val in self.iteritems():
      self[key] = self._Convert(val)
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


def Overrides(method):
  """A decorator for checking if the parent has implementation for the method.

  Inspired from http://stackoverflow.com/questions/1167617.
  Current implementation does not support multiple inheritance.

  Example:
    class A(object):
      def m(self):
        return 1

    class B(A):
      @Overrides
      def m(self):
        return 2

    class C(A):
      @Overrides  # This will raise exception because A does not have k method.
      def k(self):
        return 3
        print('child')

  When being used with other decorators, Overrides should be put at last:

  class B(A):
   @property
   @Overrides
   def m(self):
     return 2
  """
  stack = inspect.stack()
  # stack: [overrides, ....[other decorators]..., inside-class, outside-class]
  # The real class (inside-class) is not defined yet so we have to find its
  # parent directly from source definition.
  for i, frame_record in enumerate(stack[2:]):
    source = frame_record[4] or ['']
    matched = _OVERRIDES_CLASS_RE.match(source[0])
    if matched:
      # Find class name from previous frame record.
      current_class = stack[i + 1][3]
      base_class = matched.group(1)
      frame = frame_record[0]
      break
  else:
    raise ValueError('@Overrides failed to find base class from %r' % stack)

  # Resolve base_class in context (look up both locals and globals)
  context = frame.f_globals.copy()
  context.update(frame.f_locals)
  for name in base_class.split('.'):
    if isinstance(context, dict):
      context = context[name]
    else:
      context = getattr(context, name)

  assert hasattr(context, method.__name__), (
      'Method <%s> in class <%s> is not defined in base class <%s>.' %
      (method.__name__, current_class, base_class))
  return method


class CachedGetter(object):
  """A decorator for a cacheable getter function.

  This is helpful for caching results for getter functions. For example::

  @CacheGetter
  def ReadDeviceID():
    with open('/var/device_id') as f:
      return f.read()

  The real file I/O will occur only on first invocation of ``ReadDeviceID()``,
  until ``ReadDeviceID.InvalidateCache()`` is called.

  In current implementation, the getter may accept arguments, but the arguments
  are ignored if there is already cache available. In other words::

  @CacheGetter
  def m(v):
    return v + 1

  m(0)  # First call: returns 1
  m(1)  # Second call: return previous cached answer, 1.
  """

  def __init__(self, getter):
    functools.update_wrapper(self, getter)
    self._getter = getter
    self._has_cached = False
    self._cached_value = None

  def InvalidateCache(self):
    self._has_cached = False
    self._cached_value = None

  def Override(self, value):
    self._has_cached = True
    self._cached_value = value

  def HasCached(self):
    return self._has_cached

  def __call__(self, *args, **kargs):
    # TODO(hungte) Cache args/kargs as well, to return different values when the
    # arguments are different.
    if not self.HasCached():
      self.Override(self._getter(*args, **kargs))
    return self._cached_value


def OverrideCacheableGetter(getter, value):
  """Overrides a function decorated by CacheableGetter with some value."""
  assert hasattr(getter, 'has_cached'), 'Need a CacheableGetter target.'
  assert hasattr(getter, 'cached_value'), 'Need a CacheableGetter target.'
  getter.has_cached = True
  getter.cached_value = value


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
    functools.update_wrapper(self, prop)

  def __get__(self, obj, ignored_obj_type):
    if obj is None:
      return self
    if not hasattr(obj, self._prop_name):
      prop_value = self._init_func(obj)
      setattr(obj, self._prop_name, prop_value)
      return prop_value
    return getattr(obj, self._prop_name)

  def __set__(self, obj, value):
    raise AttributeError('cannot set attribute, use %s.Override instead' %
                         type(self).__name__)

  @classmethod
  def Override(cls, obj, prop_name, value):
    obj_class = type(obj)
    if not hasattr(obj_class, prop_name):
      raise AttributeError('%s has no attribute named %s' % (obj, prop_name))
    if not isinstance(getattr(obj_class, prop_name), cls):
      raise AttributeError('%s is not a %s' % (prop_name, cls.__name__))
    setattr(obj, cls.PROP_NAME_PREFIX + prop_name, value)


class LazyObject(object):
  """A proxy object for creating an object on demand.."""

  def __init__(self, constructor, *args, **kargs):
    self._proxy_constructor = lambda: constructor(*args, **kargs)
    self._proxy_object = None

  def __getattr__(self, name):
    if self._proxy_constructor is not None:
      self._proxy_object = self._proxy_constructor()
      self._proxy_constructor = None
    attr = getattr(self._proxy_object, name)
    # We can't do 'setattr' here to speed up processing because the members in
    # the proxy object may be volatile.
    return attr


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
      while self._list:
        if self._list[-1] in self._set:
          return self._list[-1]
        else:
          self._list.pop()
      return None


def UnicodeToString(obj):
  """Converts any Unicode strings in obj to UTF-8 strings.

  Recurses into lists, dicts, and tuples in obj.
  """
  if isinstance(obj, list):
    return [UnicodeToString(x) for x in obj]
  elif isinstance(obj, dict):
    return dict((UnicodeToString(k), UnicodeToString(v))
                for k, v in obj.iteritems())
  elif isinstance(obj, unicode):
    return obj.encode('utf-8')
  elif isinstance(obj, tuple):
    return tuple(UnicodeToString(x) for x in obj)
  elif isinstance(obj, set):
    return set(UnicodeToString(x) for x in obj)
  else:
    return obj


def UnicodeToStringArgs(function):
  """A function decorator that converts function's arguments from
  Unicode to strings using UnicodeToString.
  """
  @functools.wraps(function)
  def _Wrapper(*args, **kwargs):
    return function(*UnicodeToString(args), **UnicodeToString(kwargs))

  return _Wrapper

def UnicodeToStringClass(cls):
  """A class decorator that converts all arguments of all
  methods in class from Unicode to strings using UnicodeToStringArgs."""
  for k, v in cls.__dict__.items():
    if callable(v):
      setattr(cls, k, UnicodeToStringArgs(v))
  return cls


def StdRepr(obj, extra=None, excluded_keys=None, true_only=False):
  """Returns the representation of an object including its properties.

  Args:
    obj: The object to get properties from.
    extra: Extra items to include in the representation.
    excluded_keys: Keys not to include in the representation.
    true_only: Whether to include only values that evaluate to
      true.
  """
  extra = extra or []
  excluded_keys = excluded_keys or []
  return (obj.__class__.__name__ + '('
          + ', '.join(
              extra +
              ['%s=%s' % (k, repr(getattr(obj, k)))
               for k in sorted(obj.__dict__.keys())
               if k[0] != '_' and k not in excluded_keys and (
                   not true_only or getattr(obj, k))])
          + ')')


def BindFunction(func, *args, **kwargs):
  """Bind arguments to a function.

  The returned function have same __name__ and __doc__ with func.
  """
  @functools.wraps(func)
  def _Wrapper():
    return func(*args, **kwargs)
  return _Wrapper
