# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test list builder."""

import abc
import ast
import collections
import copy
import json
import logging
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.test import i18n
from cros.factory.test.i18n import translation
from cros.factory.test.rules import phase
from cros.factory.test import state
from cros.factory.test.state import TestState
from cros.factory.test.test_lists import test_object as test_object_module
from cros.factory.test.utils import selector_utils
from cros.factory.utils import config_utils
from cros.factory.utils import debug_utils
from cros.factory.utils import shelve_utils
from cros.factory.utils import type_utils


# String prefix to indicate this value needs to be evaluated
EVALUATE_PREFIX = 'eval! '

# String prefix to indicate this value needs to be translated
TRANSLATE_PREFIX = 'i18n! '

# used for loop detection
_DUMMY_CACHE = object()

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
  if obj.startswith(TRANSLATE_PREFIX):
    return i18n.Translated(obj[len(TRANSLATE_PREFIX):])
  else:
    return i18n.Translated(obj) if force else obj


class Options(object):
  """Test list options.

  These may be set by assigning to the options variable in a test list,
  e.g.::

    test_list.options.auto_run_on_start = False
  """
  # Allowable types for an option (defaults to the type of the default
  # value).
  _types = {}

  auto_run_on_start = True
  """If set to True, then the test list is automatically started when
  the test harness starts.  If False, then the operator will have to
  manually start a test."""

  retry_failed_on_start = False
  """If set to True, then the failed tests are automatically retried
  when the test harness starts. It is effective when auto_run_on_start
  is set to True."""

  clear_state_on_start = False
  """If set to True, the state of all tests is cleared each time the
  test harness starts."""

  auto_run_on_keypress = False
  """If set to True, the test harness will perform an auto-run whenever
  the operator switches to any test."""

  ui_locale = translation.DEFAULT_LOCALE
  """The default UI locale."""

  engineering_password_sha1 = None
  """SHA1 hash for a engineering password in the UI.  Use None to
  always enable engingeering mode.

  To enter engineering mode, an operator may press Ctrl-Alt-0 and
  enter this password.  Certain special functions in the UI (such as
  being able to arbitrarily run any test) will be enabled.  Pressing
  Ctrl-Alt-0 will exit engineering mode.

  In order to keep the password hidden from operator (even if they
  happen to see the test list file), the actual password is not stored
  in the test list; rather, a hash is.  To generate the hash, run:

  .. parsed-literal::

    echo -n `password` | sha1sum

  For example, for a password of ``test0000``, run::

    echo -n test0000 | sha1sum

  This will display a hash of ``266abb9bec3aff5c37bd025463ee5c14ac18bfca``,
  so you should set::

    test.list.options.engineering_password_sha1 = \
        '266abb9bec3aff5c37bd025463ee5c14ac18bfca'
  """
  _types['engineering_password_sha1'] = (type(None), str)

  sync_event_log_period_secs = None
  """Send events to the factory server when it is reachable at this
  interval.  Set to ``None`` to disable."""
  _types['sync_event_log_period_secs'] = (type(None), int)

  update_period_secs = None
  """Automatically check for updates at the given interval.  Set to
  ``None`` to disable."""
  _types['update_period_secs'] = (type(None), int)

  stop_on_failure = False
  """Whether to stop on any failure."""

  hooks_class = 'cros.factory.goofy.hooks.Hooks'
  """Hooks class for the factory test harness.  Defaults to a dummy class."""
  testlog_hooks = 'cros.factory.testlog.hooks.Hooks'
  """Hooks class for Testlog event. Defaults to a dummy class."""

  phase = None
  """Name of a phase to set.  If None, the phase is unset and the
  strictest (PVT) checks are applied."""
  _types['phase'] = (type(None), str)

  dut_options = {}
  """Options for DUT target.  Automatically inherits from parent node.
  Valid options include::

    {'link_class': 'LocalLink'},  # To run tests locally.
    {'link_class': 'ADBLink'},  # To run tests via ADB.
    {'link_class': 'SSHLink', 'host': TARGET_IP},  # To run tests over SSH.

  See :py:attr:`cros.factory.device.device_utils` for more information."""

  plugin_config_name = 'goofy_plugin_chromeos'
  """Name of the config to be loaded for running Goofy plugins."""

  _types['plugin_config_name'] = (type(None), str)

  read_device_data_from_vpd_on_init = True
  """Read device data from VPD in goofy._InitStates()."""

  skipped_tests = {}
  """A list of tests that should be skipped.
  The content of ``skipped_tests`` should be::

      {
        "<phase>": [ <pattern> ... ],
        "<run_if expr>": [ <pattern> ... ]
      }

  For example::

      {
          'PROTO': [
              'SMT.AudioJack',
              'SMT.SpeakerDMic',
              '*.Fingerprint'
          ],
          'EVT': [
              'SMT.AudioJack',
          ],
          'not device.component.has_touchscreen': [
              '*.Touchscreen'
          ],
          'device.factory.end_SMT': [
              'SMT'
          ]
      }

  If the pattern starts with ``*``, then it will match for all tests with same
  suffix.  For example, ``*.Fingerprint`` matches ``SMT.Fingerprint``,
  ``FATP.FingerPrint``, ``FOO.BAR.Fingerprint``.  But it does not match for
  ``SMT.Fingerprint_2`` (Generated ID when there are duplicate IDs).
  """

  waived_tests = {}
  """Tests that should be waived according to current phase.
  See ``skipped_tests`` for the format"""


  def CheckValid(self):
    """Throws a TestListError if there are any invalid options."""
    # Make sure no errant options, or options with weird types,
    # were set.
    default_options = Options()
    errors = []
    for key in sorted(self.__dict__):
      if not hasattr(default_options, key):
        errors.append('Unknown option %s' % key)
        continue

      value = getattr(self, key)
      allowable_types = Options._types.get(
          key, [type(getattr(default_options, key))])
      if not any(isinstance(value, x) for x in allowable_types):
        errors.append('Option %s has unexpected type %s (should be %s)' %
                      (key, type(value), allowable_types))
    if errors:
      raise type_utils.TestListError('\n'.join(errors))

  def ToDict(self):
    """Returns a dict containing all values of the Options.

    This include default values for keys not set on the Options.
    """
    result = {
        k: v
        for k, v in self.__class__.__dict__.iteritems() if k[0].islower()
    }
    result.update(self.__dict__)
    return result


