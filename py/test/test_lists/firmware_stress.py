# -*- mode: python; coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Stress tests for firmware verification."""

import factory_common  # pylint: disable=W0611
from cros.factory.test.test_lists import firmware_stress_generic
from cros.factory.test.test_lists.test_lists import OperatorTest
from cros.factory.test.test_lists.test_lists import TestList

HOURS = 60 * 60
MINUTES = 60


class TestListArgs(object):
  """A helper object used to construct a single test list.

  This may contain:

  - arguments used when constructing the test list
  - common dargs or values that are shared across different tests
  - helper methods use to construct tests based on test arguments

  Nothing in this class is used by the test harness directly, rather
  only used by this file when constructing the test list.
  """
  # Enable options that apply only in a real factory environment.
  factory_environment = True

  # Enable shopfloor. Note that some factory environment might
  # not need a shopfloor.
  enable_shopfloor = False

  # Enable fixute tests if fixtures are available.
  enable_fixture_tests = True

  # Enable/Disable flush event logs in foreground.
  # This is used in SyncShopFloor and Finalize.
  enable_flush_event_logs = True

  # Whether to check for a completed netboot factory install.
  # Disable it for preflash image.
  check_factory_install_complete = False

  # Whether the device is fully imaged (and has the normal partition
  # table).
  fully_imaged = False

  # Host/port for shopfloor communication.
  shopfloor_host = '10.3.0.11'
  shopfloor_port = 8082

  # Whether barriers should be enabled.
  enable_barriers = True

  # Minimum/maximum target battery charge.  Note that charge manager
  # is now always enabled.
  min_charge_pct = 87
  max_charge_pct = 88

  #####
  #
  # Parameters for run-in tests.
  #
  #####

  # Number of suspend/resume tests during run-in.
  run_in_resume_iterations = 30

  # Number of reboots during run-in.
  run_in_reboot_seq_iterations = 30

  # If set, the version to which the image must be updated during
  # run-in (e.g., '4262.69.0').  If the current image's version is
  # less than this, the device will be re-imaged.
  run_in_update_image_version = '0.0'

  # If set, the chromeos-firmwareupdate in /usr/local/factory/board/
  # will be executed to update firmware in RunIn.
  run_in_update_firmware = False

  # Set device info from shopfloor or let operator select/input.
  run_in_set_device_info_from_shopfloor = False

  # Golden ICCID format for LTE SIM card.
  run_in_golden_iccid_format = r'^(\d{20})$'

  # Golden IMEI format for LTE module.
  run_in_golden_imei_format = r'^(\d{15})$'

  # We can set control run units to update image or update firmware.

  # Use SelectedForControlRunImageUpdate to control the range of
  # control run unit. The range is set in generic_control_run.py
  # This is the lowest factory image version for control run.
  run_in_control_run_update_image_version = '0.0'
  # This netboot firmware will seek different config file than default.
  # e.g. using '/usr/local/factory/board/nv_image-<board>.bin.control
  run_in_control_run_netboot_firmware = None

  # This is for control run for firmware update.
  # Use SelectedForControlRunFirmwareUpdate to control firmware update.
  run_in_control_run_firmware_update = False

  # Duration of stress test + repeated suspend/resume during run-in.
  # This may detect bit flips between suspend/resume.
  run_in_dozing_stress_duration_secs = 30 * MINUTES

  # The duration of stress test during run-in (suggested 10+ mins).
  run_in_stress_duration_secs = 30 * MINUTES

  # The interval of logging events in seconds during run-in.
  run_in_countdown_log_interval_secs = 2 * MINUTES
  # Grace period before starting abnormal status detection
  run_in_countdown_grace_secs = 8 * MINUTES
  # Allowed difference between current and last temperature of a sensor
  # in Celsius.
  run_in_countdown_temp_max_delta_deg_c = 10
  # Expected AC type.
  run_in_ac_type = 'Mains'
  # A list of rules to check that temperature is under the given range
  # rule format: (name, temp_index, warning_temp, critical_temp)
  run_in_countdown_temp_criteria = [('CPU', 0, 95, 105)]

  # Charge percentage for RunIn.Charge test in the end of run-in.
  run_in_blocking_charge_pct = 95

  # Enable requirement for RunIn finish test.
  run_in_require_run_for_finish = True

  # Prompt for space bar at the end of run-in.
  run_in_prompt_at_finish = True

  #####
  #
  # Helper methods.
  # Some helper methods can be used in run_if test argument. Helper methods like
  # SyncShopFloor and Barrier can create test that is used in many test lists.
  #
  #####

  @staticmethod
  def HasCellular(env):
    """Helper function to check if device has cellular.

    component.has_cellular has to be set in some step in the flow.
    For example, set it in shopfloor steps.

    Args:
      env: The TestArgEnv object passed by goofy when evaluating
        run_if argument.

    Returns:
      Returns component.has_cellular if it exists, else returns False.
    """
    return env.GetDeviceData().get('component.has_cellular', False)

  @staticmethod
  def HasLTE(env):
    """Helper function to check if device has LTE.

    component.has_lte has to be set in some step in the flow.
    For example, set it in shopfloor steps.

    Args:
      env: The TestArgEnv object passed by goofy when evaluating
        run_if argument.

    Returns:
      Returns component.has_lte if it exists, else returns False.
    """
    return env.GetDeviceData().get('component.has_lte', False)

  def SyncShopFloor(self, id_suffix=None, update_without_prompt=False,
                    flush_event_logs=None, run_if=None):
    """Creates a step to sync with the shopfloor server.

    If factory_environment is False, None is returned (since there is no
    shopfloor server to sync to).

    Args:
      id_suffix: An optional suffix in case multiple SyncShopFloor steps
        are needed in the same group (since they cannot have the same ID).
      update_without_prompt: do factory update if needed without prompt.
      flush_event_logs: Flush event logs to shopfloor. The default value is
        enable_flush_event_logs in TestListArgs.
      run_if: run_if argument passed to OperatorTest.
    """
    if not self.factory_environment:
      return

    if flush_event_logs is None:
      flush_event_logs = self.enable_flush_event_logs

    suffix_str = str(id_suffix) if id_suffix else ''
    OperatorTest(
        id='SyncShopFloor' + suffix_str,
        pytest_name='flush_event_logs',
        label_zh=u'同步事件记录 ' + suffix_str,
        run_if=run_if,
        dargs=dict(
            update_without_prompt=update_without_prompt,
            sync_event_logs=flush_event_logs))

  def Barrier(self, id_suffix, pass_without_prompt=False,
              accessibility=False, charge_manager=True, run_if=None):
    """Test barrier to display test summary.

    Args:
      id_suffix: The id suffix after 'Barrier'.
      pass_without_prompt: Pass barrier without prompt.
      accessibility: To show the message with clear color.
      charge_manager: Enable/disable charge manager.
      run_if: run_if argument passed to OperatorTest.
    """
    if self.enable_barriers:
      OperatorTest(
          id='Barrier' + str(id_suffix),
          label_zh=u'检查关卡' + str(id_suffix),
          has_automator=True,
          pytest_name='summary',
          run_if=run_if,
          never_fails=True,
          disable_abort=True,
          exclusive=None if charge_manager else ['CHARGER'],
          dargs=dict(
              disable_input_on_fail=True,
              pass_without_prompt=pass_without_prompt,
              accessibility=accessibility))


