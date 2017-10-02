# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common types and routines for factory test infrastructure.

This library provides common types and routines for the factory test
infrastructure. This library explicitly does not import gtk, to
allow its use by the autotest control process.
"""

from __future__ import print_function

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import translation
from cros.factory.test import session
from cros.factory.utils import type_utils


# TODO(hungte) Remove this when everyone is using new location session.console.
console = session.console


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

  disable_cros_shortcut_keys = True
  """Disable ChromeOS shortcut keys (see ``factory/tools/key_filter.py``)."""
  disable_caps_lock = False
  """Disable the CapsLock key."""
  caps_lock_keycode = 66
  """The CapsLock key code (used in conjunction with
  :py:attr:`cros.factory.test.factory.Options.disable_caps_lock`)."""

  hooks_class = 'cros.factory.goofy.hooks.Hooks'
  """Hooks class for the factory test harness.  Defaults to a dummy class."""

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
  """Read device data from VPD in goofy.init_states()."""

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
      raise TestListError('\n'.join(errors))

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


class TestState(object):
  """The complete state of a test.

  Properties:
    status: The status of the test (one of ACTIVE, PASSED, FAILED, or UNTESTED).
    count: The number of times the test has been run.
    error_msg: The last error message that caused a test failure.
    shutdown_count: The number of times the test has caused a shutdown.
    invocation: The currently executing invocation.
    iterations_left: For an active test, the number of remaining iterations
        after the current one.
    retries_left: Maximum number of retries allowed to pass the test.
  """
  ACTIVE = 'ACTIVE'
  PASSED = 'PASSED'
  FAILED = 'FAILED'
  UNTESTED = 'UNTESTED'
  FAILED_AND_WAIVED = 'FAILED_AND_WAIVED'
  SKIPPED = 'SKIPPED'

  def __init__(self, status=UNTESTED, count=0, error_msg=None,
               shutdown_count=0, invocation=None, iterations_left=0,
               retries_left=0):
    self.status = status
    self.count = count
    self.error_msg = error_msg
    self.shutdown_count = shutdown_count
    self.invocation = invocation
    self.iterations_left = iterations_left
    self.retries_left = retries_left

  def __repr__(self):
    return type_utils.StdRepr(self)

  def update(self, status=None, increment_count=0, error_msg=None,
             shutdown_count=None, increment_shutdown_count=0,
             invocation=None,
             decrement_iterations_left=0, iterations_left=None,
             decrement_retries_left=0, retries_left=None):
    """Updates the state of a test.

    Args:
      status: The new status of the test.
      increment_count: An amount by which to increment count.
      error_msg: If non-None, the new error message for the test.
      shutdown_count: If non-None, the new shutdown count.
      increment_shutdown_count: An amount by which to increment shutdown_count.
      invocation: The currently executing or last invocation, if any.
      iterations_left: If non-None, the new iterations_left.
      decrement_iterations_left: An amount by which to decrement
          iterations_left.
      retries_left: If non-None, the new retries_left.
          The case retries_left = -1 means the test had already used the first
          try and all the retries.
      decrement_retries_left: An amount by which to decrement retries_left.

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
    if isinstance(obj, dict):
      return TestState(**obj)
    else:
      assert isinstance(obj, TestState), type(obj)
      return obj

  def __eq__(self, other):
    return all(getattr(self, attr) == getattr(other, attr)
               for attr in self.__dict__)

  def ToStruct(self):
    result = dict(self.__dict__)
    for key in ['retries_left', 'iterations_left']:
      if result[key] == float('inf'):
        result[key] = -1
    return result


def overall_status(statuses):
  """Returns the "overall status" given a list of statuses.

  This is the first element of

    [ACTIVE, FAILED, UNTESTED, FAILED_AND_WAIVED, PASSED]

  (in that order) that is present in the status list.
  """
  status_set = set(statuses)
  for status in [TestState.ACTIVE, TestState.FAILED,
                 TestState.UNTESTED, TestState.FAILED_AND_WAIVED,
                 TestState.SKIPPED, TestState.PASSED]:
    if status in status_set:
      return status

  # E.g., if statuses is empty
  return TestState.UNTESTED


class TestListError(Exception):
  """Test list error."""
  # TODO(chromium:758115): This is defined in
  # cros.factory.test.test_lists.test_lists.  We redefine it again at here
  # because we want to resolve dependency issue.  (So factory.py won't depend on
  # cros.factory.test.test_lists.test_lists).  This should be removed when
  # factory.py is cleaned up.


class FactoryTestFailure(Exception):
  """Failure of a factory test.

  Args:
    message: The exception message.
    status: The status to report for the failure (usually FAILED but possibly
        UNTESTED).
  """

  def __init__(self, message=None, status=TestState.FAILED):
    super(FactoryTestFailure, self).__init__(message)
    self.status = status
