# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''
This library provides common types and routines for the factory test
infrastructure.  This library explicitly does not import gtk, to
allow its use by the autotest control process.

To log to the factory console, use:

  from autotest_lib.client.cros import factory
  factory.console.info('...')  # Or warn, or error
'''


import getpass
import logging
import os
import sys


def in_chroot():
    '''Returns True if currently in the chroot.'''
    return 'CROS_WORKON_SRCROOT' in os.environ


def get_log_root():
    '''Returns the root for logging and state.

    This is usually /var/log, or /tmp/factory.$USER if in the chroot, but may be
    overridden by the CROS_FACTORY_LOG_ROOT environment variable.
    '''
    ret = os.environ.get('CROS_FACTORY_LOG_ROOT')
    if ret:
        return ret
    if in_chroot():
        return '/tmp/factory.%s' % getpass.getuser()
    return '/var/log'


CONSOLE_LOG_PATH = os.path.join(get_log_root(), 'console.log')


_state_instance = None


def get_current_test_path():
    # Returns the path of the currently executing test, if any.
    return os.environ.get("CROS_FACTORY_TEST_PATH")


def get_lsb_data():
    """Reads all key-value pairs from system lsb-* configuration files."""
    # TODO(hungte) Re-implement using regex.
    # lsb-* file format:
    # [#]KEY="VALUE DATA"
    lsb_files = ('/etc/lsb-release',
                 '/usr/local/etc/lsb-release',
                 '/usr/local/etc/lsb-factory')
    def unquote(entry):
        for c in ('"', "'"):
            if entry.startswith(c) and entry.endswith(c):
                return entry[1:-1]
        return entry
    data = dict()
    for lsb_file in lsb_files:
        if not os.path.exists(lsb_file):
            continue
        with open(lsb_file, "rt") as lsb_handle:
            for line in lsb_handle.readlines():
                line = line.strip()
                if ('=' not in line) or line.startswith('#'):
                    continue
                (key, value) = line.split('=', 1)
                data[unquote(key)] = unquote(value)
    return data


def _init_console_log():
    handler = logging.FileHandler(CONSOLE_LOG_PATH, "a", delay=True)
    log_format = '[%(levelname)s] %(message)s'
    test_path = get_current_test_path()
    if test_path:
        log_format = test_path + ': ' + log_format
    handler.setFormatter(logging.Formatter(log_format))

    ret = logging.getLogger("console")
    ret.addHandler(handler)
    ret.setLevel(logging.INFO)
    return ret


console = _init_console_log()


def std_repr(obj, extra=[], excluded_keys=[], true_only=False):
    '''
    Returns the representation of an object including its properties.

    @param extra: Extra items to include in the representation.
    @param excluded_keys: Keys not to include in the representation.
    @param true_only: Whether to include only values that evaluate to
        true.
    '''
    # pylint: disable=W0102
    return (obj.__class__.__name__ + '(' +
            ', '.join(extra +
                      ['%s=%s' % (k, repr(getattr(obj, k)))
                       for k in sorted(obj.__dict__.keys())
                       if k[0] != '_' and k not in excluded_keys and
                       (not true_only or getattr(obj, k))])
            + ')')


def log(s):
    '''
    Logs a message to the console.  Deprecated; use the 'console'
    property instead.

    TODO(jsalz): Remove references throughout factory tests.
    '''
    console.info(s)


def get_state_instance():
    '''
    Returns a cached factory state client instance.
    '''
    # Delay loading modules to prevent circular dependency.
    import factory_common
    from autotest_lib.client.cros.factory import state
    global _state_instance  # pylint: disable=W0603
    if _state_instance is None:
        _state_instance = state.get_instance()
    return _state_instance


def get_shared_data(key, default=None):
    if not get_state_instance().has_shared_data(key):
        return default
    return get_state_instance().get_shared_data(key)


def set_shared_data(key, value):
    return get_state_instance().set_shared_data(key, value)


def has_shared_data(key):
    return get_state_instance().has_shared_data(key)


def del_shared_data(key):
    return get_state_instance().del_shared_data(key)


def read_test_list(path, state_instance=None):
    test_list_locals = {}
    # Import test classes into the evaluation namespace
    for (k, v) in dict(globals()).iteritems():
        if type(v) == type and issubclass(v, FactoryTest):
            test_list_locals[k] = v

    execfile(path, {}, test_list_locals)
    assert 'TEST_LIST' in test_list_locals, (
        'Test list %s does not define TEST_LIST' % path)

    return FactoryTestList(test_list_locals['TEST_LIST'],
                           state_instance or get_state_instance())


_inited_logging = False
def init_logging(prefix=None, verbose=False):
    '''
    Initializes logging.

    @param prefix: A prefix to display for each log line, e.g., the program
        name.
    @param verbose: True for debug logging, false for info logging.
    '''
    global _inited_logging  # pylint: disable=W0603
    assert not _inited_logging, "May only call init_logging once"
    _inited_logging = True

    if not prefix:
        prefix = os.path.basename(sys.argv[0])

    # Make sure that nothing else has initialized logging yet (e.g.,
    # autotest, whose logging_config does basicConfig).
    assert not logging.getLogger().handlers, (
        "Logging has already been initialized")

    logging.basicConfig(
        format=prefix + ': [%(levelname)s] %(asctime)s.%(msecs)03d %(message)s',
        level=logging.DEBUG if verbose else logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S')

    logging.debug('Initialized logging')


class TestState(object):
    '''
    The complete state of a test.

    @property status: The status of the test (one of ACTIVE, PASSED,
        FAILED, or UNTESTED).
    @property count: The number of times the test has been run.
    @property error_msg: The last error message that caused a test failure.
    @property shutdown_count: The next of times the test has caused a shutdown.
    @property visible: Whether the test is the currently visible test.
    '''
    ACTIVE = 'ACTIVE'
    PASSED = 'PASSED'
    FAILED = 'FAILED'
    UNTESTED = 'UNTESTED'

    def __init__(self, status=UNTESTED, count=0, visible=False, error_msg=None,
                 shutdown_count=0):
        self.status = status
        self.count = count
        self.visible = visible
        self.error_msg = error_msg
        self.shutdown_count = shutdown_count

    def __repr__(self):
        return std_repr(self)

    def update(self, status=None, increment_count=0, error_msg=None,
               shutdown_count=None, increment_shutdown_count=0, visible=None):
        '''
        Updates the state of a test.

        @param status: The new status of the test.
        @param increment_count: An amount by which to increment count.
        @param error_msg: If non-None, the new error message for the test.
        @param shutdown_count: If non-None, the new shutdown count.
        @param increment_shutdown_count: An amount by which to increment
            shutdown_count.
        @param visible: If non-None, whether the test should become visible.

        Returns True if anything was changed.
        '''
        old_dict = dict(self.__dict__)

        if status:
            self.status = status
        if error_msg is not None:
            self.error_msg = error_msg
        if shutdown_count is not None:
            self.shutdown_count = shutdown_count
        if visible is not None:
            self.visible = visible

        self.count += increment_count
        self.shutdown_count += increment_shutdown_count

        return self.__dict__ != old_dict

    @classmethod
    def from_dict_or_object(cls, obj):
        if type(obj) == dict:
            return TestState(**obj)
        else:
            assert type(obj) == TestState, type(obj)
            return obj


class FactoryTest(object):
    '''
    A factory test object.

    Factory tests are stored in a tree.  Each node has an id (unique
    among its siblings).  Each node also has a path (unique throughout the
    tree), constructed by joining the IDs of all the test's ancestors
    with a '.' delimiter.
    '''

    # If True, the test never fails, but only returns to an untested state.
    never_fails = False

    # If True, the test has a UI, so if it is active factory_ui will not
    # display the summary of running tests.
    has_ui = False

    REPR_FIELDS = ['id', 'autotest_name', 'dargs', 'backgroundable',
                   'never_fails']

    def __init__(self,
                 label_en='',
                 label_zh='',
                 autotest_name=None,
                 kbd_shortcut=None,
                 dargs=None,
                 backgroundable=False,
                 subtests=None,
                 id=None,                  # pylint: disable=W0622
                 has_ui=None,
                 never_fails=None,
                 _root=None):
        '''
        Constructor.

        @param label_en: An English label.
        @param label_zh: A Chinese label.
        @param autotest_name: The name of the autotest to run.
        @param kbd_shortcut: The keyboard shortcut for the test.
        @param dargs: Autotest arguments.
        @param backgroundable: Whether the test may run in the background.
        @param subtests: A list of tests to run inside this test.
        @param id: A unique ID for the test (defaults to the autotest name).
        @param has_ui: True if the test has a UI.  (This defaults to True for
            OperatorTest.)  If has_ui is not True, then when the test is
            running, the statuses of the test and its siblings will be shown in
            the test UI area instead.
        @param never_fails: True if the test never fails, but only returns to an
            untested state.
        @param _root: True only if this is the root node (for internal use
            only).
        '''
        self.label_en = label_en
        self.label_zh = label_zh
        self.autotest_name = autotest_name
        self.kbd_shortcut = kbd_shortcut.lower() if kbd_shortcut else None
        self.dargs = dargs or {}
        self.backgroundable = backgroundable
        self.subtests = subtests or []
        self.path = ''
        self.parent = None
        self.root = None

        if _root:
            self.id = None
        else:
            self.id = id or autotest_name
            assert self.id, (
                'Tests require either an id or autotest name: %r' % self)
            assert '.' not in self.id, (
                'id cannot contain a period: %r' % self)
            # Note that we check ID uniqueness in _init.

        if has_ui is not None:
            self.has_ui = has_ui
        if never_fails is not None:
            self.never_fails = never_fails

        # Auto-assign label text.
        if not self.label_en:
            if self.id and (self.id != self.autotest_name):
                self.label_en = self.id
            elif self.autotest_name:
                # autotest_name is type_NameInCamelCase.
                self.label_en = self.autotest_name.partition('_')[2]

        assert not (autotest_name and self.subtests), (
            'Test %s may not have both an autotest and subtests' % self.id)

    def __repr__(self, recursive=False):
        attrs = ['%s=%s' % (k, repr(getattr(self, k)))
                 for k in sorted(self.__dict__.keys())
                 if k in FactoryTest.REPR_FIELDS and getattr(self, k)]
        if recursive and self.subtests:
            indent = '    ' * (1 + self.path.count('.'))
            attrs.append(
                'subtests=[' +
                ('\n' +
                 ',\n'.join([subtest.__repr__(recursive)
                             for subtest in self.subtests]
                            )).replace('\n', '\n' + indent)
                + '\n]')

        return '%s(%s)' % (self.__class__.__name__, ', '.join(attrs))

    def _init(self, prefix, path_map):
        '''
        Recursively assigns paths to this node and its children.

        Also adds this node to the root's path_map.
        '''
        if self.parent:
            self.root = self.parent.root

        self.path = prefix + (self.id or '')
        assert self.path not in path_map, 'Duplicate test path %s' % (self.path)
        path_map[self.path] = self

        for subtest in self.subtests:
            subtest.parent = self
            subtest._init((self.path + '.' if len(self.path) else ''), path_map)

    def depth(self):
        '''
        Returns the depth of the node (0 for the root).
        '''
        return self.path.count('.') + (self.parent is not None)

    def is_leaf(self):
        '''
        Returns true if this is a leaf node.
        '''
        return not self.subtests

    def get_ancestors(self):
      '''
      Returns list of ancestors, ordered by seniority.
      '''
      if self.parent is not None:
        return self.parent.get_ancestors() + [self.parent]
      return []

    def get_ancestor_groups(self):
      '''
      Returns list of ancestors that are groups, ordered by seniority.
      '''
      return [node for node in self.get_ancestors() if node.is_group()]

    def get_state(self):
        '''
        Returns the current test state from the state instance.
        '''
        return TestState.from_dict_or_object(
            self.root.state_instance.get_test_state(self.path))

    def update_state(self, update_parent=True, status=None, **kw):
        '''
        Updates the test state.

        See TestState.update for allowable kw arguments.
        '''
        if self.never_fails and status == TestState.FAILED:
            status = TestState.UNTESTED

        ret = TestState.from_dict_or_object(
            self.root._update_test_state(  # pylint: disable=W0212
                self.path, status=status, **kw))
        if update_parent and self.parent:
            self.parent.update_status_from_children()
        return ret

    def update_status_from_children(self):
        '''
        Updates the status based on children's status.

        A test is active if any children are active; else failed if
        any children are failed; else untested if any children are
        untested; else passed.
        '''
        if not self.subtests:
            return

        statuses = set([x.get_state().status for x in self.subtests])

        # If there are any active tests, consider it active; if any failed,
        # consider it failed, etc.  The order is important!
        # pylint: disable=W0631
        for status in [TestState.ACTIVE, TestState.FAILED,
                       TestState.UNTESTED, TestState.PASSED]:
            if status in statuses:
                break

        if status != self.get_state().status:
            self.update_state(status=status)

    def walk(self, in_order=False):
        '''
        Yields this test and each sub-test.

        @param in_order: Whether to walk in-order.  If False, walks depth-first.
        '''
        if in_order:
            # Walking in order - yield self first.
            yield self
        for subtest in self.subtests:
            for f in subtest.walk(in_order):
                yield f
        if not in_order:
            # Walking depth first - yield self last.
            yield self

    def is_group(self):
        '''
        Returns true if this node is a test group.
        '''
        return isinstance(self, TestGroup)

    def is_top_level_test(self):
        '''
        Returns true if this node is a top-level test.

        A 'top-level test' is a test directly underneath the root or a
        TestGroup, e.g., a node under which all tests must be run
        together to be meaningful.
        '''
        return ((not self.is_group()) and
                self.parent and
                (self.parent == self.root or self.parent.is_group()))

class FactoryTestList(FactoryTest):
    '''
    The root node for factory tests.

    Properties:
        path_map: A map from test paths to FactoryTest objects.
    '''
    def __init__(self, subtests, state_instance):
        super(FactoryTestList, self).__init__(_root=True, subtests=subtests)
        self.state_instance = state_instance
        self.subtests = subtests
        self.path_map = {}
        self.root = self
        self.state_change_callback = None
        self._init('', self.path_map)

    def get_all_tests(self):
        '''
        Returns all FactoryTest objects.
        '''
        return self.path_map.values()

    def get_state_map(self):
        '''
        Returns a map of all FactoryTest objects to their TestStates.
        '''
        # The state instance may return a dict (for the XML/RPC proxy)
        # or the TestState object itself.  Convert accordingly.
        return dict(
            (self.lookup_path(k), TestState.from_dict_or_object(v))
            for k, v in self.state_instance.get_test_states().iteritems())

    def get_top_level_tests(self):
        '''
        Returns a list of top-level tests.
        '''
        return [node for node in self.walk()
                if node.is_top_level_test()]

    def lookup_path(self, path):
        '''
        Looks up a test from its path.
        '''
        return self.path_map.get(path, None)

    def _update_test_state(self, path, **kw):
        '''
        Updates a test state, invoking the state_change_callback if any.

        Internal-only; clients should call update_state directly on the
        appropriate TestState object.
        '''
        ret, changed = self.state_instance.update_test_state(path, **kw)
        if changed and self.state_change_callback:
            self.state_change_callback(  # pylint: disable=E1102
                self.lookup_path(path), ret)
        return ret


class TestGroup(FactoryTest):
    '''
    A collection of related tests, shown together in RHS panel if one is active.
    '''
    pass


class FactoryAutotestTest(FactoryTest):
    pass


class OperatorTest(FactoryAutotestTest):
    has_ui = True


AutomatedSequence = FactoryTest
AutomatedSubTest = FactoryAutotestTest


class ShutdownStep(AutomatedSubTest):
    '''A shutdown (halt or reboot) step.

    Properties:
        iterations: The number of times to reboot.
        operation: The command to run to perform the shutdown
            (REBOOT or HALT).
    '''
    REBOOT = 'reboot'
    HALT = 'halt'

    def __init__(self, operation, iterations=1, **kw):
        kw.setdefault('id', operation)
        super(ShutdownStep, self).__init__(**kw)
        assert not self.autotest_name, (
            'Reboot/halt steps may not have an autotest')
        assert not self.subtests, 'Reboot/halt steps may not have subtests'
        assert not self.backgroundable, (
            'Reboot/halt steps may not be backgroundable')
        assert iterations > 0
        self.iterations = iterations

        assert operation in [self.REBOOT, self.HALT]
        self.operation = operation


class HaltStep(ShutdownStep):
    '''Halts the machine.'''
    def __init__(self, **kw):
        super(HaltStep, self).__init__(operation=ShutdownStep.HALT, **kw)


class RebootStep(ShutdownStep):
    '''Reboots the machine.'''
    def __init__(self, **kw):
        super(RebootStep, self).__init__(operation=ShutdownStep.REBOOT, **kw)


AutomatedRebootSubTest = RebootStep
