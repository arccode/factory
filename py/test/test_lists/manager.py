#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Loader of test_list.json"""

import __builtin__
import abc
import ast
import collections
import copy
import glob
import inspect
import logging
import os
import sys

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test import factory
from cros.factory.test.i18n import _
from cros.factory.test.test_lists import test_lists
from cros.factory.utils import config_utils
from cros.factory.utils import type_utils


# used for loop detection
_DUMMY_CACHE = object()


class TestListConfig(object):
  """A loaded test list config.

  This is basically a wrapper for JSON object (the content loaded from test list
  JSON file), with some helper functions and caches.
  """
  def __init__(self, json_object, test_list_id, timestamp):
    self._json_object = json_object
    self._timestamp = timestamp
    self._test_list_id = test_list_id

  def GetParents(self):
    return self._json_object.get('inherit', [])

  @property
  def timestamp(self):
    return self._timestamp

  @property
  def test_list_id(self):
    return self._test_list_id

  def __getitem__(self, key):
    return self._json_object[key]

  def __iter__(self):
    return iter(self._json_object)

  def ToDict(self):
    return self._json_object.copy()


class ITestList(object):
  """An interface of test list object."""

  __metaclass__ = abc.ABCMeta

  # Declare instance variables to make __setattr__ happy.
  _checker = None

  def __init__(self, checker=None):
    self._checker = checker or Checker()

  @abc.abstractmethod
  def ToFactoryTestList(self):
    """Convert this object to a factory.FactoryTestList object.

    Returns:
      :rtype: cros.factory.test.factory.FactoryTestList
    """
    raise NotImplementedError

  def __getattr__(self, name):
    """Redirects attribute lookup to ToFactoryTestList()."""
    logging.debug('getting: %s', name)
    return getattr(self.ToFactoryTestList(), name)

  def __setattr__(self, name, value):
    # Can only set an attribute that already exists.
    if hasattr(self, name):
      object.__setattr__(self, name, value)
    else:
      raise AttributeError('cannot set attribute %r' % name)

  @abc.abstractproperty
  def modified(self):
    raise NotImplementedError

  @abc.abstractproperty
  def constants(self):
    raise NotImplementedError

  def ResolveTestArgs(
      self, test_args, dut, station, constants=None, options=None):
    if constants is None:
      constants = self.constants
    if options is None:
      options = self.options

    _EVALUATE_PREFIX = 'eval! '
    def ResolveArg(key, value):
      if isinstance(value, collections.Mapping):
        return {k: ResolveArg('%s[%r]' % (key, k), v)
                for k, v in value.iteritems()}

      if isinstance(value, collections.Sequence):
        if not isinstance(value, basestring):
          # value is a list, but not a string.
          return [ResolveArg('%s[%d]' % (key, i), v)
                  for i, v in enumerate(value)]

      if not isinstance(value, basestring):
        return value

      if value.startswith(_EVALUATE_PREFIX):
        logging.info('Resolving argument %s: %s', key, value)
        expression = value[len(_EVALUATE_PREFIX):]  # remove prefix

        self._checker.AssertExpressionIsValid(expression)
        return self.EvaluateExpression(
            expression, dut, station, constants, options)

      # otherwise, this is a normal string
      return value
    return {k: ResolveArg(k, v) for k, v in test_args.iteritems()}

  @staticmethod
  def EvaluateExpression(expression, dut, station, constants, options):
    namespace = {
        'dut': dut,
        'station': station,
        'constants': constants,
        'options': options, }
    # pylint: disable=eval-used
    return eval(expression, namespace)

  # the following properties are required by goofy
  @abc.abstractproperty
  def state_instance(self):
    raise NotImplementedError

  @state_instance.setter
  def state_instance(self, state_instance):
    raise NotImplementedError

  @abc.abstractproperty
  def state_change_callback(self):
    raise NotImplementedError

  @state_change_callback.setter
  def state_change_callback(self, state_change_callback):
    raise NotImplementedError