class FactoryTestList(test_object_module.FactoryTest):
  """The root node for factory tests.

  Properties:
    path_map: A map from test paths to FactoryTest objects.
    source_path: The path to the file in which the test list was defined,
        if known.  For new-style test lists only.
  """

  def __init__(self, subtests, state_instance, options, test_list_id,
               label=None, finish_construction=True, constants=None):
    """Constructor.

    Args:
      subtests: A list of subtests (FactoryTest instances).
      state_instance: The state instance to associate with the list.
          This may be left empty and set later.
      options: A TestListOptions object.  This may be left empty
          and set later (before calling FinishConstruction).
      test_list_id: An optional ID for the test list.  Note that this is
          separate from the FactoryTest object's 'id' member, which is always
          None for test lists, to preserve the invariant that a test's
          path is always starts with the concatenation of all 'id's of its
          ancestors.
      label: An optional label for the test list.
      finish_construction: Whether to immediately finalize the test
          list.  If False, the caller may add modify subtests and options and
          then call FinishConstruction().
      constants: A type_utils.AttrDict object, which will be used to resolve
          'eval! ' dargs.  See test.test_lists.manager.ITestList.ResolveTestArgs
          for how it is used.
    """
    super(FactoryTestList, self).__init__(_root=True, subtests=subtests)
    self.state_instance = state_instance
    self.subtests = filter(None, type_utils.FlattenList(subtests))
    self.path_map = {}
    self.root = self
    self.test_list_id = test_list_id
    self.state_change_callback = None
    self.options = options
    self.label = label
    self.source_path = None
    self.constants = type_utils.AttrDict(constants or {})

    if finish_construction:
      self.FinishConstruction()

  def FinishConstruction(self):
    """Finishes construction of the test list.

    Performs final validity checks on the test list (e.g., resolve duplicate
    IDs, check if required tests exist) and sets up some internal data
    structures (like path_map).  This must be invoked after all nodes and
    options have been added to the test list, and before the test list is used.

    If finish_construction=True in the constructor, this is invoked in
    the constructor and the caller need not invoke it manually.

    When this function is called, self.state_instance might not be set
    (normally, it is set by goofy **after** FinishConstruction is called).

    Raises:
      TestListError: If the test list is invalid for any reason.
    """
    self._init(self.test_list_id + ':', self.path_map)

    # Resolve require_run paths to the actual test objects.
    for test in self.Walk():
      for requirement in test.require_run:
        requirement.test = self.LookupPath(
            self.ResolveRequireRun(test.path, requirement.path))
        if not requirement.test:
          raise type_utils.TestListError(
              "Unknown test %s in %s's require_run argument (note "
              'that full paths are required)'
              % (requirement.path, test.path))

    self.options.CheckValid()
    self._check()

  @staticmethod
  def ResolveRequireRun(test_path, requirement_path):
    """Resolve the test path for a requirement in require_run.

    If the path for the requirement starts with ".", then it will be
    interpreted as relative path to parent of test similar to Python's relative
    import syntax.

    For example:

     test_path | requirement_path | returned path
    -----------+------------------+---------------
     a.b.c.d   | e.f              | e.f
     a.b.c.d   | .e.f             | a.b.c.e.f
     a.b.c.d   | ..e.f            | a.b.e.f
     a.b.c.d   | ...e.f           | a.e.f
    """
    if requirement_path.startswith('.'):
      while requirement_path.startswith('.'):
        test_path = shelve_utils.DictKey.GetParent(test_path)
        requirement_path = requirement_path[1:]
      requirement_path = shelve_utils.DictKey.Join(test_path, requirement_path)
    return requirement_path

  def GetAllTests(self):
    """Returns all FactoryTest objects."""
    return self.path_map.values()

  def GetStateMap(self):
    """Returns a map of all FactoryTest objects to their TestStates."""
    # The state instance may return a dict (for the XML/RPC proxy)
    # or the TestState object itself. Convert accordingly.
    return dict(
        (self.LookupPath(k), TestState.FromDictOrObject(v))
        for k, v in self.state_instance.GetTestStates().iteritems())

  def LookupPath(self, path):
    """Looks up a test from its path."""
    if ':' not in path:
      path = self.test_list_id + ':' + path
    return self.path_map.get(path, None)

  def _UpdateTestState(self, path, **kwargs):
    """Updates a test state, invoking the state_change_callback if any.

    Internal-only; clients should call update_state directly on the
    appropriate TestState object.
    """
    ret, changed = self.state_instance.UpdateTestState(path=path, **kwargs)
    if changed and self.state_change_callback:
      self.state_change_callback(  # pylint: disable=not-callable
          self.LookupPath(path), ret)
    return ret

  def ToTestListConfig(self, recursive=True):
    """Output a JSON object that is a valid test_lists.schema.json object."""
    config = {
        'inherit': [],
        'label': self.label,
        'options': self.options.ToDict(),
        'constants': dict(self.constants),
    }
    if recursive:
      config['tests'] = [subtest.ToStruct() for subtest in self.subtests]
    return config

  def __repr__(self, recursive=False):
    if recursive:
      return json.dumps(self.ToTestListConfig(recursive=True), indent=2,
                        sort_keys=True, separators=(',', ': '))
    else:
      return json.dumps(self.ToTestListConfig(recursive=False), sort_keys=True)


