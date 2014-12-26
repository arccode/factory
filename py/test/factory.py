# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common types and routines for factory test infrastructure.

This library provides common types and routines for the factory test
infrastructure. This library explicitly does not import gtk, to
allow its use by the autotest control process.

To log to the factory console, use:

 from cros.factory.test import factory
 factory.console.info('...') # Or warn, or error
"""

from __future__ import print_function

# pylint: disable=W0105

import getpass
import logging
import os
import re
import sys
import yaml

import factory_common # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.test.unicode_to_string import UnicodeToString
from cros.factory.utils import net_utils


SCRIPT_PATH = os.path.realpath(__file__)
CROS_FACTORY_LIB_PATH = os.path.dirname(SCRIPT_PATH)
FACTORY_PATH = os.path.realpath(os.path.join(CROS_FACTORY_LIB_PATH, '..', '..'))
FACTORY_PACKAGE_PATH = os.path.join(FACTORY_PATH, 'py_pkg', 'cros', 'factory')
CLIENT_PATH = FACTORY_PATH
FACTORY_MD5SUM_PATH = os.path.join(FACTORY_PATH, 'MD5SUM')
FIRMWARE_UPDATER_PATH = os.path.join(
    FACTORY_PATH, 'board', 'chromeos-firmwareupdate')

# Path to stateful partition on device.
DEVICE_STATEFUL_PATH = '/mnt/stateful_partition'

# Path for old-style test lists.
TEST_LISTS_PATH = os.path.join(FACTORY_PATH, 'test_lists')

# Name of Chrome data directory within the state directory.
CHROME_DATA_DIR_NAME = 'chrome-data-dir'

FACTORY_STATE_VERSION = 2

# Regexp that all IDs should match.  Currently we just warn if it doesn't
# match, for backward compatibility.  Note that this allows leading digits
# (for tests like '3G').
ID_REGEXP = re.compile(r'^\w+$')

# Special value for require_run meaning "all tests".
ALL = 'all'


# For compatibility; moved to utils.
in_chroot = utils.in_chroot


def get_factory_root(subdir=None):
  """Returns the root for logging and state.

  This is usually /var/log, or /tmp/factory.$USER if in the chroot, but may be
  overridden by the CROS_FACTORY_ROOT environment variable.

  Creates the directory it doesn't exist.

  Args:
   subdir: If not None, returns that subdirectory.
  """
  ret = (os.environ.get('CROS_FACTORY_ROOT') or
      (('/tmp/factory.%s' % getpass.getuser())
      if utils.in_chroot() else '/var/factory'))
  if subdir:
    ret = os.path.join(ret, subdir)
  utils.TryMakeDirs(ret)
  return ret


def get_log_root():
  """Returns the root for logs"""
  return get_factory_root('log')


def get_state_root():
  """Returns the root for all factory state."""
  return get_factory_root('state')


def get_test_data_root():
  """Returns the root for all test logs/state."""
  return get_factory_root('tests')


CONSOLE_LOG_PATH = os.path.join(get_log_root(), 'console.log')
FACTORY_LOG_PATH = os.path.join(get_log_root(), 'factory.log')

# Path to factory log on a "real" device.
FACTORY_LOG_PATH_ON_DEVICE = '/var/factory/log/factory.log'

_state_instance = None


def get_current_test_path():
  # Returns the path of the currently executing test, if any.
  return os.environ.get("CROS_FACTORY_TEST_PATH")


def get_current_test_metadata():
  """Returns metadata for the currently executing test, if any."""
  path = os.environ.get("CROS_FACTORY_TEST_METADATA")
  if not path or not os.path.exists(path):
    return {}

  with open(path) as f:
    return yaml.load(f)


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


def get_current_md5sum():
  """Returns MD5SUM of the current autotest directory.

  Returns None if there has been no update (i.e., unable to read
  the MD5SUM file).
  """
  if os.path.exists(FACTORY_MD5SUM_PATH):
    return open(FACTORY_MD5SUM_PATH, 'r').read().strip()
  else:
    return None


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


def get_verbose_log_file():
  """Returns an opened log file.

  Note that this returns a file instead of a logger (so the verbose log is not
  picked up by root logger.) Therefore, the caller is responsible for flushing
  and closing this file.

  The log file name will contain test invocation ID and thus this method
  can only be called from a test.
  """
  invocation = os.environ['CROS_FACTORY_TEST_INVOCATION']
  log_name = '%s-log-%s' % (get_current_test_path(), invocation)
  log_path = os.path.join(get_factory_root('log'), log_name)
  console.info('Raw log stored at %s', log_path)
  return open(log_path, 'a')


def std_repr(obj, extra=None, excluded_keys=None, true_only=False):
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


def log(message):
  """Logs a message to the console.

  Deprecated; use the 'console' property instead.

  TODO(jsalz): Remove references throughout factory tests.
  """
  console.info(message)


def get_state_instance():
  """Returns a factory state client instance."""
  # Delay loading modules to prevent circular dependency.
  from cros.factory.test import state  # pylint: disable=W0404
  return state.get_instance()


def get_shared_data(key, default=None):
  if not get_state_instance().has_shared_data(key):
    return default
  return get_state_instance().get_shared_data(key)


def set_shared_data(*key_value_pairs):
  return get_state_instance().set_shared_data(*key_value_pairs)


def has_shared_data(key):
  return get_state_instance().has_shared_data(key)


def del_shared_data(key):
  return get_state_instance().del_shared_data(key)


def read_test_list(path=None, state_instance=None, text=None):
  if len([x for x in [path, text] if x]) != 1:
    raise TestListError('Exactly one of path and text must be set')

  test_list_locals = {}

  # Import test classes into the evaluation namespace
  for (k, v) in dict(globals()).iteritems():
    if type(v) == type and issubclass(v, FactoryTest):
      test_list_locals[k] = v

  # Import types necessary to construct the test list.
  test_list_locals['WLAN'] = net_utils.WLAN
  test_list_locals['RequireRun'] = RequireRun
  test_list_locals['ALL'] = ALL

  # Add "Passed(x)" as an alias for "RequireRun(x, passed=True)", e.g.,
  #
  #   OperatorTest(..., require_run=Passed('a'))
  test_list_locals['Passed'] = lambda name: RequireRun(name, passed=True)

  # Add "LoadTestList(x)" allowing evaluation of another test list.
  def LoadTestList(name):
    path = os.path.join(FACTORY_PATH, 'test_lists', name)
    logging.info('LoadTestList: loading %s', path)
    execfile(path, test_list_locals)
  test_list_locals['LoadTestList'] = LoadTestList

  options = Options()
  test_list_locals['options'] = options

  if path:
    execfile(path, test_list_locals)
  else:
    exec text in test_list_locals
  assert 'TEST_LIST' in test_list_locals, (
    'Test list %s does not define TEST_LIST' % (path or '<text>'))

  options.check_valid()

  label_en = test_list_locals.get('TEST_LIST_NAME')
  if not label_en and path:
    label_en = os.path.basename(path)

  return FactoryTestList(
      test_list_locals['TEST_LIST'],
      state_instance or get_state_instance(),
      options,
      None,
      label_en)


_inited_logging = False
def init_logging(prefix=None, verbose=False):
  """Initializes logging.

  Args:
    prefix: A prefix to display for each log line, e.g., the program
      name.
    verbose: True for debug logging, false for info logging.
  """
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
    format=('[%(levelname)s] ' + prefix +
            ' %(filename)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
    level=logging.DEBUG if verbose else logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

  logging.debug('Initialized logging')


class Hooks(object):
  """Goofy hooks.

  This class is a dummy implementation, but methods may be overridden
  by the subclass.

  Properties (initialized by Goofy):
    test_list: The test_list object.
  """
  test_list = None

  def OnStartup(self):
    """Invoked on Goofy startup (just before the UI is started)."""
    pass

  def OnCreatedTestList(self):
    """Invoked right after Goofy creates test_list."""
    pass


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

  clear_state_on_start = False
  """If set to True, the state of all tests is cleared each time the
  test harness starts."""

  auto_run_on_keypress = False
  """If set to True, the test harness will perform an auto-run whenever
  the operator switches to any test."""

  ui_lang = 'en'
  """The default UI language (must be ``'en'`` for English or ``'zh'``
  for Chinese."""

  preserve_autotest_results = ['*.DEBUG', '*.INFO']
  """Discard all autotest results that do not match these globs."""

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


  wlans = []
  """WLANs that the connection manager may connect to."""

  sync_event_log_period_secs = None
  """Send events to the shopfloor server when it is reachable at this
  interval.  Set to ``None`` to disable."""
  _types['sync_event_log_period_secs'] = (type(None), int)

  update_period_secs = None
  """Automatically check for updates at the given interval.  Set to
  ``None`` to disable."""
  _types['update_period_secs'] = (type(None), int)

  scan_wifi_period_secs = 10
  """Scan wireless networks at the given interval."""

  shopfloor_timeout_secs = 10
  """Timeout when talking to shopfloor server for background
  operations."""

  time_sanitizer = True
  """Whether to enable the time sanitizer."""

  sync_time_period_secs = None
  """Interval to use when syncing time with the shopfloor server.
  Requires the time sanitizer."""
  _types['sync_time_period_secs'] = (type(None), int)

  log_disk_space_period_secs = 120
  """Interval at which to log disk usage stats."""
  _types['log_disk_space_period_secs'] = (type(None), int)

  check_battery_period_secs = 120
  """Interval at which to check battery status."""
  _types['check_battery_period_secs'] = (type(None), int)

  check_cpu_usage_period_secs = 120
  """Interval at which to check CPU usage."""
  _types['check_cpu_usage_period_secs'] = (type(None), int)

  warning_low_battery_pct = 10
  """Log warning event and try to sync with shopfloor server when
  battery level is lower than this value and AC charger is
  disconnected.  The option is effective only if
  :py:attr:`cros.factory.test.factory.Options.check_battery_period_secs`
  is not ``None``."""
  _types['warning_low_battery_pct'] = (type(None), int)

  critical_low_battery_pct = 5
  """Do low-power emergency handling (such as flushing disks) when
  battery level is lower than this value, regardless of AC charger
  status.  (The option is effective only if
  :py:attr:`cros.factory.test.factory.Options.check_battery_period_secs`
  is not ``None``)."""
  _types['critical_low_battery_pct'] = (type(None), int)

  scan_log_period_secs = 120
  """Time interval to scan system logs. A scan includes clearing logs
  in clear_log_paths and optionally syncing logs in sync_log_paths
  to shopfloor server if enable_sync_log is True and the time difference
  between this scan and last syncing event is greater than
  sync_log_period_secs.
  """
  _types['scan_log_period_secs'] = (int)

  clear_log_paths = [
      '/var/log/connectivity.log',
      '/var/log/connectivity.bak',
      '/var/log/net.log',
      '/var/log/net.*.log',
      '/var/log/messages*']
  """A list of log files to remove periodically."""

  clear_log_excluded_paths = ['/var/log/messages', '/var/log/messages.[12]']
  """A list of log files which will be excluded from clearing periodically."""

  sync_log_period_secs = None
  """Time interval to sync system logs in background. Set it to None to disable
  log syncing in background.
  """
  _types['sync_log_period_secs'] = (type(None), int)

  enable_sync_log = False
  """Sync system logs to the shopfloor server in foreground."""

  sync_log_paths = [
      '/var/factory/log/',
      '/var/log/messages',
      '/var/log/Xorg.0.log',
      '/var/log/bios_info.txt',
      '/var/log/ec_info.txt']
  """The list of log files to sync periodically."""
  _types['sync_log_paths'] = list

  core_dump_watchlist = None
  """The list of core dump pattern to watch for."""
  _types['core_dump_watchlist'] = (type(None), list)

  kick_sync_min_interval_secs = 120
  """The minimum interval between two kick syncs due to core dump files."""
  _types[kick_sync_min_interval_secs] = int

  stateful_usage_threshold = None
  """Upload stateful partition disk usage stats to shopfloor server if
  stateful partition disk usage is above threshold.  Checks bytes
  usage and inodes usage of /dev/mmcblk0p1 (or /dev/sda1) and
  /dev/mapper/encstateful.  The checking period is the same as
  :py:attr:`cros.factory.test.factory.Options.log_disk_space_period_secs`."""
  _types['stateful_usage_threshold'] = (type(None), int)

  stateful_usage_above_threshold_action = None
  """The action to perform when stateful partition disk usage is above
  the threshold specified by
  :py:attr:`cros.factory.test.factory.Options.stateful_usage_threshold`.
  The list will be passed to ``Spawn()`` as the first argument."""
  _types['stateful_usage_above_threshold_action'] = (type(None), list)

  enable_charge_manager = True
  """Whether to enable the charge manager."""

  min_charge_pct = None
  """The target range for the device's charge level. If
  :py:attr:`cros.factory.test.factory.Options.min_charge_pct` and
  :py:attr:`cros.factory.test.factory.Options.max_charge_pct` are set,
  Goofy will use ``ChargeManager`` to attempt to keep the battery
  charge within these thresholds."""
  _types['min_charge_pct'] = (type(None), int)
  max_charge_pct = None
  """See :py:attr:`cros.factory.test.factory.Options.min_charge_pct`."""
  _types['max_charge_pct'] = (type(None), int)

  shopfloor_server_url = None
  """The shopfloor server URL."""
  _types['shopfloor_server_url'] = (type(None), str)

  shopfloor_server_url_for_stage = {}
  """Test stage to shopfloor URL mapping."""

  stop_on_failure = False
  """Whether to stop on any failure."""

  disable_log_rotation = True
  """Disables (or Enables) log rotation by writing (or deleting)
  ``/var/lib/cleanup_logs_paused`` (see ``/usr/sbin/chromeos-cleanup-logs``).
  in goofy idle loops. Note that autotest harness disables log rotation.
  """

  disable_cros_shortcut_keys = False
  """Disable ChromeOS shortcut keys (see ``factory/tools/key_filter.py``)."""
  disable_caps_lock = False
  """Disable the CapsLock key."""
  caps_lock_keycode = 66
  """The CapsLock key code (used in conjunction with
  :py:attr:`cros.factory.test.factory.Options.disable_caps_lock`)."""

  hooks_class = 'cros.factory.test.factory.Hooks'
  """Hooks class for the factory test harness.  Defaults to a dummy
  class."""

  strict_ids = False
  """Strictly require an ID for each test."""

  use_cpufreq_manager = True
  """Enable ``CpufreqManager`` to manage CPU frequency."""

  check_if_mlb_changed = False
  """Check if MLB has been changed, and reset all tests if so."""

  phase = None
  """Name of a phase to set.  If None, the phase is unset and the
  strictest (PVT) checks are applied."""
  _types['phase'] = (type(None), str)

  def check_valid(self):
    """Throws a TestListError if there are any invalid options."""
    # Make sure no errant options, or options with weird types,
    # were set.
    default_options = Options()
    for key in sorted(self.__dict__):
      if key.startswith('_'):
        continue
      if not hasattr(default_options, key):
        raise TestListError('Unknown option %s' % key)

      value = getattr(self, key)
      allowable_types = Options._types.get(
          key, [type(getattr(default_options, key))])
      if not any(isinstance(value, x) for x in allowable_types):
        raise TestListError(
            'Option %s has unexpected type %s (should be %s)' % (
                key, type(value), allowable_types))


class TestState(object):
  """The complete state of a test.

  Properties:
    status: The status of the test (one of ACTIVE, PASSED,
      FAILED, or UNTESTED).
    count: The number of times the test has been run.
    error_msg: The last error message that caused a test failure.
    shutdown_count: The number of times the test has caused a shutdown.
    visible: Whether the test is the currently visible test.
    invocation: The currently executing invocation.
    iterations_left: For an active test, the number of remaining
      iterations after the current one.
    retries_left: Maximum number of retries allowed to pass the test.
  """
  ACTIVE = 'ACTIVE'
  PASSED = 'PASSED'
  FAILED = 'FAILED'
  UNTESTED = 'UNTESTED'
  FAILED_AND_WAIVED = 'FAILED_AND_WAIVED'

  # Error message used for tests that are considered passed only because
  # they have been skipped.
  SKIPPED_MSG = 'SKIPPED'

  def __init__(self, status=UNTESTED, count=0, visible=False, error_msg=None,
               shutdown_count=0, invocation=None, iterations_left=0,
               retries_left=0, skip=False):
    self.status = status
    self.count = count
    self.visible = visible
    self.error_msg = error_msg
    self.shutdown_count = shutdown_count
    self.invocation = invocation
    self.iterations_left = iterations_left
    self.retries_left = retries_left
    self.skip = skip

  def __repr__(self):
    return std_repr(self)

  def update(self, status=None, increment_count=0, error_msg=None,
             shutdown_count=None, increment_shutdown_count=0, visible=None,
             invocation=None,
             decrement_iterations_left=0, iterations_left=None,
             decrement_retries_left=0, retries_left=None,
             skip=None):
    """Updates the state of a test.

    Args:
      status: The new status of the test.
      increment_count: An amount by which to increment count.
      error_msg: If non-None, the new error message for the test.
      shutdown_count: If non-None, the new shutdown count.
      increment_shutdown_count: An amount by which to increment
        shutdown_count.
      visible: If non-None, whether the test should become visible.
      invocation: The currently executing or last invocation, if any.
      iterations_left: If non-None, the new iterations_left.
      decrement_iterations_left: An amount by which to decrement
        iterations_left.
      retries_left: If non-None, the new retries_left.
        The case retries_left = -1 means the test had already used the first try
        and all the retries.
      decrement_retries_left: An amount by which to decrement
        retries_left.
      skip: Whether the test should be skipped.

    Returns:
      True if anything was changed.
    """
    old_dict = dict(self.__dict__)

    if status:
      self.status = status
    if error_msg is not None:
      self.error_msg = error_msg
    if shutdown_count is not None:
      self.shutdown_count = shutdown_count
    if iterations_left is not None:
      self.iterations_left = iterations_left
    if retries_left is not None:
      self.retries_left = retries_left
    if visible is not None:
      self.visible = visible
    if skip is not None:
      self.skip = skip

    if invocation is not None:
      self.invocation = invocation

    self.count += increment_count
    self.shutdown_count += increment_shutdown_count
    self.iterations_left = max(
      0, self.iterations_left - decrement_iterations_left)
    # If retries_left is 0 after update, it is the usual case, so test
    # can be run for the last time. If retries_left is -1 after update,
    # it had already used the first try and all the retries.
    self.retries_left = max(
      -1, self.retries_left - decrement_retries_left)

    return self.__dict__ != old_dict

  @classmethod
  def from_dict_or_object(cls, obj):
    if type(obj) == dict:
      return TestState(**obj)
    else:
      assert type(obj) == TestState, type(obj)
      return obj


def overall_status(statuses):
  """Returns the "overall status" given a list of statuses.

  This is the first element of

    [ACTIVE, FAILED, UNTESTED, FAILED_AND_WAIVED, PASSED]

  (in that order) that is present in the status list.
  """
  status_set = set(statuses)
  for status in [TestState.ACTIVE, TestState.FAILED,
                 TestState.UNTESTED, TestState.FAILED_AND_WAIVED,
                 TestState.PASSED]:
    if status in status_set:
      return status

  # E.g., if statuses is empty
  return TestState.UNTESTED


class TestListError(Exception):
  """Test list error."""
  pass


class FactoryTestFailure(Exception):
  """Failure of a factory test.

  Args:
    message: The exception message.
    status: The status to report for the failure (usually FAILED
      but possibly UNTESTED).
  """
  def __init__(self, message=None, status=TestState.FAILED):
    super(FactoryTestFailure, self).__init__(message)
    self.status = status


class RequireRun(object):
  """Requirement that a test has run (and optionally passed)."""
  def __init__(self, path, passed=True):
    """Constructor.

    Args:
      path: Path to the test that must have been run.  "ALL" is
        a valid value and refers to the root (all tests).
      passed: Whether the test is required to have passed.
    """
    # '' is the key of the root and will resolve to the root node.
    self.path = ('' if path == ALL else path)
    self.passed = passed
    # The test object will be resolved later (it is not available
    # upon creation).
    self.test = None


class FactoryTest(object):
  """A factory test object.

  Factory tests are stored in a tree. Each node has an id (unique
  among its siblings). Each node also has a path (unique throughout the
  tree), constructed by joining the IDs of all the test's ancestors
  with a '.' delimiter.

  Properties:
    Mostly the same as constructor args.  Additionally:
      run_if_table_name: The table_name portion of the run_if ctor arg.
      run_if_col: The column name portion of the run_if ctor arg.
      run_if_not: Whether the sense of the argument is inverted.
      run_if_expr: A callable function (taking one argument, an
          invocation.TestArgEnv) that will return True if the test
          should be run.
      implicit_id: Whether the ID was determined implicitly (i.e., not
          explicitly specified in the test list).
  """

  # If True, the test never fails, but only returns to an untested state.
  never_fails = False

  # If True, the test can not be aborted.
  disable_abort = False

  # If True, the test has a UI, so if it is active factory_ui will not
  # display the summary of running tests.
  has_ui = False

  REPR_FIELDS = ['test_list_id', 'id', 'autotest_name', 'pytest_name', 'dargs',
                 'backgroundable', 'exclusive', 'never_fails',
                 'enable_services', 'disable_services', 'no_host']

  # Subsystems that the test may require exclusive access to.
  EXCLUSIVE_OPTIONS = utils.Enum(['NETWORKING', 'CHARGER', 'CPUFREQ'])

  RUN_IF_REGEXP = re.compile(r'^(!)?(\w+)\.(.+)$')

  def __init__(self,
               label_en='',
               label_zh='',
               has_automator=False,
               autotest_name=None,
               pytest_name=None,
               invocation_target=None,
               kbd_shortcut=None,
               dargs=None,
               backgroundable=False,
               subtests=None,
               id=None,  # pylint: disable=W0622
               has_ui=None,
               no_host=False,
               never_fails=None,
               disable_abort=None,
               exclusive=None,
               enable_services=None,
               disable_services=None,
               require_run=None,
               run_if=None,
               iterations=1,
               retries=0,
               prepare=None,
               finish=None,
               force_background=False,
               waived=False,
               _root=None,
               _default_id=None):
    """Constructor.

    See cros.factory.test.test_lists.FactoryTest for argument
    documentation.
    """
    self.label_en = label_en
    self.label_zh = (label_zh if isinstance(label_zh, unicode)
                     else label_zh.decode('utf-8'))
    self.has_automator = has_automator
    self.autotest_name = autotest_name
    self.pytest_name = pytest_name
    self.invocation_target = invocation_target
    # TODO(henryhsu): prepare and finish should support TestGroup also
    #    instead of test case only
    self.prepare = prepare
    self.finish = finish
    self.kbd_shortcut = kbd_shortcut.lower() if kbd_shortcut else None
    self.dargs = dargs or {}
    self.backgroundable = backgroundable
    self.force_background = force_background
    self.no_host = no_host
    self.waived = waived
    if isinstance(exclusive, str):
      self.exclusive = [exclusive]
    else:
      self.exclusive = exclusive or []
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

    self.run_if_table_name = None
    self.run_if_col = None
    self.run_if_not = False
    self.run_if_expr = None
    if callable(run_if):
      self.run_if_expr = run_if
    elif run_if:
      match = self.RUN_IF_REGEXP.match(run_if)
      assert match, ('In test %s, run_if value %r does not match %s',
                     self.path, run_if, self.RUN_IF_REGEXP.pattern)
      self.run_if_not = match.group(1) is not None
      self.run_if_table_name = match.group(2)
      self.run_if_col = match.group(3)

    self.subtests = filter(None, utils.FlattenList(subtests or []))
    self.path = ''
    self.parent = None
    self.root = None
    self.iterations = iterations
    assert isinstance(self.iterations, int) and self.iterations > 0, (
      'In test %s, Iterations must be a positive integer, not %r' % (
        self.path, self.iterations))
    self.retries = retries
    assert isinstance(self.retries, int) and self.retries >= 0, (
      'In test %s, Retries must be a positive integer or 0, not %r' % (
        self.path, self.retries))
    if _root:
      self.id = None
      self.implicit_id = False
    else:
      self.implicit_id = not id

      if id:
        self.id = id
      elif autotest_name:
        self.id = autotest_name
      elif pytest_name:
        self.id = self.pytest_name_to_id(pytest_name)
      else:
        self.id = _default_id

      assert self.id, (
          'id not specified for test: %r' % self)
      assert '.' not in self.id, (
          'id cannot contain a period: %r' % self)
      assert ID_REGEXP.match(self.id), (
          'id %r does not match regexp %s' % (
              self.id, ID_REGEXP.pattern))
      # Note that we check ID uniqueness in _init.

    assert len(filter(None, [autotest_name, pytest_name,
                             invocation_target, subtests])) <= 1, (
        'No more than one of autotest_name, pytest_name, '
        'invocation_target, and subtests must be specified')

    if has_ui is not None:
      self.has_ui = has_ui
    if never_fails is not None:
      self.never_fails = never_fails
    if disable_abort is not None:
      self.disable_abort = disable_abort

    # Auto-assign label text.
    if not self.label_en:
      if self.id and (self.id != self.autotest_name):
        self.label_en = self.id
      elif self.autotest_name:
        # autotest_name is type_NameInCamelCase.
        self.label_en = self.autotest_name.partition('_')[2]

    bogus_exclusive_items = set(self.exclusive) - self.EXCLUSIVE_OPTIONS
    assert not bogus_exclusive_items, (
        'In test %s, invalid exclusive options: %s (should be in %s)' %
        (self.id, bogus_exclusive_items, self.EXCLUSIVE_OPTIONS))
    assert not ((backgroundable or force_background) and (
        enable_services or disable_services)), (
        'Test %s may not be backgroundable with enable_services or '
        'disable_services specified.' % self.id)
    assert not (force_background and self.has_ui), (
        'Test %s may not have UI with force background.' % self.id)
    assert not (force_background and backgroundable), (
        'Test %s may not set backgroundable and force_background at '
        'the same time.' % self.id)

  @staticmethod
  def pytest_name_to_id(pytest_name):
    """Converts a pytest name to an ID.

    Removes all but the rightmost dot-separated component, removes
    underscores, and converts to CamelCase.
    """
    name = pytest_name.rpartition('.')[2]
    return re.sub('(?:^|_)([a-z])',
                  lambda match: match.group(1).upper(),
                  name)

  def to_struct(self):
    """Returns the node as a struct suitable for JSONification."""
    ret = dict(
        (k, getattr(self, k))
        for k in ['id', 'path', 'label_en', 'label_zh',
                  'kbd_shortcut', 'backgroundable', 'disable_abort'])
    ret['is_shutdown_step'] = isinstance(self, ShutdownStep)
    ret['subtests'] = [subtest.to_struct() for subtest in self.subtests]
    return ret


  def __repr__(self, recursive=False):
    attrs = ['%s=%s' % (k, repr(getattr(self, k)))
             for k in sorted(self.__dict__.keys())
             if k in FactoryTest.REPR_FIELDS and getattr(self, k)]
    if recursive and self.subtests:
      indent = '  ' * (1 + self.path.count('.'))
      attrs.append(
          'subtests=['
          + ('\n' + ',\n'.join([subtest.__repr__(recursive)
                                for subtest in self.subtests])
             ).replace('\n', '\n' + indent)
          + '\n]')

    return '%s(%s)' % (self.__class__.__name__, ', '.join(attrs))

  def _init(self, prefix, path_map):
    """Recursively assigns paths to this node and its children.

    Also adds this node to the root's path_map.
    """
    if self.parent:
      self.root = self.parent.root

    self.path = prefix + (self.id or '')
    assert self.path not in path_map, 'Duplicate test path %s' % (self.path)
    path_map[self.path] = self

    for subtest in self.subtests:
      subtest.parent = self
      # pylint: disable=W0212
      subtest._init((self.path + '.' if len(self.path) else ''), path_map)

  def depth(self):
    """Returns the depth of the node (0 for the root)."""
    return self.path.count('.') + (self.parent is not None)

  def is_leaf(self):
    """Returns true if this is a leaf node."""
    return not self.subtests

  def has_ancestor(self, other):
    """Returns True if other is an ancestor of this test (or is that test
    itself).
    """
    return (self == other) or (self.parent and self.parent.has_ancestor(other))

  def get_ancestors(self):
    """Returns list of ancestors, ordered by seniority."""
    if self.parent is not None:
      return self.parent.get_ancestors() + [self.parent]
    return []

  def get_ancestor_groups(self):
    """Returns list of ancestors that are groups, ordered by seniority."""
    return [node for node in self.get_ancestors() if node.is_group()]

  def get_state(self):
    """Returns the current test state from the state instance."""
    return TestState.from_dict_or_object(
      self.root.state_instance.get_test_state(self.path))

  def update_state(self, update_parent=True, status=None, **kwargs):
    """Updates the test state.

    See TestState.update for allowable kwargs arguments.
    """
    if self.never_fails and status == TestState.FAILED:
      status = TestState.UNTESTED

    if status == TestState.UNTESTED:
      kwargs['shutdown_count'] = 0

    ret = TestState.from_dict_or_object(
      self.root._update_test_state(  # pylint: disable=W0212
        self.path, status=status, **kwargs))
    if update_parent and self.parent:
      self.parent.update_status_from_children()
    return ret

  def update_status_from_children(self):
    """Updates the status based on children's status.

    A test is active if any children are active; else failed if
    any children are failed; else untested if any children are
    untested; else passed.
    """
    if not self.subtests:
      return

    # If there are any active tests, consider it active; if any failed,
    # consider it failed, etc. The order is important!
    status = overall_status([x.get_state().status for x in self.subtests])
    if status != self.get_state().status:
      self.update_state(status=status)

  def walk(self, in_order=False):
    """Yields this test and each sub-test.

    Args:
      in_order: Whether to walk in-order. If False, walks depth-first.
    """
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
    """Returns true if this node is a test group."""
    return isinstance(self, TestGroup)

  def is_top_level_test(self):
    """Returns true if this node is a top-level test.

    A 'top-level test' is a test directly underneath the root or a
    TestGroup, e.g., a node under which all tests must be run
    together to be meaningful.
    """
    return ((not self.is_group()) and
            self.parent and
            (self.parent == self.root or self.parent.is_group()))

  def get_top_level_parent_or_group(self):
    if self.is_group() or self.is_top_level_test() or not self.parent:
      return self
    return self.parent.get_top_level_parent_or_group()

  def get_top_level_tests(self):
    """Returns a list of top-level tests."""
    return [node for node in self.walk() if node.is_top_level_test()]

  def is_exclusive(self, option):
    """Returns true if the test or any parent is exclusive w.r.t. option.

    Args:
     option: A member of EXCLUSIVE_OPTIONS.
    """
    assert option in self.EXCLUSIVE_OPTIONS
    return option in self.exclusive or (
        self.parent and self.parent.is_exclusive(option))

  def is_no_host(self):
    """Returns true if the test or any parent is marked 'no_host'."""
    if self.no_host:
      return True
    return any([node.no_host for node in self.get_ancestor_groups()])

  def as_dict(self, state_map=None):
    """Returns this node and children in a dictionary suitable for
    YAMLification.
    """
    node = {'id': self.id or None, 'path': self.path or None}
    if not self.subtests and state_map:
      state = state_map[self.path]
      node['status'] = state.status
      node['count'] = state.count
      node['error_msg'] = state.error_msg or None
    # Convert to string, in case state_map has Unicode stuff from an RPC call
    node = UnicodeToString(node)
    if self.subtests:
      node['subtests'] = [x.as_dict(state_map) for x in self.subtests]
    return node

  def as_yaml(self, state_map=None):
    """Returns this node and children in YAML format."""
    return yaml.dump(self.as_dict(state_map))

  def disable_by_run_if(self):
    """Overwrites properties related to run_if to disable a test.

    Modifies run_if_expr, run_if_not, run_if_table_name so the run_if evaluation
    will always skip the test.
    """
    self.run_if_expr = lambda _: False
    self.run_if_not = False
    self.run_if_table_name = None

  def skip(self):
    """Skips this test and any subtests that have not already passed.

    Subtests that have passed are not modified.  If any subtests were
    skipped, this node (if not a leaf node) is marked as skipped as well.
    """
    # Modifies run_if argument of this test so it will not be enabled again
    # when its run_if is evaluated.
    self.disable_by_run_if()
    skipped_tests = []
    for test in self.walk():
      if not test.subtests and test.get_state().status != TestState.PASSED:
        test.update_state(status=TestState.PASSED, skip=True,
                          error_msg=TestState.SKIPPED_MSG)
        skipped_tests.append(test.path)
    if skipped_tests:
      logging.info('Skipped tests %s', skipped_tests)
      if self.subtests:
        logging.info('Marking %s as skipped, since subtests were skipped',
                     self.path)
        self.update_state(status=TestState.PASSED, skip=True,
                          error_msg=TestState.SKIPPED_MSG)

class FactoryTestList(FactoryTest):
  """The root node for factory tests.

  Properties:
    path_map: A map from test paths to FactoryTest objects.
    source_path: The path to the file in which the test list was defined,
        if known.  For new-style test lists only.
  """
  def __init__(self, subtests, state_instance, options,
               test_list_id=None, label_en=None, finish_construction=True):
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
      label_en: An optional label for the test list.
      finish_construction: Whether to immediately finalize the test
          list.  If False, the caller may add modify subtests,
          state_instance, and options and then call FinishConstruction().
    """
    super(FactoryTestList, self).__init__(_root=True, subtests=subtests)
    self.state_instance = state_instance
    self.subtests = filter(None, utils.FlattenList(subtests))
    self.path_map = {}
    self.root = self
    self.test_list_id = test_list_id
    self.state_change_callback = None
    self.options = options
    self.label_en = label_en or 'untitled'
    self.source_path = None

    if finish_construction:
      self.FinishConstruction()

  def FinishConstruction(self):
    """Finishes construction of the test list.

    Performs final validity checks on the test list (e.g., making sure
    there are no nodes with duplicate IDs) and sets up some internal
    data structures (like path_map).  This must be invoked after all
    nodes and options have been added to the test list, and before the
    test list is used.

    If finish_construction=True in the constructor, this is invoked in
    the constructor and the caller need not invoke it manually.

    Raises:
      TestListError: If the test list is invalid for any reason.
    """
    self._init('', self.path_map)

    # Resolve require_run paths to the actual test objects.
    for test in self.walk():
      for requirement in test.require_run:
        requirement.test = self.lookup_path(requirement.path)
        if not requirement.test:
          raise TestListError(
            "Unknown test %s in %s's require_run argument (note "
            "that full paths are required)"
            % (requirement.path, test.path))

    if self.options.strict_ids:
      bad_implicit_ids = []
      for test in self.walk():
        if test.implicit_id:
          bad_implicit_ids.append(test.path)
      if bad_implicit_ids:
        raise TestListError("options.strict_ids is set, but tests %s lack "
                            "explicitly specified IDs" % bad_implicit_ids)

  def get_all_tests(self):
    """Returns all FactoryTest objects."""
    return self.path_map.values()

  def get_state_map(self):
    """Returns a map of all FactoryTest objects to their TestStates."""
    # The state instance may return a dict (for the XML/RPC proxy)
    # or the TestState object itself. Convert accordingly.
    return dict(
      (self.lookup_path(k), TestState.from_dict_or_object(v))
      for k, v in self.state_instance.get_test_states().iteritems())

  def lookup_path(self, path):
    """Looks up a test from its path."""
    return self.path_map.get(path, None)

  def _update_test_state(self, path, **kwargs):
    """Updates a test state, invoking the state_change_callback if any.

    Internal-only; clients should call update_state directly on the
    appropriate TestState object.
    """
    ret, changed = self.state_instance.update_test_state(path, **kwargs)
    if changed and self.state_change_callback:
      self.state_change_callback(  # pylint: disable=E1102
          self.lookup_path(path), ret)
    return ret


class TestGroup(FactoryTest):
  """A collection of related tests, shown together in RHS panel if one is
  active.
  """
  pass


class FactoryAutotestTest(FactoryTest):
  """Autotest-based factory test."""
  pass


class OperatorTest(FactoryAutotestTest):
  """Factory test with UI to interact with operators."""
  has_ui = True


AutomatedSequence = FactoryTest
AutomatedSubTest = FactoryAutotestTest


class ShutdownStep(OperatorTest):
  """A shutdown (halt, reboot, or full_reboot) step.

  Properties:
    iterations: The number of times to reboot.
    operation: The command to run to perform the shutdown (FULL_REBOOT,
      REBOOT, or HALT).
    delay_secs: Number of seconds the operator has to abort the shutdown.
  """
  FULL_REBOOT = 'full_reboot'
  REBOOT = 'reboot'
  HALT = 'halt'

  def __init__(self, operation, delay_secs=5, **kwargs):
    super(ShutdownStep, self).__init__(**kwargs)
    assert not (self.autotest_name or self.pytest_name), (
        'Reboot/halt steps may not have an autotest/pytest')
    assert not self.subtests, 'Reboot/halt steps may not have subtests'
    assert not self.backgroundable, (
        'Reboot/halt steps may not be backgroundable')
    assert operation in [self.REBOOT, self.HALT, self.FULL_REBOOT]
    assert delay_secs >= 0
    self.pytest_name = 'shutdown'
    self.dargs = kwargs.get('dargs', {})
    self.dargs.update(dict(
        operation=operation,
        delay_secs=delay_secs))


class HaltStep(ShutdownStep):
  """Halts the machine."""
  def __init__(self, **kw):
    kw.setdefault('id', 'Halt')
    super(HaltStep, self).__init__(operation=ShutdownStep.HALT, **kw)


class RebootStep(ShutdownStep):
  """Reboots the machine."""
  def __init__(self, **kw):
    kw.setdefault('id', 'Reboot')
    super(RebootStep, self).__init__(operation=ShutdownStep.REBOOT, **kw)


class FullRebootStep(ShutdownStep):
  """Fully reboots the machine."""
  def __init__(self, **kw):
    kw.setdefault('id', 'FullReboot')
    super(FullRebootStep, self).__init__(
        operation=ShutdownStep.FULL_REBOOT, **kw)


AutomatedRebootSubTest = RebootStep