class TestList(ITestList):
  """A test list object represented by test list config.

  This object should act like a cros.factory.test.factory.FactoryTestList
  object.
  """

  # Declare instance variables to make __setattr__ happy.
  _config = None
  _cached_test_list = None
  _timestamp = 0
  _options = None
  _constants = None
  _state_instance = None
  _state_change_callback = None

  def __init__(self, config, checker=None):
    super(TestList, self).__init__(checker)
    self._config = config
    self._cached_test_list = None
    self._timestamp = 0
    self._options = None
    self._constants = None
    self._state_instance = None
    self._state_change_callback = None

  def ToFactoryTestList(self):
    if not self.modified and self._cached_test_list:
      return self._cached_test_list

    subtests = []
    cache = {}
    for test_object in self._config['tests']:
      subtests.append(self.MakeTest(test_object, cache))

    self._cached_test_list = factory.FactoryTestList(
        subtests, self._state_instance, self.options,
        test_list_id=self._config.test_list_id,
        label=_(self._config['label']),
        finish_construction=True)
    self._cached_test_list.state_change_callback = self._state_change_callback
    return self._cached_test_list

  def MakeTest(self,
               test_object,
               cache,
               default_action_on_failure=None):
    """Convert a test_object to a FactoryTest object."""

    test_object = self.ResolveTestObject(
        test_object=test_object,
        test_object_name=None,
        cache=cache)

    if not test_object.get('action_on_failure', None):
      test_object['action_on_failure'] = default_action_on_failure
    default_action_on_failure = test_object.pop('child_action_on_failure',
                                                default_action_on_failure)
    # TODO(stimim):
    #   * auto derive label / id from pytest name
    kwargs = copy.deepcopy(test_object)
    class_name = kwargs.pop('inherit', 'FactoryTest')

    subtests = []
    for subtest in test_object.get('subtests', []):
      subtests.append(self.MakeTest(subtest, cache, default_action_on_failure))

    # replace subtests
    kwargs['subtests'] = subtests
    kwargs['dargs'] = kwargs.pop('args', {})
    kwargs.pop('__comment', None)

    # syntactic sugar: if `id` is not specified, we will try to generate an id
    # for you.
    if 'id' not in kwargs:
      if 'pytest_name' in kwargs:
        kwargs['id'] = kwargs['pytest_name']
      elif subtests:
        kwargs['id'] = 'TestGroup'

    return getattr(factory, class_name)(**kwargs)

  def ResolveTestObject(self, test_object, test_object_name, cache):
    """Returns a test object inherits all its parents field."""
    if test_object_name in cache:
      if cache[test_object_name] == _DUMMY_CACHE:
        raise factory.TestListError(
            'Detected loop inheritance dependency of %s' % test_object_name)
      else:
        return cache[test_object_name]

    # syntactic sugar: if a test_object is just a string, it's equivalent to
    # {"inherit": string}, e.g.:
    #   "test_object" === {"inherit": "test_object"}
    if isinstance(test_object, basestring):
      resolved = self.ResolveTestObject({'inherit': test_object},
                                        test_object_name, cache)
      return resolved

    parent_name = test_object.get('inherit', 'FactoryTest')
    if parent_name not in self._config['definitions']:
      raise factory.TestListError(
          '%s inherits %s, which is not defined' % (test_object_name,
                                                    parent_name))
    if parent_name == test_object_name:
      # this test object inherits itself, it means that this object is a class
      # defined in cros.factory.test.factory
      # just save the object and return
      cache[test_object_name] = test_object
      return test_object

    if test_object_name:
      cache[test_object_name] = _DUMMY_CACHE
      if 'id' not in test_object:
        test_object['id'] = test_object_name

    parent_object = self._config['definitions'][parent_name]
    parent_object = self.ResolveTestObject(parent_object, parent_name, cache)
    test_object = config_utils.OverrideConfig(copy.deepcopy(parent_object),
                                              test_object)
    test_object['inherit'] = parent_object['inherit']
    if test_object_name:
      cache[test_object_name] = test_object
    return test_object

  def ToTestListConfig(self, recursive=True):
    if recursive:
      return self._config.ToDict()
    else:
      ret = self._config.ToDict()
      ret.pop('tests', None)
      return ret

  @property
  def modified(self):
    """Return True if the test list is considered modified, need to be reloaded.

    Currently, this function always returns False.
    """
    # TODO(stimim): implement this function.
    return False

  @property
  def constants(self):
    if not self.modified and self._constants:
      return self._constants
    self._constants = type_utils.AttrDict(self._config['constants'])
    return self._constants

  # the following functions / properties are required by goofy
  @property
  def options(self):
    if not self.modified and self._options:
      return self._options

    self._options = factory.Options()

    class NotAccessable(object):
      def __getattribute__(self, name):
        raise KeyError('options cannot depend on options')

    resolved_options = self.ResolveTestArgs(
        self._config['options'],
        constants=self.constants,
        options=NotAccessable(),
        dut=None,
        station=None)
    for key, value in resolved_options.iteritems():
      setattr(self._options, key, value)
    return self._options

  @property
  def state_instance(self):
    return self.ToFactoryTestList().state_instance

  @state_instance.setter
  def state_instance(self, state_instance):  # pylint: disable=arguments-differ
    self._state_instance = state_instance
    self.ToFactoryTestList().state_instance = state_instance

  @property
  def state_change_callback(self):
    return self.ToFactoryTestList().state_change_callback

  # pylint: disable=arguments-differ
  @state_change_callback.setter
  def state_change_callback(self, state_change_callback):
    self._state_change_callback = state_change_callback
    self.ToFactoryTestList().state_change_callback = state_change_callback


