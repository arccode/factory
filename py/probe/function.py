# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import inspect
import logging
import os
import pkgutil

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import arg_utils
from cros.factory.utils.arg_utils import Arg


# The index for indicating the situation that there is only one argument.
_FAKE_INDEX = 'FAKE_INDEX'
NOTHING = []
INITIAL_DATA = [{}]


# The registered function table mapping from the name to the function class.
_function_map = {}
_function_loaded = False  # Only load the function classes in 'functions/' once.


def GetRegisteredFunctions():
  return _function_map.keys()


def GetFunctionClass(func_name):
  return _function_map.get(func_name)


def RegisterFunction(name, cls, force=False):
  """Register the function to make it able to be interpreted.

  Args:
    name: the registered function name.
    cls: the function class. It should be a derived class of "Function".
    force: True to allow overwriting a registered function name.
  """
  if type(cls) != type or not issubclass(cls, Function):
    raise FunctionException('"%s" is not subclass of Function.' % cls.__name__)
  if name in _function_map and not force:
    raise FunctionException('Function "%s" is already registered.' % name)
  _function_map[name] = cls


def LoadFunctions():
  """Load every function class in `py/probe/functions/` directory."""
  global _function_loaded  # pylint: disable=global-statement
  if _function_loaded:
    return
  _function_loaded = True

  def IsFunctionClass(obj):
    return isinstance(obj, type) and issubclass(obj, Function)

  from cros.factory.probe import functions
  module_path = os.path.dirname(functions.__file__)
  for loader, module_name, unused_is_pkg in pkgutil.iter_modules([module_path]):
    if module_name.endswith('unittest'):
      continue
    module = loader.find_module(module_name).load_module(module_name)
    func_classes = inspect.getmembers(module, IsFunctionClass)
    assert len(func_classes) <= 1
    if func_classes:
      logging.info('Load function: %s', module_name)
      RegisterFunction(module_name, func_classes[0][1])


def InterpretFunction(func_expression):
  """Interpret a function expression to a callable function instance.

  The format of the function expression is:
  FUNCTIONS := FUNCTION | <list of FUNCTION>
  FUNCTION  := "FUNC_NAME" |  # Valid if FUNC_ARGS is a empty dict.
               "FUNC_NAME:FUNC_ARGS" |  # Valid if FUNC_ARGS is a string.
               {FUNC_NAME: FUNC_ARGS}
  FUNC_NAME := <string>  # The function should be already registered.
  FUNC_ARGS := <string> |  # Valid if there is only one required argument.
               <dict>

  For example:
    {'file': {'file_path': '/var/log/dmesg'}}
    {'file': '/var/log/dmesg'}
    'file:/var/log/dmesg'
  These three expressions are equivalent.

  Args:
    func_expression: dict or list of dict.

  Returns:
    a Function instance.
  """
  if not _function_loaded:
    LoadFunctions()

  if isinstance(func_expression, list):
    # It's syntax sugar for sequence function.
    expression = {'sequence': {'functions': func_expression}}
    return InterpretFunction(expression)
  if isinstance(func_expression, str):
    func_name, unused_sep, kwargs = func_expression.partition(':')
    func_expression = {func_name: {}} if not kwargs else {func_name: kwargs}

  assert len(func_expression) == 1
  func_name, kwargs = func_expression.items()[0]
  if func_name not in _function_map:
    raise FunctionException('Function "%s" is not registered.' % func_name)

  if not isinstance(kwargs, str) and not isinstance(kwargs, dict):
    raise FunctionException(
        'Invalid argument: "%s" should be string or dict.' % kwargs)
  if isinstance(kwargs, str):
    # If the argument is a string, then treat it the only required argument.
    instance = _function_map[func_name](**{_FAKE_INDEX: kwargs})
  else:
    instance = _function_map[func_name](**kwargs)
  return instance


class FunctionException(Exception):
  pass