class ITestList(object):
  """An interface of test list object."""

  __metaclass__ = abc.ABCMeta

  # Declare instance variables to make __setattr__ happy.
  _checker = None

  def __init__(self, checker):
    self._checker = checker

  @abc.abstractmethod
  def ToFactoryTestList(self):
    """Convert this object to a FactoryTestList object.

    Returns:
      :rtype: cros.factory.test.test_lists.test_list.FactoryTestList
    """
    raise NotImplementedError

  def CheckValid(self):
    """Check if this can be convert to a FactoryTestList object."""
    if not self.ToFactoryTestList():
      raise type_utils.TestListError('Cannot convert to FactoryTestList')

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
      locals_=None, state_proxy=None):
    self._checker.AssertValidArgs(test_args)

    if constants is None:
      constants = self.constants
    if options is None:
      options = self.options
    if state_proxy is None:
      state_proxy = state.GetInstance()
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
          return [
              ResolveArg('%s[%d]' % (key, i), v) for i, v in enumerate(value)
          ]

      if not isinstance(value, basestring):
        return value

      if value.startswith(EVALUATE_PREFIX):
        logging.debug('Resolving argument %s: %s', key, value)
        expression = value[len(EVALUATE_PREFIX):]  # remove prefix

        return self.EvaluateExpression(
            expression, dut, station, constants, options, locals_, state_proxy)

      return MayTranslate(value)
    return ConvertToBasicType(
        {k: ResolveArg(k, v) for k, v in test_args.iteritems()})

  @debug_utils.CatchException(_LOGGED_NAME)
  def SetSkippedAndWaivedTests(self):
    """Set skipped and waived tests according to phase and options.

    Since SKIPPED status is saved in state_instance, self.state_instance must be
    available at this moment.  This functions reads skipped_tests and
    waived_tests options from self.options, for the format of these options,
    please check `cros.factory.test.test_lists.test_list.Options`.
    """
    assert self.state_instance is not None

    current_phase = self.options.phase
    patterns = []

    def _AddPattern(pattern, action):
      pattern = pattern.split(':')[-1]  # To remove test_list_id
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
      test.Waive()

    _CollectPatterns(self.options.skipped_tests, _MarkSkipped)
    _CollectPatterns(self.options.waived_tests, _MarkWaived)

    for test_path, test in self.path_map.iteritems():
      test_path = test_path.split(':')[-1]  # To remove test_list_id
      for match, action in patterns:
        if match(test_path):
          action(test)

  @staticmethod
  def EvaluateExpression(expression, dut, station, constants, options, locals_,
                         state_proxy):
    namespace = {
        'dut': dut,
        'station': station,
        'constants': constants,
        'options': options,
        'locals': locals_,
        'state_proxy': state_proxy,
        'device': state_proxy.data_shelf.device, }

    syntax_tree = ast.parse(expression, mode='eval')
    syntax_tree = NodeTransformer_AddGet(['device']).visit(syntax_tree)
    code_object = compile(syntax_tree, '<string>', 'eval')
    return eval(code_object, namespace)  # pylint: disable=eval-used

  @staticmethod
  def EvaluateRunIf(test, test_list):
    """Evaluate the run_if value of this test.

    Evaluates run_if argument to decide skipping the test or not.  If run_if
    argument is not set, the test will never be skipped.

    Args:
      test: a FactoryTest object whose run_if will be checked
      test_list: the test list which is currently running, will get
        state_instance and constants from it.

    Returns:
      True if this test should be run, otherwise False
    """
    return ITestList._EvaluateRunIf(
        test.run_if, test.path, test_list, default=True)

  @staticmethod
  def _EvaluateRunIf(run_if, source, test_list, default):
    """Real implementation of EvaluateRunIf.

    If anything went wrong, `default` will be returned.
    """
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
      syntax_tree = ast.parse(run_if, mode='eval')
      syntax_tree = NodeTransformer_AddGet(
          ['device', 'constant']).visit(syntax_tree)
      code_object = compile(syntax_tree, '<string>', 'eval')
      return eval(code_object, namespace)  # pylint: disable=eval-used
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