class LegacyTestList(ITestList):
  """Wrap a factory.FactoryTestList object into ITestList object."""

  # Declare instance variables to make __setattr__ happy.
  test_list = None

  def __init__(self, test_list, checker=None):
    """Constructor

    Args:
      :type test_list: cros.factory.test.factory.FactoryTestList
    """
    super(LegacyTestList, self).__init__(checker)
    self.test_list = test_list

  def ToFactoryTestList(self):
    return self.test_list

  @property
  def modified(self):
    return False

  @property
  def constants(self):
    # Legacy test list does not have constants field, return an empty namespace
    return type_utils.AttrDict()

  @property
  def state_instance(self):
    return self.test_list.state_instance

  @state_instance.setter
  def state_instance(self, state_instance):  # pylint: disable=arguments-differ
    self.test_list.state_instance = state_instance

  @property
  def state_change_callback(self):
    return self.test_list.state_change_callback

  # pylint: disable=arguments-differ
  @state_change_callback.setter
  def state_change_callback(self, state_change_callback):
    self.test_list.state_change_callback = state_change_callback


class Loader(object):
  """Helper class to load a test list from given directory.

  The loader loads a JSON test list config from file system.  A loaded config
  will be `TestListConfig` object, which can be passed to `TestList` to create
  an `ITestList` object.
  """
  CONFIG_SUFFIX = '.test_list'
  """All test lists must have name: <id>.test_list.json"""

  ARGS_CONFIG_SUFFIX = '.test_list.args'
  """Config files with name: <id>.test_list.args.json can override arguments"""

  def __init__(self, schema_name='test_list', config_dir=None):
    self.schema_name = schema_name
    if not config_dir:
      # paths.FACTORY_DIR does not work in factory par, however, currently, we
      # should not run Goofy and test list manager in factory par.
      # The default_config_dir config_utils.LoadConfig will find should be the
      # same one we compute here, however, we also need this path to check file
      # state, so let's figure out the path by ourselves.
      config_dir = os.path.join(paths.FACTORY_DIR,
                                'py', 'test', 'test_lists')
    self.config_dir = config_dir

  def Load(self, test_list_id):
    """Loads test list config by test list ID.

    Returns:
      :rtype: TestListConfig
    """
    config_name = self._GetConfigName(test_list_id)
    loaded_config = config_utils.LoadConfig(
        config_name=config_name,
        schema_name=self.schema_name,
        validate_schema=True,
        default_config_dir=self.config_dir,
        allow_inherit=True)

    timestamp = os.stat(self.GetConfigPath(test_list_id)).st_mtime

    return TestListConfig(
        json_object=loaded_config,
        test_list_id=test_list_id,
        timestamp=timestamp)

  def GetConfigPath(self, test_list_id):
    """Returns the test list config file path of `test_list_id`."""
    return os.path.join(self.config_dir,
                        self._GetConfigName(test_list_id) + '.json')

  def _GetConfigName(self, test_list_id):
    """Returns the test list config file corresponding to `test_list_id`."""
    return test_list_id + self.CONFIG_SUFFIX

  def _GetArgsConfigName(self, test_list_id):
    """Returns the test argument config file corresponding to `test_list_id`."""
    return test_list_id + self.ARGS_CONFIG_SUFFIX

  def FindTestListIDs(self):
    suffix = self.CONFIG_SUFFIX + '.json'
    return [os.path.basename(p)[:-len(suffix)] for p in
            glob.iglob(os.path.join(self.config_dir, '*' + suffix))]