class Function(object):
  """The base function class.

  The instance of a function class is callable, which input data and output data
  are both list of the dict. Every item in the list means a possible result of
  the computation. While the list is empty, it means the computation is failed.
  In this case the procedure will not be executed.
  """

  # The definition of the required arguments in constructor. Each element should
  # be an Arg object. It should be overwritten by each subclass.
  ARGS = []

  def __init__(self, **kwargs):
    """Parse the arguments and set them to self.args."""
    if len(kwargs) == 1 and _FAKE_INDEX in kwargs:
      if len(self.ARGS) == 0:
        raise FunctionException(
            'Function "%s" does not require any argument.' %
            self.__class__.__name__)
      elif len(self.ARGS) == 1:
        kwargs = {self.ARGS[0].name: kwargs[_FAKE_INDEX]}
      else:
        required_args = [arg.name for arg in self.ARGS if not arg.optional]
        if len(required_args) != 1:
          raise FunctionException(
              'Function "%s" requires more than one argument: %s' %
              (self.__class__.__name__, required_args))
        kwargs = {required_args[0]: kwargs[_FAKE_INDEX]}
    self.args = arg_utils.Args(*self.ARGS).Parse(kwargs)

  def __call__(self, data=None):
    if data is None:
      data = INITIAL_DATA
    if not data:
      return NOTHING

    try:
      return self.Apply(data)
    except Exception:
      logging.exception('Error occurred while applying function "%s.%s"',
                        self.__class__.__module__, self.__class__.__name__)
      return NOTHING

  def Apply(self, data):
    raise NotImplementedError


class ProbeFunction(Function):
  """The base class of probe functions.

  While evaluation, the function probes the result, and update to the input
  data. If there are multiple probe result, the output list contains all
  the combination of the input and the probed data.
  """
  def Apply(self, data):
    results = self.Probe()
    if not isinstance(results, list):
      results = [results]

    ret = []
    for result in results:
      for item in data:
        new_item = copy.copy(item)
        new_item.update(result)
        ret.append(new_item)
    return ret

  def Probe(self):
    """Return the probe result. It can be a dict or a list of dict."""
    raise NotImplementedError


class ActionFunction(Function):
  """The base class of action functions.

  While evaluation, an action function executes a side-effect action. If the
  action is successfully executed, it returns the input data. Otherwise it
  returns an empty list to notify the computation failed.
  """
  def Apply(self, data):
    if self.Action():
      return data
    return NOTHING

  def Action(self):
    """Execute an action and return the action is successfully or not."""
    raise NotImplementedError


class CombinationFunction(Function):
  """The base class of combination functions.

  The argument of combination function is a list of the function expressions.
  The combination function combine the output of the functions in a certain way.
  """
  ARGS = [
      Arg('functions', list, 'The list of the function expression.')
  ]

  def __init__(self, **kwargs):
    super(CombinationFunction, self).__init__(**kwargs)
    # Interpret the function expressions to function instances.
    self.functions = [InterpretFunction(func) for func in self.args.functions]

  def Apply(self, data):
    return self.Combine(self.functions, data)

  def Combine(self, functions, data):
    raise NotImplementedError


class Sequence(CombinationFunction):
  """Sequential execute the functions.

  The input of the next function is the output of the previous function.
  The concept is:
    data = Func1(data)
    data = Func2(data)
    ...
  """
  def Combine(self, functions, data):
    for func in functions:
      data = func(data)
    return data
RegisterFunction('sequence', Sequence)


class Or(CombinationFunction):
  """Returns the first successful output.

  The concept is:
    output = Func1(data) or Func2(data) or ...
  """
  def Combine(self, functions, data):
    for func in functions:
      ret = func(data)
      if ret:
        return ret
    return NOTHING
RegisterFunction('or', Or)


class InnerJoin(CombinationFunction):
  """Inner join the result of functions.

  InnerJoin combines the result by finding the same index. For example:
  Combine them by 'idx':
    [{'idx': '1', 'foo': 'foo1'}, {'idx': '2', 'foo': 'foo2'}]
    [{'idx': '1', 'bar': 'bar1'}, {'idx': '2', 'bar': 'bar2'}]
  becomes:
    [{'idx': '1', 'foo': 'foo1', 'bar': 'bar1'},
     {'idx': '2', 'foo': 'foo2', 'bar': 'bar2'}]
  """
  ARGS = [
      Arg('functions', list, 'The list of the function expression.'),
      Arg('index', str, 'The index name for inner join.')
  ]

  def Combine(self, functions, data):
    idx_set = None
    result_list = []
    for func in functions:
      results = [item for item in func(data) if self.args.index in item]
      if not results:
        return NOTHING
      result_map = {result[self.args.index]: result for result in results}
      if idx_set is None:
        idx_set = set(result_map.keys())
      else:
        idx_set &= set(result_map.keys())
      result_list.append(result_map)

    if not idx_set:
      return NOTHING
    ret = []
    for idx in idx_set:
      joined_result = {}
      for result_item in result_list:
        joined_result.update(result_item[idx])
      ret.append(joined_result)
    return ret
RegisterFunction('inner_join', InnerJoin)
