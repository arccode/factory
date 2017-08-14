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
import numbers
import os
import sys
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test import factory
from cros.factory.test import i18n
from cros.factory.test.rules import phase
from cros.factory.test import state
from cros.factory.test.test_lists import test_lists
from cros.factory.test.utils import selector_utils
from cros.factory.utils import config_utils
from cros.factory.utils import debug_utils
from cros.factory.utils import type_utils


# used for loop detection
_DUMMY_CACHE = object()

_EVALUATE_PREFIX = 'eval! '

# logged name for debug_utils.CatchException
_LOGGED_NAME = 'TestListManager'


def MayTranslate(obj, force=False):
  """Translate a string if it starts with 'i18n! ' or force=True.

  Args:
    force: force translation even if the string does not start with 'i18n! '.

  Returns:
    A translation dict or string
  """
  if isinstance(obj, dict):
    return obj
  if not isinstance(obj, basestring):
    raise TypeError('not a string')
  prefix = 'i18n! '
  if obj.startswith(prefix):
    return i18n.Translated(obj[len(prefix):])
  else:
    return i18n.Translated(obj) if force else obj


class TestListConfig(object):
  """A loaded test list config.

  This is basically a wrapper for JSON object (the content loaded from test list
  JSON file), with some helper functions and caches.
  """
  def __init__(self, json_object, test_list_id, timestamp=None):
    self._json_object = json_object
    self._test_list_id = test_list_id
    self._timestamp = timestamp

  def GetParents(self):
    return [p[:-len(Loader.CONFIG_SUFFIX)]
            for p in self._json_object.get('depend', [])]

  @property
  def timestamp(self):
    """When the config was loaded."""
    return self._timestamp

  def SetTimestamp(self, value):
    """Update timestamp value.

    We are not using property.setter because normally you should not override
    timestamp.  Changing timestamp value might break modification detection and
    auto reloading.

    *** Don't do it unless you know what you are doing ***
    """
    assert isinstance(value, numbers.Real), "timestamp must be a number"
    self._timestamp = value

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

  def CheckValid(self):
    """Check if this can be convert to a FactoryTestList object."""
    if not self.ToFactoryTestList():
      raise factory.TestListError('Cannot convert to FactoryTestList')

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

  def ReloadIfModified(self):
    """Reloads the test list (when self.modified == True)."""
    # default behavior, does nothing
    return

  @abc.abstractproperty
  def constants(self):
    raise NotImplementedError

  def ResolveTestArgs(
      self, test_args, dut, station, constants=None, options=None,
      locals_=None):
    self._checker.AssertValidArgs(test_args)

    if constants is None:
      constants = self.constants
    if options is None:
      options = self.options
    locals_ = type_utils.AttrDict(locals_ or {})

    def ConvertToBasicType(value):
      if isinstance(value, collections.Mapping):
        return {k: ConvertToBasicType(v) for k, v in value.iteritems()}
      elif isinstance(value, basestring):
        return value
      elif isinstance(value, (list, tuple)):
        return type(value)(ConvertToBasicType(v) for v in value)
      elif isinstance(value, collections.Sequence):
        return [ConvertToBasicType(v) for v in value]
      else:
        return value

    def ResolveArg(key, value):
      if isinstance(value, collections.Mapping):
        return {k: ResolveArg('%s[%r]' % (key, k), v)
                for k, v in value.iteritems()}

      if isinstance(value, collections.Sequence):
        if not isinstance(value, basestring):
          # value is a list or tuple, but not a string.
          # TODO(pihsun): When all test lists are in JSON format, we won't have
          # tuple, so we can change below back to [].
          return type(value)(ResolveArg('%s[%d]' % (key, i), v)
                             for i, v in enumerate(value))

      if not isinstance(value, basestring):
        return value

      if value.startswith(_EVALUATE_PREFIX):
        logging.info('Resolving argument %s: %s', key, value)
        expression = value[len(_EVALUATE_PREFIX):]  # remove prefix

        return self.EvaluateExpression(
            expression, dut, station, constants, options, locals_)

      return MayTranslate(value)
    return ConvertToBasicType(
        {k: ResolveArg(k, v) for k, v in test_args.iteritems()})

  @debug_utils.CatchException(_LOGGED_NAME)
  def SetSkippedAndWaivedTests(self):
    """Set skipped and waived tests according to phase and options.

    Since SKIPPED status is saved in state_instance, self.state_instance must be
    available at this moment.  This functions reads skipped_tests and
    waived_tests options from self.options, for the format of these options,
    please check `cros.factory.test.factory.Options`.
    """
    assert self.state_instance is not None

    current_phase = self.options.phase
    patterns = []

    def _AddPattern(pattern, action):
      if pattern.startswith('*'):
        patterns.append((lambda s: s.endswith(pattern[1:]), action))
      else:
        patterns.append((lambda s: s == pattern, action))

    def _CollectPatterns(option, action):
      """Collect enabled patterns from test list options.

      Args:
        option: this should be `self.options.skipped_tests` or
          `self.options.waived_tests`
        action: the action that will be passed to _AddPattern
      """

      for key in option:
        if key in phase.PHASE_NAMES:
          if key != current_phase:
            continue
        else:  # Assume key is a run_if expression
          if not self._EvaluateRunIf(
              run_if=key,
              source='test list options',
              test_list=self,
              test_arg_env=None,
              default=False):
            continue

        for pattern in option[key]:
          _AddPattern(pattern, action)

    def _MarkSkipped(test):
      """Mark a test as skipped.

      The test (and its subtests) statuses will become SKIPPED if they were not
      PASSED.  And test.run_if will become constant false.  So Goofy will always
      skip it.
      """
      test.Skip(forever=True)

    def _MarkWaived(test):
      """Mark all test and its subtests as waived.

      subtests should also be waived, so that subtests will become
      FAILED_AND_WAIVED when failed.  And the status will be propagated to
      parents (this test).
      """
      for subtest in test.Walk():
        subtest.waived = True

    _CollectPatterns(self.options.skipped_tests, _MarkSkipped)
    _CollectPatterns(self.options.waived_tests, _MarkWaived)

    for test_path, test in self.path_map.iteritems():
      for match, action in patterns:
        if match(test_path):
          action(test)

  @staticmethod
  def EvaluateExpression(expression, dut, station, constants, options, locals_):
    namespace = {
        'dut': dut,
        'station': station,
        'constants': constants,
        'options': options,
        'locals': locals_,
        'state_proxy': state.get_instance(), }
    return eval(expression, namespace)  # pylint: disable=eval-used

  @staticmethod
  def EvaluateRunIf(test, test_list, test_arg_env):
    """Evaluate the run_if value of this test.

    Evaluates run_if argument to decide skipping the test or not.  If run_if
    argument is not set, the test will never be skipped.

    Args:
      test: a FactoryTest object whose run_if will be checked
      test_list: the test list which is currently running, will get
        state_instance and constants from it.
      test_arg_env: a cros.factory.goofy.invocation.TestArgEnv object

    Returns:
      True if this test should be run, otherwise False
    """
    return ITestList._EvaluateRunIf(
        test.run_if, test.path, test_list, test_arg_env, default=True)

  @staticmethod
  def _EvaluateRunIf(run_if, source, test_list, test_arg_env, default):
    """Real implementation of EvaluateRunIf.

    If anything went wrong, `default` will be returned.
    """
    # To support LegacyTestList
    if callable(run_if):
      logging.warning('%s is using callable run_if, try to use string instead',
                      source)
      try:
        return bool(run_if(test_arg_env))
      except Exception:
        logging.exception('Unable to evaluate run_if expression for %s', source)
        return default

    if not isinstance(run_if, basestring):
      # run_if is not a function, not a string, just return default value
      return default

    state_instance = test_list.state_instance
    namespace = {
        'device': selector_utils.DataShelfSelector(
            state_instance, key='device'),
        'constants': selector_utils.DictSelector(value=test_list.constants),
    }
    try:
      return bool(eval(run_if, namespace))  # pylint: disable=eval-used
    except Exception:
      logging.exception('Unable to evaluate run_if %r for %s', run_if, source)
      return default

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
  _loader = None
  _config = None
  _state_instance = None
  _state_change_callback = None

  # variables starts with '_cached_' will be cleared by ReloadIfModified
  _cached_test_list = None
  _cached_options = None
  _cached_constants = None

  def __init__(self, config, checker=None, loader=None):
    super(TestList, self).__init__(checker)
    self._loader = loader or Loader()
    self._config = config
    self._cached_test_list = None
    self._cached_options = None
    self._cached_constants = None
    self._state_instance = None
    self._state_change_callback = None

  @debug_utils.CatchException(_LOGGED_NAME)
  def ToFactoryTestList(self):
    self.ReloadIfModified()
    if self._cached_test_list:
      return self._cached_test_list
    return self._ConstructFactoryTestList()

  @debug_utils.NoRecursion
  def _ConstructFactoryTestList(self):
    subtests = []
    cache = {}
    for test_object in self._config['tests']:
      subtests.append(self.MakeTest(test_object, cache))

    # this might cause recursive call if self.options is not implemented
    # correctly.  Put it in a single line for easier debugging.
    options = self.options

    self._cached_test_list = factory.FactoryTestList(
        subtests, self._state_instance, options,
        test_list_id=self._config.test_list_id,
        label=MayTranslate(self._config['label'], force=True),
        finish_construction=True)

    # Handle override_args
    if 'override_args' in self._config:
      for key, override in self._config['override_args'].iteritems():
        test = self._cached_test_list.LookupPath(key)
        if test:
          config_utils.OverrideConfig(test.dargs, override)

    self._cached_test_list.state_change_callback = self._state_change_callback
    return self._cached_test_list

  def MakeTest(self,
               test_object,
               cache,
               default_action_on_failure=None,
               locals_=None):
    """Convert a test_object to a FactoryTest object."""

    test_object = self.ResolveTestObject(
        test_object=test_object,
        test_object_name=None,
        cache=cache)

    if locals_ is None:
      locals_ = {}

    if 'locals' in test_object:
      locals_ = config_utils.OverrideConfig(
          locals_,
          self.ResolveTestArgs(
              test_object.pop('locals'),
              dut=None,
              station=None,
              locals_=locals_),
          copy_on_write=True)

    if not test_object.get('action_on_failure', None):
      test_object['action_on_failure'] = default_action_on_failure
    default_action_on_failure = test_object.pop('child_action_on_failure',
                                                default_action_on_failure)
    kwargs = copy.deepcopy(test_object)
    class_name = kwargs.pop('inherit', 'FactoryTest')

    subtests = []
    for subtest in test_object.get('subtests', []):
      subtests.append(self.MakeTest(
          subtest, cache, default_action_on_failure, locals_))

    # replace subtests
    kwargs['subtests'] = subtests
    kwargs['dargs'] = kwargs.pop('args', {})
    kwargs['locals_'] = locals_
    kwargs.pop('__comment', None)

    if kwargs.get('label'):
      kwargs['label'] = MayTranslate(kwargs['label'], force=True)

    # check if expressions are valid.
    self._checker.AssertValidArgs(kwargs['dargs'])
    if 'run_if' in kwargs and isinstance(kwargs['run_if'], basestring):
      self._checker.AssertValidRunIf(kwargs['run_if'])

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
      # syntax sugar, if id is not given, set id as test object name.
      #
      # According to test/factory.py, considering I18n, the priority is:
      # 1. `label` must be specified, or it should come from pytest_name
      # 2. If not specified, `id` comes from label by stripping spaces and dots.
      # Resolved id may be changed in _init when there are duplicated id's found
      # in same path.
      #
      # However, in most of the case, test_object_name would be more like an ID,
      # for example,
      #     "ThermalSensors": {
      #       "pytest_name": "thermal_sensors"
      #     }
      # The label will be derived from pytest_name, "Thermal Sensors", while the
      # ID will be test_object_name, "ThermalSensors".
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

  def ReloadIfModified(self):
    if not self.modified:
      return
    self._Reload()

  @debug_utils.NoRecursion
  def _Reload(self):
    logging.debug('reloading test list %s', self._config.test_list_id)
    note = {
        'name': _LOGGED_NAME
    }

    try:
      new_config = self._loader.Load(self._config.test_list_id)

      if not new_config:
        raise factory.TestListError(
            'Syntax or schema error in %s' % self._config.test_list_id)

      # make sure the new test list is working, if it's not, will raise an
      # exception and self._config will not be changed.
      TestList(new_config, self._checker, self._loader).CheckValid()

      self._config = new_config
      for key in self.__dict__:
        if key.startswith('_cached_'):
          self.__dict__[key] = None
      note['level'] = 'INFO'
      note['text'] = ('Test list %s is reloaded.' % self._config.test_list_id)
    except Exception:
      logging.exception('Failed to reload latest test list %s.',
                        self._config.test_list_id)
      # update timestamp to prevent reloading the same incorrect file
      self._config.SetTimestamp(time.time())
      note['level'] = 'WARNING'
      note['text'] = ('Failed to reload latest test list %s.' %
                      self._config.test_list_id)
    try:
      self._state_instance.AddNote(note)
    except Exception:
      pass

  @property
  def modified(self):
    """Return True if the test list is considered modified, need to be reloaded.

    self._config.timestamp is when was the config last modified, if the config
    file or any of config files it inherits is changed after the timestamp, this
    function will return True.

    Returns:
      True if the test list config is modified, otherwise False.
    """
    return (self._config.timestamp <
            self._loader.GetConfigInheritTreeLastModifiedTime(
                self._config))

  @property
  def constants(self):
    self.ReloadIfModified()

    if self._cached_constants:
      return self._cached_constants
    self._cached_constants = type_utils.AttrDict(self._config['constants'])
    return self._cached_constants

  # the following functions / properties are required by goofy
  @property
  @debug_utils.CatchException(_LOGGED_NAME)
  def options(self):
    self.ReloadIfModified()
    if self._cached_options:
      return self._cached_options

    self._cached_options = factory.Options()

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
      setattr(self._cached_options, key, value)

    self._cached_options.CheckValid()
    return self._cached_options

  @property
  def state_instance(self):
    return self._state_instance

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
    return self.test_list.constants

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

  @debug_utils.CatchException(_LOGGED_NAME)
  def Load(self, test_list_id, allow_inherit=True):
    """Loads test list config by test list ID.

    Returns:
      :rtype: TestListConfig
    """
    config_name = self._GetConfigName(test_list_id)
    try:
      loaded_config = config_utils.LoadConfig(
          config_name=config_name,
          schema_name=self.schema_name,
          validate_schema=True,
          default_config_dir=self.config_dir,
          allow_inherit=allow_inherit,
          generate_depend=allow_inherit)
    except Exception:
      logging.exception('Cannot load test list "%s"', test_list_id)
      return None

    loaded_config = TestListConfig(
        json_object=loaded_config,
        test_list_id=test_list_id)

    if allow_inherit:
      timestamp = self.GetConfigInheritTreeLastModifiedTime(loaded_config)
    else:
      timestamp = self.GetConfigLastModifiedTime(test_list_id)

    loaded_config.SetTimestamp(timestamp)
    return loaded_config

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

  def GetConfigLastModifiedTime(self, test_list_id):
    return os.stat(self.GetConfigPath(test_list_id)).st_mtime

  def GetConfigInheritTreeLastModifiedTime(self, loaded_config):
    last_modified_time = 0
    for test_list_id in loaded_config.GetParents():
      last_modified_time = max(
          last_modified_time,
          self.GetConfigLastModifiedTime(test_list_id))
    return last_modified_time


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
  _EVAL_VALID_IDENTIFIERS = set(
      ['constants', 'options', 'dut', 'station', 'state_proxy', 'locals'] +
      [key for key, unused_value in inspect.getmembers(__builtin__)])

  _RUN_IF_VALID_IDENTIFIERS = set(
      ['constants', 'device'] +
      [key for key, unused_value in inspect.getmembers(__builtin__)])

  def AssertValidArgs(self, args):
    """Check if the "eval! " expressions in an argument is valid."""
    if not isinstance(args, dict):
      return

    for value in args.itervalues():
      if isinstance(value, basestring):
        if value.startswith(_EVALUATE_PREFIX):
          self.AssertValidEval(value[len(_EVALUATE_PREFIX):])
      else:
        self.AssertValidArgs(value)

  def AssertValidEval(self, expression):
    """Check if an expression from "eval! ..." is valid.

    This function calls `self.AssertExpressionIsValid` to parse and collect free
    variables in the expression.  We only allows the following identifiers:
      - built-in functions
      - "constants" and "options" defined by test list
      - "dut", "station" (to get information from DUT and station)
      - "state_proxy" (state server proxy returned by state.get_instance())

    Args:
      :type expression: basestring
    """
    return self._AssertValidExpression(
        expression, self._EVAL_VALID_IDENTIFIERS)

  def AssertValidRunIf(self, run_if):
    return self._AssertValidExpression(run_if, self._RUN_IF_VALID_IDENTIFIERS)

  def _AssertValidExpression(self, expression, valid_identifiers):
    """Raise an expression if this expression is not allowed.

    The expression is a snippet of python code, which,

      * Is a single expression (not necessary single line, but the parsed result
        is a single expression)
      * Not all operators are allowed, you cannot use generator or create lambda
        functions.

    This function will raise an exception if you are using an undefined
    variable, e.g. `[x for x in undefined_var]`.  We also assume that target
    variables in list comprehension does not leak into local namespace.
    Therefore, the expression `([x for x in [1]], x)` will be rejected, even
    though it is a valid expression in Python2.  See TestListExpressionVisitor
    for more details.

    Collected free variables must be a subset of `valid_identifiers`.

    Args:
      :type expression: basestring
      :type valid_identifiers: set
    """
    try:
      syntax_tree = ast.parse(expression, filename=repr(expression),
                              mode='eval')
    except SyntaxError as e:
      raise CheckerError(e)

    collector = TestListExpressionVisitor()
    # collect all variables, might raise an exception if there are invalid nodes
    collector.visit(syntax_tree)
    undefined_identifiers = (collector.free_vars - valid_identifiers)

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
    """Get test list by test list ID.

    Args:
      test_list_id: ID of the test list

    Returns:
      a TestList object if the corresponding test list config is loaded
      successfully, otherwise None.
    """
    if test_list_id in self.test_lists:
      self.test_lists[test_list_id].ReloadIfModified()
      return self.test_lists[test_list_id]

    config = self.loader.Load(test_list_id)
    if not config:
      # cannot load config file, return the value we currently have
      return self.test_lists.get(test_list_id, None)

    if not isinstance(config, TestListConfig):
      logging.critical('Loader is not returning a TestListConfig instance')
      return None

    try:
      test_list = TestList(config, self.checker, self.loader)
      self.test_lists[test_list_id] = test_list
    except Exception:
      logging.critical('Failed to build test list %r from config',
                       test_list_id)
    return self.test_lists.get(test_list_id, None)

  def GetTestListIDs(self):
    return self.test_lists.keys()

  def BuildAllTestLists(self, load_legacy_test_lists=True):
    failed_files = {}
    for test_list_id in self.loader.FindTestListIDs():
      logging.info('try to load test list: %s', test_list_id)
      try:
        test_list = self.GetTestListByID(test_list_id)
        if test_list is None:
          raise factory.TestListError('failed to load test list')
      except Exception:
        path = self.loader.GetConfigPath(test_list_id)
        logging.exception('Unable to import %s', path)
        failed_files[path] = sys.exc_info()

    if load_legacy_test_lists:
      legacy_test_lists, legacy_failed_files = self.BuildAllLegacyTestLists()

      for test_list_id, test_list in legacy_test_lists.iteritems():
        if test_list_id in self.test_lists:
          logging.warning('legacy test list "%s" is not loaded', test_list_id)
          try:
            raise factory.TestListError(
                'legacy test list "%s" is not loaded' % test_list_id)
          except Exception:
            legacy_failed_files[test_list.source_path] = sys.exc_info()
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
        try:
          test_list.CheckValid()
        except Exception:
          path = self.loader.GetConfigPath(test_list_id)
          logging.exception('test list %s is invalid', path)
          failed_files[path] = sys.exc_info()
      valid_test_lists[test_list_id] = test_list

    logging.info('loaded test lists: %r', self.test_lists.keys())
    return valid_test_lists, failed_files

  def BuildAllLegacyTestLists(self):
    """Build all legacy test lists (test lists in python)."""
    test_lists_, legacy_failed_files = test_lists.BuildAllTestLists(True)

    legacy_test_lists = {}

    for key, test_list in test_lists_.iteritems():
      legacy_test_lists[key] = LegacyTestList(test_list, self.checker)

    return legacy_test_lists, legacy_failed_files
