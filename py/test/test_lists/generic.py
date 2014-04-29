# -*- mode: python; coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The creation of generic test list.

This file implements CreateTestLists method to create
a generic test list and a experiment test list.
The class TestListArgs is a helper object to contruct test list.
The method SetOptions controls the test list options used by goofy.
"""


import hashlib
import logging
import glob

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.test.test_lists import generic_control_run
from cros.factory.test.test_lists import generic_diagnostic
from cros.factory.test.test_lists import generic_experiment
from cros.factory.test.test_lists import generic_fatp
from cros.factory.test.test_lists import generic_grt
from cros.factory.test.test_lists import generic_run_in
from cros.factory.test.test_lists import generic_smt
from cros.factory.test.test_lists.test_lists import OperatorTest
from cros.factory.test.test_lists.test_lists import SamplingRate
from cros.factory.test.test_lists.test_lists import TestList
from cros.factory.test.test_lists.test_lists import WLAN

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
  enable_shopfloor = True

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
  fully_imaged = True

  # Host/port for shopfloor communication.
  shopfloor_host = '10.3.0.11'
  shopfloor_port = 8082

  # Whether barriers should be enabled.
  enable_barriers = True

  # Minimum/maximum target battery charge.  Note that charge manager
  # is now always enabled.
  min_charge_pct = 87
  max_charge_pct = 88

  # A value that may be used for rlz_brand_code or customization_id to indicate
  # that these values should be read from device data.
  FROM_DEVICE_DATA = 'FROM_DEVICE_DATA'

  # How to obtain the rlz_brand_code and customization_id VPD values.
  # See the "Branding" page in the documentation bundle for more
  # information.  For testing, you can use rlz_brand_code = 'ZZCR' and
  # customization_id = None.  Note that this is only supported in M35
  # and above.
  rlz_brand_code = None
  customization_id = None

  #####
  #
  # Parameters for SMT (surface-mount technology) tests.
  #
  #####

  # Whether to include SMT test or not.
  smt_test_enabled = True

  # Whether to check for external power in SMT.
  smt_enable_check_external_power = True

  # Expected AC type.
  smt_ac_type = 'Mains'

  # SMT test group ID.
  smt_test_group_id = 'SMT'

  # SMT MLB serial number pattern.
  smt_mlb_serial_number_pattern = '.+'

  # Whether boards are missing 3G modems in SMT.
  smt_expect_3g_modem = False

  # Duration of stress test (SAT, Stressful Application Test)
  # during SMT.
  smt_stress_duration_secs = 10

  # Retries for flaky tests.
  smt_retries_camera_probe = 2
  smt_retries_basic_wifi = 2
  smt_retries_3g = 2
  smt_retries_thermal_load = 1
  smt_retries_audio_jack = 1

  # ThermalLoad lower and upper temperature threshold.
  smt_thremal_load_lower_threshold_deg_c = 42
  smt_thremal_load_temperature_limit_deg_c = 80
  # The duration of thermal load test during SMT.
  smt_thermal_load_heat_up_timeout_secs = 12
  @property
  def smt_thermal_load_duration_secs(self):
    return self.smt_thermal_load_heat_up_timeout_secs + 3

  # Enable requirement for SMT finish test.
  @property
  def smt_require_run_for_finish(self):
    return self.factory_environment

  # Update firmware in smt FirmwareUpdate test.
  smt_update_firmware = False

  #####
  #
  # Parameters for run-in tests.
  #
  #####

  # Number of suspend/resume tests during run-in.
  run_in_resume_iterations = 40

  # Number of reboots during run-in.
  run_in_reboot_seq_iterations = 60

  # If set, the version to which the image must be updated during
  # run-in (e.g., '4262.69.0').  If the current image's version is
  # less than this, the device will be re-imaged.
  run_in_update_image_version = '0.0'

  # If set, the chromeos-firmwareupdate in /usr/local/factory/board/
  # will be executed to update firmware in RunIn.
  run_in_update_firmware = False

  # Set device info from shopfloor or let operator select/input.
  run_in_set_device_info_from_shopfloor = True

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
  run_in_dozing_stress_duration_secs = int(0.5 * HOURS)

  # The duration of stress test during run-in (suggested 10+ mins).
  run_in_stress_duration_secs = int(2 * HOURS)

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
  # Parameters for FATP (Final Assembly, Test, and Pack) tests.
  #
  #####

  # Whether to check for external power in FATP.
  fatp_check_external_power = False

  # A dict containing all SamplingRate used in the test list:
  fatp_sampling_rate = {
    # Sampling for audio fixture tests
    'fatp_audio_fixture': SamplingRate(
        key='selected_for_audio_fixture_tests', rate=0.0),
    # Sampling for camera fixture test.
    'fatp_camera_fixture': SamplingRate(
        key='selected_for_camera_fixture_tests', rate=0.0),
    # Sampling for RF fixture test.
    'fatp_rf_fixture': SamplingRate(
        key='selected_for_rf_fixture_tests', rate=0.0),
    # Sampling for RF fixture test for LTE model.
    'fatp_rf_fixture_lte_model': SamplingRate(
        key='selected_for_rf_fixture_tests', rate=0.0),
    # Sampling for LTE fixture test.
    'fatp_lte_fixture': SamplingRate(
        key='selected_for_lte_fixture_tests', rate=0.0)
  }

  # Retries for FATP basic wifi test.
  fatp_retries_basic_wifi = 2

  # The password of AP in FATP.
  fatp_ap_password = 'crospassword'

  # The block size and count for usb performance test.
  fatp_usb_performance_block_size = 512 * 1024
  fatp_usb_performance_sequential_block_count = 8

  # Enable requirement for FATP finish test.
  @property
  def fatp_require_run_for_finish(self):
    return self.factory_environment

  # AP setting for FATP.WirelessConnection test and FATP.RSSI.WirelessRSSI.
  # 2.4G uses channels 1(2412), 4(2427), 8(2447).
  # 5G uses channels 149(5745), 153(5765), 157(5785).
  # In this example, A and B share an AP. Config AP so it can have two
  # SSID for 2.4G and two SSID for 5G.
  fatp_ap_map = {
      'A': {'2.4G': (('antenna_test_A', 2412), {"main": -50, "all": -50}),
            '5G': (('antenna_test_A_5G', 5745), {"main": -60, "all": -60})},
      'B': {'2.4G': (('antenna_test_B', 2412), {"main": -50, "all": -50}),
            '5G': (('antenna_test_B_5G', 5745), {"main": -60, "all": -60})},
      'C': {'2.4G': (('antenna_test_C', 2427), {"main": -50, "all": -50}),
            '5G': (('antenna_test_C_5G', 5765), {"main": -60, "all": -60})},
      'D': {'2.4G': (('antenna_test_D', 2447), {"main": -50, "all": -50}),
            '5G': (('antenna_test_D_5G', 5785), {"main": -60, "all": -60})},
  }

  #####
  #
  # Parameters for GRT (Google Required Tests).
  #
  #####

  # Whether to enable detailed cellular tests. These tests may not apply to all
  # boards.
  detailed_cellular_tests = False

  # Enable requirement for GRT finish test.
  @property
  def grt_require_run_for_finish(self):
    return self.factory_environment

  # Enable secure wipe (slow).
  grt_factory_secure_wipe = True

  # Enable firmware write protection.
  # *** THIS IS REQUIRED TO BE TRUE FOR MASS PRODUCTION / SHIPPING DEVICES. ***
  grt_write_protect = True

  # Upload mechanism for reports.
  #
  # Other options include:
  #   - "ftp://user:pass@host:port/directory/"
  #   - "cpfe:https://www.google.com/chromeos/partner/fe/"
  #         "report_upload?device_name=mario&report_type=rma"
  @property
  def grt_report_upload_method(self):
    return 'shopfloor' if self.enable_shopfloor else 'none'

  # Minimum percentage of battery charge level when finalizing.
  @property
  def grt_finalize_battery_min_pct(self):
    # Assume battery will discharge at most 12% during FATP testing.
    return self.run_in_blocking_charge_pct - 12

  # Serial number format. This is used in RunIn.ShopFloor.Scan test as well.
  grt_serial_number_format = r'.+'

  # Set the user that can force finalize.
  # The possible values in the list are 'engineer' and 'operator'.
  grt_allow_force_finalize = []

  # Set the waive tests in finalize. Waive all tests in Diagnostic test group.
  grt_waive_tests = [(r'^Diagnostic\..*')]

  #####
  #
  # Parameters for experiment test list which is defined in generic_experiment.
  # User can setup different test sequences in experiment test list to debug
  # certain issue. Check CreateExperimentTestList for other setttings of
  # experiment test list. The tests set in generic_experiment are just examples.
  #
  #####

  # The iterations of reboot tests in experiment test list.
  experiment_reboot_iterations = 500

  #####
  #
  # Helper methods.
  # Some helper methods can be used in run_if test argument. Helper methods like
  # SyncShopFloor and Barrier can create test that is used in many test lists.
  #
  #####

  @staticmethod
  def SelectedForControlRunImageUpdate(env):
    """The helper function switching RunIn.ShopFloor.ImageUpdateControlRun.

    This is the helper function used in run_if to switch
    RunIn.ShopFloor.ImageUpdateControlRun. User can modify this function to
    suit the actual need.
    In this example, units with serial_number in device_data falling into
    generic_control_run.CONTROL_RUN_IMAGE_UPDATE_SERIAL_NUMBERS
    will get image update. Note that if this function return None, it will be
    treated as True in current run_if mechanism.

    Args:
      env: The TestArgEnv object passed by goofy when evaluating
        run_if argument.

    Returns:
      True to run RunIn.ShopFloor.ImageUpdateControlRun.
      None will be treated as True.
    """
    serial_number = env.GetDeviceData().get('serial_number', None)
    if not serial_number:
      return None
    return (str(serial_number) in
            generic_control_run.CONTROL_RUN_IMAGE_UPDATE_SERIAL_NUMBERS)

  @staticmethod
  def SelectedForControlRunFirmwareUpdate(env):
    """The helper function switching RunIn.ShopFloor.FirmwareUpdate

    This is the helper function used in run_if to switch
    RunIn.ShopFloor.FirmwareUpdate. User can modify this function to
    suit the actual need.
    In this example, units with serial_number in device_data falling into
    generic_control_run.CONTROL_RUN_FIRMWARE_UPDATE_SERIAL_NUMBERS
    will get firmware update.

    Args:
      env: The TestArgEnv object passed by goofy when evaluating
        run_if argument.

    Returns:
      True to run RunIn.ShopFloor.FirmwareUpdate. None will be treated
      as True.
    """
    serial_number = env.GetDeviceData().get('serial_number', None)
    if not serial_number:
      return None
    return (str(serial_number) in
            generic_control_run.CONTROL_RUN_FIRMWARE_UPDATE_SERIAL_NUMBERS)

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
    """Helper functio to check if device has LTE.

    component.has_lte has to be set in some step in the flow.
    For example, set it in shopfloor steps.

    Args:
      env: The TestArgEnv object passed by goofy when evaluating
        run_if argument.

    Returns:
      Returns component.has_lte if it exists, else returns False.
    """
    return env.GetDeviceData().get('component.has_lte', False)

  def SelectedForSampling(self, name):
    """Helper function to check if a test is sampled.

    The device_data key for sampling has to be set in some step in the flow,
    For example, using select_for_sampling pytest to do sampling.

    Args:
      name: a key in self.fatp_sampling_rate.

    Returns:
      A function which will have env as argument and check if the
      device_data key corresponding to name in self.sampling is True.
      If it is not present, treat it as True.
    """
    return lambda env: env.GetDeviceData().get(
        self.fatp_sampling_rate[name].key, True)


  def SelectedForAnyFixture(self, env):
    """Helper function to check if device needs to run any fixture test.

    If the sampling key is not in device_data, treat it as True.

    Args:
      env: The TestArgEnv object passed by goofy when evaluating
        run_if argument.

    Returns:
      Returns True/False if any of audio, camera, rf, lte fixture tests is
      selected. HasLTE must be True as well if lte fixture is selected.
    """
    return (self.SelectedForSampling('fatp_audio_fixture')(env) or
            self.SelectedForSampling('fatp_camera_fixture')(env) or
            self.SelectedForSampling('fatp_rf_fixture')(env) or
            (self.SelectedForSampling('fatp_lte_fixture')(env) and
             self.HasLTE(env)))

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


def SetWLANs(options):
  """Sets options.wlans based on hash of mac_address.

  options.wlans sets the availabe wireless networks. User can set one default
  network ssid, security scheme, and passphrase e.g.
  ssid=crosfactory, security=psk, passphrase=crosfactory.
  To ease the burden of single AP, this method will further add one of
  crosfactory2[01] and one of crosfactory4[0123] to options.wlans list based on
  the hash result of mac address. It is encouraged to set the same security
  scheme and passphrase on different APs. Otherwise user has to set
  options.wlans properly in this function.

  Args:
    options: The options attribute of the TestList object to be constructed.
      Note that it will be modified in-place in this method.
  """
  # Sets default network.
  options.wlans = [WLAN(ssid='crosfactory',
                        security='psk', passphrase='crosfactory')]
  if utils.in_chroot():
    # That's good enough!
    return

  # Choose another access point as a contingency plan in case the main
  # access point gets overloaded.
  try:
    mac_address_candidate = glob.glob('/sys/class/net/*lan0/address')
    mac_address = open(mac_address_candidate[0]).read().strip()
    # pylint: disable=E1101
    mac_hash = int(hashlib.md5(mac_address).hexdigest(), 16)
    for ap_count in [2, 4]:
      # Choose based on a hash of the MAC address.  (Don't use the MAC
      # address directly since it may have certain bit patterns.)
      ap_number = mac_hash % ap_count
      wlan = WLAN(ssid=('crosfactory%d%d' % (ap_count, ap_number + 1)),
                  security='psk', passphrase='crosfactory')
      options.wlans.append(wlan)
      logging.info('Setting WLAN to ssid=%r,security=%r, passphrase=%r',
                   wlan.ssid, wlan.security, wlan.passphrase)
  except:  # pylint: disable=W0702
    # This shouldn't happen, but let's not prevent Goofy from starting up.
    logging.exception('Unable to choose random WLAN access point')


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
    options.engineering_password_sha1 = ('8c19cad459f97de3f8c836c794d9a0060'
        'a795d7b')

    # - Default to Chinese language
    options.ui_lang = 'zh'

    SetWLANs(options)

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


def CreateGenericTestList():
  """Creates a generic test list with smt, run_in, fatp and grt."""
  args = TestListArgs()
  with TestList('generic', 'All Generic Tests') as test_list:
    SetOptions(test_list.options, args)

    if args.smt_test_enabled:
      generic_smt.SMT(args)
    generic_run_in.RunIn(args)
    generic_fatp.FATP(args)
    generic_grt.GRT(args)
    generic_diagnostic.Diagnostic(args)


def CreateExperimentTestList():
  """Creates an experiment test list.

  This is a place holder for experiment test list. User can modify this
  function to suit the need.
  In this example this method creates an experiment test list containing
  Experiment tests defined in generic_experiment. Also, the test list contains
  RunIn tests defined in generic_run_in. Also, note that the
  TestListArgs object args and test_list.options are modified for experiment.
  """
  args = TestListArgs()
  args.factory_environment = False
  args.enable_shopfloor = False
  args.fully_imaged = False
  with TestList('generic_experiment', 'Generic Experiment Test') as test_list:
    SetOptions(test_list.options, args)
    test_list.options.auto_run_on_start = False
    test_list.options.stop_on_failure = True
    test_list.options.engineering_password_sha1 = None
    test_list.options.ui_lang = 'zh'
    generic_experiment.Experiment(args)
    generic_run_in.RunIn(args)


def CreateTestLists():
  """Creates test list.

  This is the external interface to test list creation (called by the
  test list builder).  This function is required and its name cannot
  be changed.
  """
  CreateGenericTestList()
  CreateExperimentTestList()
