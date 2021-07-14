# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common types and routines for factory test infrastructure.

This library provides common types and routines for the factory test
infrastructure. This library explicitly does not import gtk, to
allow its use by the autotest control process.
"""

import itertools
import json
import logging
import re

from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test.i18n import translation
from cros.factory.test.state import TestState
from cros.factory.utils import type_utils


# Regexp that all IDs should match.  Note that this allows leading digits
# (for tests like '3G').
ID_REGEXP = re.compile(r'^[a-zA-Z0-9]+$')

# Special value for require_run meaning "all tests".
ALL = 'all'


class RequireRun:
  """Requirement that a test has run (and optionally passed)."""

  def __init__(self, path, passed=True):
    """Constructor.

    Args:
      path: Path to the test that must have been run.  "ALL" is a valid value
          and refers to the root (all tests).
      passed: Whether the test is required to have passed.
    """
    # '' is the key of the root and will resolve to the root node.
    self.path = ('' if path == ALL else path)
    self.passed = passed
    # The test object will be resolved later (it is not available
    # upon creation).
    self.test = None


class FactoryTest:
  """A factory test object.

  Factory tests are stored in a tree. Each node has an id (unique
  among its siblings). Each node also has a path (unique throughout the
  tree), constructed by joining the IDs of all the test's ancestors
  with a '.' delimiter.

  Properties:
    Mostly the same as constructor args.
  """

  # If True, an unexpected reboot will not halt the pending tests
  allow_reboot = False

  # If True, the test can not be aborted.
  disable_abort = False

  # Fields of test_object defined by test_list.schema.json
  TEST_OBJECT_FIELDS = [
      'action_on_failure', 'args', 'disable_abort', 'disable_services',
      'enable_services', 'exclusive_resources', 'id', 'iterations',
      'label', 'allow_reboot', 'parallel', 'pytest_name', 'retries',
      'run_if', 'subtests', 'teardown', 'inherit', 'locals', ]

  ACTION_ON_FAILURE = type_utils.Enum(['STOP', 'NEXT', 'PARENT'])

  _PYTEST_LABEL_MAP = {
      'ac': 'AC',
      'als': 'ALS',
      'ec': 'EC',
      'ek': 'EK',  # acronym Endorsement Key in tpm_verify_ek
      'emmc': 'eMMC',
      'hwid': 'HWID',
      'id': 'ID',
      'led': 'LED',
      'lte': 'LTE',
      'sim': 'SIM',
      'ui': 'UI',
      'usb': 'USB',
  }

  def __init__(self,
               label=None,
               has_automator=False,
               pytest_name=None,
               dargs=None,
               locals_=None,
               dut_options=None,
               subtests=None,
               teardown=False,
               id=None,  # pylint: disable=redefined-builtin
               no_host=False,
               allow_reboot=None,
               disable_abort=None,
               exclusive_resources=None,
               enable_services=None,
               disable_services=None,
               require_run=None,
               run_if=None,
               iterations=1,
               retries=0,
               waived=False,
               parallel=False,
               layout=None,
               action_on_failure=None,
               _root=None):
    """Constructor.

    Args:
      label: An i18n label.
      pytest_name: The name of the pytest to run (relative to
        ``cros.factory.test.pytests``).
      dargs: pytest arguments.
      parallel: Whether the subtests should run in parallel.
      layout: The layout to be used for parallel test. Should be either a string
        or a dict like {"type": "tiled", "options": {"rows": 1, "columns": 2}}.
      subtests: A list of tests to run inside this test.  In order
        to make conditional construction easier, this may contain None items
        (which are removed) or nested arrays (which are flattened).
      id: A unique ID for the test.
      allow_reboot: True if allowing unexpected reboot.
      disable_abort: True if the test can not be aborted
        while it is running.
      exclusive_resources: Resources that the test may require exclusive access
        to. May be a list or a single string. Items must all be in
        ``cros.factory.goofy.plugins.plugin.RESOURCE``.
      enable_services: Services to enable for the test to run correctly.
      disable_services: Services to disable for the test to run correctly.
      require_run: A list of test paths indicating which tests must have been
        passed before this test may be run.  If the specified path includes this
        test, then all tests up to (but not including) this test must have been
        passed already.  For instance, if this test is ``STM.FlushTestlogs``,
        and require_run is ``SMT``, then all tests in SMT before
        ``FlushTestlogs`` must have already been passed.  ``"all"`` may be used
        to refer to the root (i.e., all tests in the whole test list before this
        one must already have been run).  Examples::

          require_run="x"             # These two are equivalent; requires that
          require_run=["x"]           # "X" has been passed.

          require_run=["x", "y"]      # Require both "X" and "Y" are passed.

          require_run=[".x", "..y"]   # Require "X" under same group and "Y"
                                      # under parent group to be passed.  See
                                      # ``FactoryTestList.ResolveRequireRun()``

          require_run="all"           # Require all tests before current test to
                                      # be passed.

      run_if: Condition under which the test should be run.  This
        must be either a function taking a single argument (an
        ``invocation.TestArgsEnv`` object), or a string of the format::

          table_name.col
          !table_name.col

        If the auxiliary table 'table_name' is available, then its column 'col'
        is used to determine whether the test should be run.
      iterations: Number of times to run the test.
      retries: Maximum number of retries allowed to pass the test.
        If it's 0, then no retries are allowed (the usual case). If, for
        example, iterations=60 and retries=2, then the test would be run up to
        62 times and could fail up to twice.
      _root: True only if this is the root node (for internal use
        only).
    """
    self.pytest_name = pytest_name

    self.subtests = list(filter(None, type_utils.FlattenList(subtests or [])))
    assert len(list(filter(None, [pytest_name, subtests]))) <= 1, (
        'Only one of pytest_name and subtests can be specified')

    # The next test under its parent, this value will be updated by
    # FactoryTestList object
    self.next_sibling = None

    self.has_automator = has_automator
    self.dargs = dargs or {}
    self.locals_ = locals_ or {}
    self.dut_options = dut_options or {}
    self.no_host = no_host
    self.waived = waived
    if isinstance(exclusive_resources, str):
      self.exclusive_resources = [exclusive_resources]
    else:
      self.exclusive_resources = exclusive_resources or []
    self._parallel = parallel
    layout = layout or {}
    if isinstance(layout, str):
      self.layout_type = layout
      self.layout_options = {}
    else:
      self.layout_type = layout.get('type', 'tab')
      self.layout_options = layout.get('options', {})
    self.action_on_failure = action_on_failure or self.ACTION_ON_FAILURE.NEXT
    if isinstance(enable_services, str):
      self.enable_services = [enable_services]
    else:
      self.enable_services = enable_services or []
    if isinstance(disable_services, str):
      self.disable_services = [disable_services]
    else:
      self.disable_services = disable_services or []

    require_run = require_run or []
    if not isinstance(require_run, list):
      # E.g., a single string or RequireRun object
      require_run = [require_run]
    # Turn strings into single RequireRun objects
    require_run = [RequireRun(x) if isinstance(x, str) else x
                   for x in require_run]
    assert (isinstance(require_run, list) and
            all(isinstance(x, RequireRun) for x in require_run)), (
                'require_run must be a list of RequireRun objects (%r)' %
                require_run)
    self.require_run = require_run

    self.run_if = run_if

    self._teardown = teardown
    self.path = ''
    self.parent = None
    self.root = None
    self.iterations = None
    self.retries = None
    self.SetIterationsAndRetries(iterations, retries)
    self.default_iterations = self.iterations
    self.default_retries = self.retries

    if allow_reboot is not None:
      self.allow_reboot = allow_reboot
    if disable_abort is not None:
      self.disable_abort = disable_abort

    # Solve ID and Label. Considering I18n, the priority is:
    # 1. `label` must be specified, or it should come from pytest_name
    # 2. If not specified, `id` comes from label by stripping spaces and dots.
    # Resolved id may be changed in _init when there are duplicated id's found
    # in same path.

    if label is None:
      # Auto-assign label text.
      if pytest_name:
        label = self.PytestNameToLabel(pytest_name)
      elif id:
        label = id
      else:
        label = _('Test Group')

    self.label = i18n.Translated(label)

    if _root:
      self.id = None
    else:
      self.id = id or self.LabelToId(self.label.get(translation.DEFAULT_LOCALE))

      assert self.id, (
          'id not specified for test: %r' % self)
      assert '.' not in self.id, (
          'id cannot contain a period: %r' % self)
      assert ID_REGEXP.match(self.id), (
          'id %r does not match regexp %s' % (
              self.id, ID_REGEXP.pattern))
      # Note that we check ID uniqueness in _init.

  def SetIterationsAndRetries(self, iterations, retries):
    """Sets iterations and retries if both input are valid."""
    if not isinstance(iterations, int) or iterations == 0 or iterations < -1:
      raise ValueError(
          'In test %s, Iterations must be a positive integer or -1, not %r' % (
              self.path, iterations))
    if not isinstance(retries, int) or retries < -1:
      raise ValueError(
          'In test %s, Retries must be a positive integer, 0, or -1, not %r' % (
              self.path, retries))
    self.iterations = float('inf') if iterations == -1 else iterations
    self.retries = float('inf') if retries == -1 else retries

  @staticmethod
  def PytestNameToLabel(pytest_name):
    """Returns a titled string without duplicated elements."""
    def _GuessIsAcronym(word):
      return not word.isalpha() or all(c not in 'aeiouy' for c in word)

    pytest_name = pytest_name.replace('.', ' ').replace('_', ' ')
    parts = []
    seen = set()
    for part in pytest_name.split():
      if part in seen:
        continue
      seen.add(part)
      parts.append(
          FactoryTest._PYTEST_LABEL_MAP.get(
              part, part.upper() if _GuessIsAcronym(part) else part.title()))
    return ' '.join(parts)

  @staticmethod
  def LabelToId(label):
    """Converts a label to an ID.

    Removes all symbols and join as CamelCase.
    """
    new_name = ''.join(c if c.isalnum() else ' ' for c in label)
    return ''.join(name.capitalize() if name[0].islower() else name
                   for name in new_name.split())

  def ToStruct(self, extra_fields=None, recursive=True):
    """Returns the node as a struct suitable for JSONification.

    Args:
      extra_fields: additional fields from FactoryTest object you'd like to
        include.  If this is provided, then the returned object might not match
        definition of test_list.scheme.json.

    Returns:
      A JSON serializable object that can is a test_object defined by
      test_list.schema.json.
    """
    fields = set(self.TEST_OBJECT_FIELDS + (extra_fields or []))

    struct = {
        k: getattr(self, k) for k in fields if hasattr(self, k)
    }

    # Fields that needs to remap
    struct['inherit'] = self.__class__.__name__
    struct['args'] = self.dargs.copy()
    struct['locals'] = self.locals_.copy()
    if self.iterations == float('inf'):
      struct['iterations'] = -1
    if self.retries == float('inf'):
      struct['retries'] = -1

    # Fields that need extra processing
    if recursive:
      struct['subtests'] = [
          subtest.ToStruct(extra_fields) for subtest in struct['subtests']]
    else:
      struct.pop('subtests', None)
    if callable(struct['run_if']):
      struct['run_if'] = '<lambda function>'
    for key in struct['args']:
      if callable(struct['args'][key]):
        struct['args'][key] = '<lambda function>'

    return struct

  def __repr__(self, recursive=False):
    if recursive:
      return json.dumps(self.ToStruct(recursive=True), indent=2,
                        separators=(',', ': '))
    return json.dumps(self.ToStruct(recursive=False))

  def _init(self, prefix, path_map):
    """Recursively assigns paths to this node and its children.

    Also adds this node to the root's path_map.
    """
    if self.parent:
      self.root = self.parent.root

    self.path = prefix + (self.id or '')
    if self.path in path_map:
      # duplicate test path, resolve it by appending an index,

      # first of all, count how many duplicated siblings
      count = 1
      for subtest in self.parent.subtests:
        if subtest == self:
          break
        # '_' will only appear when we try to resolve duplicate path issue,
        # so if the id contains '_', it must be followed by a number.
        if subtest.id.partition('_')[0] == self.id:
          count += 1
      assert count > 1
      # this is the new ID, since FactoryTest constructor will assert ID only
      # contains [a-zA-Z0-9], the new ID must be unique.
      self.id += '_' + str(count)
      self.path = prefix + (self.id or '')

    assert self.path not in path_map, 'Duplicate test path %s' % (self.path)
    path_map[self.path] = self

    # subtests of a teardown test should be part of teardown as well
    if self.teardown:
      if self.action_on_failure != self.ACTION_ON_FAILURE.NEXT:
        logging.warning(
            '%s: action_on_failure=%s, `action_on_failure` of a teardown test '
            'must be `NEXT`, the value will be overwritten.', self.path,
            self.action_on_failure)
        self.action_on_failure = self.ACTION_ON_FAILURE.NEXT
      for subtest in self.subtests:
        subtest.SetTeardown()

    for subtest in self.subtests:
      subtest.parent = self
      assert self.path, 'self.path should not be empty'
      # pylint: disable=protected-access
      if self.path[-1] == ':':
        subtest._init(self.path, path_map)
      else:
        subtest._init(self.path + '.', path_map)

    # next_sibling should point to next test
    for u, v in zip(self.subtests, self.subtests[1:]):
      u.next_sibling = v

  def _check(self):
    """recursively checks if each test are valid.

    1. Only leaf node tests can be group into a parallel test.
    2. Subtests of teardown tests should be marked as teardown as well.

    We assume that _init is called before _check, so properties are properly
    setup and propagated to child nodes.
    """
    if self.action_on_failure not in self.ACTION_ON_FAILURE:
      raise type_utils.TestListError(
          'action_on_failure must be one of "NEXT", "PARENT", "STOP"')

    if self.parallel:
      if not self.subtests:
        raise type_utils.TestListError(
            '`parallel` should be set on test group')
      for subtest in self.subtests:
        if not subtest.IsLeaf():
          raise type_utils.TestListError(
              'Test %s: all subtests in a parallel test should be leaf nodes' %
              self.id)
        if subtest.enable_services or subtest.disable_services:
          raise type_utils.TestListError(
              'Test %s cannot be parallel with enable_services or '
              'disable_services specified.' % subtest.id)

    # all subtests should come before teardown tests
    it = iter(self.subtests)
    if not self.teardown:
      # find first teardown test
      it = itertools.dropwhile(lambda subtest: not subtest.teardown, it)
    for subtest in it:
      if not subtest.teardown:
        raise type_utils.TestListError(
            '%s: all subtests should come before teardown tests' % self.id)

    for subtest in self.subtests:
      subtest._check()  # pylint: disable=protected-access

  def Depth(self):
    """Returns the depth of the node (0 for the root)."""
    return self.path.count('.') + (self.parent is not None)

  def IsLeaf(self):
    """Returns true if this is a leaf node."""
    return not self.subtests

  @property
  def parallel(self):
    return self._parallel

  @property
  def teardown(self):
    return self._teardown

  def SetTeardown(self, value=True):
    self._teardown = bool(value)

  def HasAncestor(self, other):
    """Returns True if other is an ancestor of this test (or is that test
    itself).
    """
    return (self == other) or (self.parent and self.parent.HasAncestor(other))

  def GetAncestors(self):
    """Returns list of ancestors, ordered by seniority."""
    if self.parent is not None:
      return self.parent.GetAncestors() + [self.parent]
    return []

  def GetAncestorGroups(self):
    """Returns list of ancestors that are groups, ordered by seniority."""
    return [node for node in self.GetAncestors() if node.IsGroup()]

  def GetState(self):
    """Returns the current test state from the state instance."""
    return TestState.FromDictOrObject(
        self.root.state_instance.GetTestState(self.path))

  def UpdateState(self, update_parent=True, status=None, **kwargs):
    """Updates the test state.

    See TestState.update for allowable kwargs arguments.
    """
    if status == TestState.UNTESTED:
      kwargs['shutdown_count'] = 0

    ret = TestState.FromDictOrObject(
        # pylint: disable=protected-access
        self.root._UpdateTestState(self.path, status=status, **kwargs))
    if update_parent and self.parent:
      self.parent.UpdateStatusFromChildren()
    return ret

  def UpdateStatusFromChildren(self):
    """Updates the status based on children's status.

    A test is active if any children are active; else failed if
    any children are failed; else untested if any children are
    untested; else passed.
    """
    if not self.subtests:
      return

    # If there are any active tests, consider it active; if any failed,
    # consider it failed, etc. The order is important!
    status = TestState.OverallStatus(
        [x.GetState().status for x in self.subtests])
    if status != self.GetState().status:
      self.UpdateState(status=status)

  def Walk(self, in_order=False):
    """Yields this test and each sub-test.

    Args:
      in_order: Whether to walk in-order. If False, walks depth-first.
    """
    if in_order:
      # Walking in order - yield self first.
      yield self
    for subtest in self.subtests:
      for f in subtest.Walk(in_order):
        yield f
    if not in_order:
      # Walking depth first - yield self last.
      yield self

  def IsGroup(self):
    """Returns true if this node is a test group."""
    return isinstance(self, TestGroup)

  def IsTopLevelTest(self):
    """Returns true if this node is a top-level test.

    A 'top-level test' is a test directly underneath the root or a
    TestGroup, e.g., a node under which all tests must be run
    together to be meaningful.
    """
    return ((not self.IsGroup()) and
            self.parent and
            (self.parent == self.root or self.parent.IsGroup()))

  def GetTopLevelParentOrGroup(self):
    if self.IsGroup() or self.IsTopLevelTest() or not self.parent:
      return self
    return self.parent.GetTopLevelParentOrGroup()

  def GetTopLevelTests(self):
    """Returns a list of top-level tests."""
    return [node for node in self.Walk() if node.IsTopLevelTest()]

  def GetExclusiveResources(self):
    """Returns a set of resources to be exclusively used."""
    res = set(self.exclusive_resources)
    if self.parent:
      res |= self.parent.GetExclusiveResources()
    return res

  def IsNoHost(self):
    """Returns true if the test or any parent is marked 'no_host'."""
    if self.no_host:
      return True
    return any([node.no_host for node in self.GetAncestorGroups()])

  def AsDict(self, state_map=None):
    """Returns this node and children in a dictionary suitable for
    YAMLification.
    """
    node = {'id': self.id or None, 'path': self.path or None}
    if not self.subtests and state_map:
      state = state_map[self.path]
      node['status'] = state.status
      node['count'] = state.count
      node['error_msg'] = state.error_msg or None
    if self.subtests:
      node['subtests'] = [x.AsDict(state_map) for x in self.subtests]
    return node

  def DisableByRunIf(self):
    """Overwrites properties related to run_if to disable a test.

    Makes self.run_if constant False.
    """
    self.run_if = 'False'

  def Skip(self, forever=False):
    """Skips this test and any subtests that have not already passed.

    Subtests that have passed are not modified.  If any subtests were
    skipped, this node (if not a leaf node) is marked as skipped as well.

    Args:
      forever: if this is True, will set run_if function to constant False,
        which will disable this pytest forever (until goofy restart).
    """
    if forever:
      self.DisableByRunIf()

    skipped_tests = []
    for test in self.Walk():
      if not test.subtests and test.GetState().status != TestState.PASSED:
        test.UpdateState(status=TestState.SKIPPED)
        skipped_tests.append(test.path)
    if skipped_tests:
      logging.info('Skipped tests %s', skipped_tests)
      if self.subtests:
        logging.info('Marking %s as skipped, since subtests were skipped',
                     self.path)
        self.UpdateState(status=TestState.SKIPPED)

  def Waive(self):
    """Waive this test and any subtests.

    If the test is 'FAILED' already, also update its status to
    'FAILED_AND_WAIVED'
    """
    self.waived = True

    for test in self.subtests:
      test.Waive()

    if self.GetState().status == TestState.FAILED:
      self.UpdateState(status=TestState.FAILED_AND_WAIVED)

  def IsSkipped(self):
    """Returns True if this test was skipped."""
    state = self.GetState()
    return state.status == TestState.SKIPPED

  def GetNextSibling(self):
    return self.next_sibling


class TestGroup(FactoryTest):
  """A collection of related tests, shown together in RHS panel if one is
  active.
  """


OperatorTest = FactoryTest


AutomatedSequence = FactoryTest


class ShutdownStep(FactoryTest):
  """A shutdown (halt, reboot, full_reboot, or direct_ec_reboot) step.

  Properties:
    iterations: The number of times to reboot.
    operation: The command to run to perform the shutdown (FULL_REBOOT,
        REBOOT, HALT, or DIRECT_EC_REBOOT).
  """

  ShutdownTypes = type_utils.Enum(
      ['reboot', 'full_reboot', 'halt', 'direct_ec_reboot'])

  allow_reboot = True

  def __init__(self, operation=None, **kwargs):
    super(ShutdownStep, self).__init__(**kwargs)
    assert not self.pytest_name, 'Reboot/halt steps may not have an pytest'
    assert not self.subtests, 'Reboot/halt steps may not have subtests'
    if not operation:
      operation = kwargs.get('dargs', {}).get('operation', None)
    self.pytest_name = 'shutdown'
    self.dargs = kwargs.get('dargs', {})
    self.dargs.update(dict(operation=operation))


class HaltStep(ShutdownStep):
  """Halts the machine."""

  def __init__(self, **kw):
    kw.setdefault('id', 'Halt')
    super(HaltStep, self).__init__(operation=ShutdownStep.ShutdownTypes.halt,
                                   **kw)


class RebootStep(ShutdownStep):
  """Reboots the machine."""

  def __init__(self, **kw):
    kw.setdefault('id', 'Reboot')
    super(RebootStep, self).__init__(
        operation=ShutdownStep.ShutdownTypes.reboot, **kw)


class FullRebootStep(ShutdownStep):
  """Fully reboots the machine."""

  def __init__(self, **kw):
    kw.setdefault('id', 'FullReboot')
    super(FullRebootStep, self).__init__(
        operation=ShutdownStep.ShutdownTypes.full_reboot, **kw)


AutomatedRebootSubTest = RebootStep


def FlattenGroup(subtests=None, **kwargs):
  kwargs.pop('locals_', None)  # handles by test list manager
  kwargs.pop('id', None)  # we don't care if it has id
  kwargs.pop('action_on_failure', None)  # injected by test list manager
  if not kwargs.get('dargs'):  # the default value is {}
    kwargs.pop('dargs', None)

  if kwargs:  # if we still have something not expected
    logging.warning('kwargs: %r will be ignored for FlattenGroup', kwargs)
  return type_utils.FlattenList(subtests or [])
