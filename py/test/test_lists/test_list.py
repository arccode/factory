# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test list builder."""


import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import translation


# String prefix to indicate this value needs to be evaluated
EVALUATE_PREFIX = 'eval! '


class TestListError(Exception):
  """TestList exception"""
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
  :py:attr:`cros.factory.test.test_lists.test_list.Options.disable_caps_lock`).
  """

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