class CheckerError(Exception):
  """An exception raised by `Checker`"""


class TestListExpressionVisitor(ast.NodeVisitor):
  """Collects free variables of an expression.

  Usage::

    collector = TestListExpressionVisitor()
    collector.visit(ast_node)

  ast_node should be a single ast.Expression.
  """
  def __init__(self):
    super(TestListExpressionVisitor, self).__init__()
    self.free_vars = set()
    self.bounded_vars = set()

  def visit_Name(self, node):
    if isinstance(node.ctx, ast.Load) and node.id not in self.bounded_vars:
      self.free_vars.add(node.id)
    elif isinstance(node.ctx, ast.Store):
      self.bounded_vars.add(node.id)
    self.generic_visit(node)

  def visit_ListComp(self, node):
    self._VisitComprehension(node)

  def visit_SetComp(self, node):
    self._VisitComprehension(node)

  def visit_DictComp(self, node):
    self._VisitComprehension(node)

  def _VisitComprehension(self, node):
    """visit a XXXComp object.

    We override default behavior because we need to make sure elements and
    generators are visited in correct order (generators first, and then
    elements)

    `node` is either a `ListComp` or `DictComp` or `SetComp` object.
    """
    bounded_vars_bak = copy.copy(self.bounded_vars)

    if isinstance(node, ast.DictComp):
      elements = [node.key, node.value]
    else:
      elements = [node.elt]

    for generator in node.generators:
      self.visit(generator)
    for element in elements:
      self.visit(element)

    # The target variables defined in list comprehension pollutes local
    # namespace while set comprehension and dict comprehension doesn't.
    # e.g. ([x for x in [1]], x) ==> ([1], 1)
    #      ({x for x in [1]}, x) ==> x is undefined
    #      ({x: 1 for x in [1]}, x) ==> x is undefined
    # We *can* implement this behavior, but it would be more simple if we assume
    # that target variables in comprehension can't pollute local namespace.
    # Otherwise we need to handle corner cases like:
    #
    #   {x for u in {(x, y) for y in [x for x in [1]]}} === set([1])
    #   {y for u in {(x, y) for y in [x for x in [1]]}} ==> undefined y
    #
    # Restore self.bounded_vars.
    self.bounded_vars = bounded_vars_bak

  # Reject nodes we don't like
  # Lambda is invalid because we cannot serialize a lambda function.
  def visit_Lambda(self, node):
    del node  # unused
    raise CheckerError('lambda function is not allowed')

  # GeneratorExp is invalid because we cannot serialize it.
  def visit_GeneratorExp(self, node):
    del node  # unused
    raise CheckerError('generator is not allowed')

  # Yield is invalid because you should not be able to define a Yield
  # expression with only one line.
  def visit_Yield(self, node):
    del node  # unused
    raise CheckerError('yield is not allowed')