class MediumTestListArgs(TestListArgs):
  """Helper object to configure run for medium length."""
  #####
  #
  # Parameters for run-in tests.
  #
  #####

  # Number of suspend/resume tests during run-in.
  run_in_resume_iterations = 1000

  # Number of reboots during run-in.
  run_in_reboot_seq_iterations = 1000

  # Duration of stress test + repeated suspend/resume during run-in.
  # This may detect bit flips between suspend/resume.
  run_in_dozing_stress_duration_secs = 6 * HOURS

  # The duration of stress test during run-in (suggested 10+ mins).
  run_in_stress_duration_secs = 6 * HOURS


class LargeTestListArgs(TestListArgs):
  """Helper object to configure run for large length."""
  #####
  #
  # Parameters for run-in tests.
  #
  #####

  # Number of suspend/resume tests during run-in.
  run_in_resume_iterations = 5000

  # Number of reboots during run-in.
  run_in_reboot_seq_iterations = 5000

  # Duration of stress test + repeated suspend/resume during run-in.
  # This may detect bit flips between suspend/resume.
  run_in_dozing_stress_duration_secs = 24 * HOURS

  # The duration of stress test during run-in (suggested 10+ mins).
  run_in_stress_duration_secs = 24 * HOURS


def SetOptions(options, args):
  """Sets test list options for goofy.

  The options in this function will be used by test harness(goofy).
  Note that this function is shared by different test lists so
  users can set default options here for their need.
  For details on available options, see the Options class in
  py/test/factory.py.
  After calling this function, user can still modify options for different
  test list. For example, set options.engineering_password_sha1 to '' to
  enable engineering mode in experiment test list.

  Args:
    options: The options attribute of the TestList object to be constructed.
      Note that it will be modified in-place in this method.
    args: A TestListArgs object which contains argument that are used commonly
      by tests and options. Fox example min_charge_pct, max_charge_pct,
      shopfloor_host.
  """

  # Require explicit IDs for each test
  options.strict_ids = True

  options.min_charge_pct = args.min_charge_pct
  options.max_charge_pct = args.max_charge_pct

  if args.factory_environment:
    # echo -n 'passwordgoeshere' | sha1sum
    # Use operator mode by default and require a password to enable
    # engineering mode. This password is 'cros'.
    options.engineering_password_sha1 = (
        '8c19cad459f97de3f8c836c794d9a0060a795d7b')

    # - Default to English language
    options.ui_lang = 'en'

    # Enable/Disable background event log syncing
    # Set to None or 0 to disable it.
    options.sync_event_log_period_secs = 0
    options.update_period_secs = 5 * MINUTES
    # - Enable clock syncing with shopfloor server
    options.sync_time_period_secs = None
    options.shopfloor_server_url = 'http://%s:%d/' % (
        args.shopfloor_host, args.shopfloor_port)
    # - Disable ChromeOS keys.
    options.disable_cros_shortcut_keys = True

    # - Disable CPU frequency manager.
    options.use_cpufreq_manager = False

    # Enable/Disable system log syncing
    options.enable_sync_log = True
    options.sync_log_period_secs = 10 * MINUTES
    options.scan_log_period_secs = 2 * MINUTES
    options.core_dump_watchlist = []
    options.log_disk_space_period_secs = 2 * MINUTES
    options.check_battery_period_secs = 2 * MINUTES
    options.warning_low_battery_pct = 10
    options.critical_low_battery_pct = 5
    options.stateful_usage_threshold = 90


def CreateFirmwareStressSmallTestList():
  """Creates a test list for firmware stress small run."""
  args = TestListArgs()
  with TestList('firmware_stress_small',
                'Firmware Stress Small') as test_list:
    SetOptions(test_list.options, args)
    firmware_stress_generic.RunIn(args)


def CreateFirmwareStressMediumTestList():
  """Creates a test list for firmware stress medium run."""
  args = MediumTestListArgs()
  with TestList('firmware_stress_medium',
                'Firmware Stress Medium') as test_list:
    SetOptions(test_list.options, args)
    firmware_stress_generic.RunIn(args)


def CreateFirmwareStressLargeTestList():
  """Creates a test list for firmware stress large run."""
  args = LargeTestListArgs()
  with TestList('firmware_stress_large',
                'Firmware Stress Large') as test_list:
    SetOptions(test_list.options, args)
    firmware_stress_generic.RunIn(args)

def CreateTestLists():
  """Creates test list.

  This is the external interface to test list creation (called by the
  test list builder).  This function is required and its name cannot
  be changed.
  """
  CreateFirmwareStressSmallTestList()
  CreateFirmwareStressMediumTestList()
  CreateFirmwareStressLargeTestList()