class NodeTransformer_AddGet(ast.NodeTransformer):
  """Given a list of names, we will call `Get` function for you.

  For example, name_list=['device']::

    "device.foo.bar"  ==> "device.foo.bar.Get(None)"

  where `None` is the default value for `Get` function.
  And `device.foo.bar.Get` will still be `device.foo.bar.Get`.
  """
  def __init__(self, name_list):
    super(NodeTransformer_AddGet, self).__init__()
    if not isinstance(name_list, list):
      name_list = [name_list]
    self.name_list = name_list

  def visit_Attribute(self, node):
    """Convert the attribute.

    An attribute node will be: `var.foo.bar.baz`, and the node we got is the
    last attribute node (that is, we will visit `var.foo.bar.baz`, not
    `var.foo.bar` or its prefix).  And NodeTransformer will not recursively
    process a node if it is processed, so we only need to worry about process a
    node twice.

    This will fail for code like::

      "eval! any(v.baz.Get() for v in [device.foo, device.bar])"

    But you can always rewrite it to::

      "eval! any(v for v in [device.foo.baz, device.bar.baz])"

    So it should be fine.
    """
    if isinstance(node.ctx, ast.Load) and node.attr != 'Get':
      v = node
      while isinstance(v, ast.Attribute):
        v = v.value
      if isinstance(v, ast.Name) and v.id in self.name_list:
        new_node = ast.Call(
            func=ast.Attribute(
                attr='Get',
                value=node,
                ctx=node.ctx),
            # Use `None` as default value
            args=[ast.Name(id='None', ctx=ast.Load())],
            kwargs=None,
            keywords=[])
        ast.copy_location(new_node, node)
        return ast.fix_missing_locations(new_node)
    return node


