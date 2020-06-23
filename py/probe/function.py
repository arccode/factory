# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import inspect
import logging
import os
import pkgutil

from cros.factory.utils import arg_utils


# The index for indicating the situation that there is only one argument.
_FAKE_INDEX = 'FAKE_INDEX'
NOTHING = []
INITIAL_DATA = [{}]


# The registered function table mapping from the name to the function class.
_function_map = {}
_function_loaded = False  # Only load the function classes in 'functions/' once.


def GetRegisteredFunctions():
  return list(_function_map)


def GetFunctionClass(func_name):
  return _function_map.get(func_name)


def RegisterFunction(name, cls, force=False):
  """Register the function to make it able to be interpreted.

  Args:
    name: the registered function name.
    cls: the function class. It should be a derived class of "Function".
    force: True to allow overwriting a registered function name.
  """
  if not isinstance(cls, type) or not issubclass(cls, Function):
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

  if len(func_expression) != 1:
    raise FunctionException(
        'Function expression %s should only contain 1 item.' % func_expression)
  func_name, kwargs = next(iter(func_expression.items()))
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


class Function:
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
      if not self.ARGS:
        raise FunctionException(
            'Function "%s" does not require any argument.' %
            self.__class__.__name__)
      if len(self.ARGS) == 1:
        kwargs = {self.ARGS[0].name: kwargs[_FAKE_INDEX]}
      else:
        required_args = [arg.name for arg in self.ARGS if not arg.IsOptional()]
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