class Checker(object):
  """Check if a test list is valid.

  This class implements functions that help you to find test list errors
  *before* actually running tests in the test list.
  """
  _EXPRESSION_VALID_IDENTIFIERS = set(
      ['constants', 'options', 'dut', 'station', 'session'] +
      [key for key, unused_value in inspect.getmembers(__builtin__)])

  def AssertExpressionIsValid(self, expression):
    """Raise an expression if this expression is not allowed.

    The expression is a snippet of python code, which,

      * Is a single expression (not necessary single line, but the parsed result
        is a single expression)
      * Not all operators are allowed, you cannot use generator or create lambda
        functions.
      * When executing, the namespace would only contains:
        - built-in functions
        - "constants" and "options" defined by test list
        - "dut", "station" (to get information from DUT and station)
        - "session" (session is not implemented yet, it will represent a test
          session on a test station)

    This function will raise an exception if you are using an undefined
    variable, e.g. `[x for x in undefined_var]`.  We also assume that target
    variables in list comprehension does not leak into local namespace.
    Therefore, the expression `([x for x in [1]], x)` will be rejected, even
    though it is a valid expression in Python2.  See TestListExpressionVisitor
    for more details.

    Args:
      :type expression: basestring
    """
    try:
      syntax_tree = ast.parse(expression, mode='eval')
    except SyntaxError as e:
      raise CheckerError(e)

    collector = TestListExpressionVisitor()
    # collect all variables, might raise an exception if there are invalid nodes
    collector.visit(syntax_tree)
    undefined_identifiers = (
        collector.free_vars - self._EXPRESSION_VALID_IDENTIFIERS)

    if undefined_identifiers:
      raise CheckerError('undefined identifiers: %s' % undefined_identifiers)


class Manager(object):
  """Test List Manager.

  Attributes:
    test_configs: a dict maps a string (test list id) to loaded config file.
      Each loaded config file is just a json object, haven't been checked by
      `Checker` or merged with base test lists.
    test_lists: a dict maps a string (test list id) to loaded test list.
      Each loaded test list is a FactoryTestList object (or acts like one), have
      merged with base test lists and passed checker.
  """
  def __init__(self, loader=None, checker=None):
    self.loader = loader or Loader()
    self.checker = checker or Checker()

    self.test_lists = {}

  def GetTestListByID(self, test_list_id):
    if test_list_id in self.test_lists:
      if not self.test_lists[test_list_id].modified:
        return self.test_lists[test_list_id]

    config = self.loader.Load(test_list_id)
    if not config:
      # cannot load config file, return the value we currently have
      return self.test_lists.get(test_list_id, None)

    assert isinstance(config, TestListConfig)
    test_list = TestList(config, self.checker)
    self.test_lists[test_list_id] = test_list
    return test_list

  def GetTestListIDs(self):
    return self.test_lists.keys()

  def BuildAllTestLists(self, load_legacy_test_lists=True):
    failed_files = {}
    for test_list_id in self.loader.FindTestListIDs():
      logging.info('try to load test list: %s', test_list_id)
      try:
        self.GetTestListByID(test_list_id)
      except Exception:
        path = self.loader.GetConfigPath(test_list_id)
        logging.exception('Unable to import %s', path)
        failed_files[path] = sys.exc_info()

    if load_legacy_test_lists:
      legacy_test_lists, legacy_failed_files = self.BuildAllLegacyTestLists()

      for test_list_id, test_list in legacy_test_lists.iteritems():
        if test_list_id in self.test_lists:
          logging.warning('legacy test list "%s" is not loaded', test_list_id)
          legacy_failed_files[test_list.source_path] = (
              'legacy test list "%s" is not loaded' % test_list_id)
        else:
          self.test_lists[test_list_id] = test_list
      failed_files.update(legacy_failed_files)

    valid_test_lists = {}  # test lists that will be returned
    for test_list_id, test_list in self.test_lists.iteritems():
      # we don't need to check LegacyTestList, because they always have
      # subtests.
      if isinstance(test_list, TestList):
        # if the test list does not have subtests, don't return it.
        # (this is a base test list)
        if 'tests' not in test_list.ToTestListConfig():
          continue
      valid_test_lists[test_list_id] = test_list

    logging.info('loaded test lists: %r', self.test_lists.keys())
    return valid_test_lists, failed_files

  def BuildAllLegacyTestLists(self):
    """Build all legacy test lists (test lists in python)."""
    test_lists_, legacy_failed_files = test_lists.BuildAllTestLists()

    legacy_test_lists = {}

    for key, test_list in test_lists_.iteritems():
      legacy_test_lists[key] = LegacyTestList(test_list, self.checker)

    return legacy_test_lists, legacy_failed_files