class TestList(ITestList):
  """A test list object represented by test list config.

  This object should act like a
  ``cros.factory.test.test_lists.test_list.FactoryTestList`` object.
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

  def __init__(self, config, checker, loader):
    super(TestList, self).__init__(checker)
    self._loader = loader
    self._config = config
    self._cached_test_list = None
    self._cached_options = None
    self._cached_constants = None
    self._state_instance = None
    self._state_change_callback = None

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

    self._cached_test_list = FactoryTestList(
        subtests, self._state_instance, options,
        test_list_id=self._config.test_list_id,
        label=MayTranslate(self._config['label'], force=True),
        finish_construction=True,
        constants=self.constants)

    # Handle override_args
    if 'override_args' in self._config:
      for key, override in self._config['override_args'].iteritems():
        test = self._cached_test_list.LookupPath(key)
        if test:
          config_utils.OverrideConfig(test.dargs, override)

    self._cached_test_list.state_change_callback = self._state_change_callback
    self._cached_test_list.source_path = self._config.source_path
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

    return getattr(test_object_module, class_name)(**kwargs)

  def ResolveTestObject(self, test_object, test_object_name, cache):
    """Returns a test object inherits all its parents field."""
    if test_object_name in cache:
      if cache[test_object_name] == _DUMMY_CACHE:
        raise type_utils.TestListError(
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
      raise type_utils.TestListError(
          '%s inherits %s, which is not defined' % (test_object_name,
                                                    parent_name))
    if parent_name == test_object_name:
      # this test object inherits itself, it means that this object is a class
      # defined in cros.factory.test.test_lists.test_object
      # just save the object and return
      cache[test_object_name] = test_object
      return test_object

    if test_object_name:
      cache[test_object_name] = _DUMMY_CACHE
      # syntax sugar, if id is not given, set id as test object name.
      #
      # According to test_object.py, considering I18n, the priority is:
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

  def ForceReload(self):
    """Bypass modification detection, force reload."""
    logging.info('Force reloading test list')
    self._Reload()

  @debug_utils.NoRecursion
  def _Reload(self):
    logging.debug('reloading test list %s', self._config.test_list_id)
    note = {
        'name': _LOGGED_NAME
    }

    try:
      new_config = self._loader.Load(self._config.test_list_id)

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
      self._PreventReload()

      note['level'] = 'WARNING'
      note['text'] = ('Failed to reload latest test list %s.' %
                      self._config.test_list_id)
    try:
      self._state_instance.AddNote(note)
    except Exception:
      pass

  def _PreventReload(self):
    """Update self._config to prevent reloading invalid test list."""
    self._config.UpdateDependTimestamp()

  @property
  def modified(self):
    """Return True if the test list is considered modified, need to be reloaded.

    self._config.timestamp is when was the config last modified, if the config
    file or any of config files it inherits is changed after the timestamp, this
    function will return True.

    Returns:
      True if the test list config is modified, otherwise False.
    """
    # Note that this method can't catch all kind of potential modification.
    # For example, this property won't become `True` if the user add an
    # additional test list in /var/factory/config/ to override an existing one.
    for config_file, timestamp in self._config.GetDepend().iteritems():
      if os.path.exists(config_file):
        if timestamp != os.stat(config_file).st_mtime:
          return True
      elif timestamp is not None:
        # the file doesn't exist, and we think it should exist
        return True
    return False

  @property
  def constants(self):
    self.ReloadIfModified()

    if self._cached_constants:
      return self._cached_constants
    self._cached_constants = type_utils.AttrDict(self._config['constants'])
    return self._cached_constants

  # the following functions / properties are required by goofy
  @property
  def options(self):
    self.ReloadIfModified()
    if self._cached_options:
      return self._cached_options

    self._cached_options = Options()

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
