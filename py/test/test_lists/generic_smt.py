# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=W0613,W0622


"""The creation of generic SMT test list.

This file implements SMT method to create SMT test list.
"""


import factory_common  # pylint: disable=unused-import
from cros.factory.gooftool import commands
from cros.factory.goofy.plugins import plugin
from cros.factory.test.i18n import _
from cros.factory.test.test_lists.test_lists import AutomatedSequence
from cros.factory.test.test_lists.test_lists import FactoryTest
from cros.factory.test.test_lists.test_lists import HaltStep
from cros.factory.test.test_lists.test_lists import OperatorTest
from cros.factory.test.test_lists.test_lists import Passed
from cros.factory.test.test_lists.test_lists import RebootStep
from cros.factory.test.test_lists.test_lists import TestGroup


# SMT test items.

def SMTCharger(args, id_suffix=''):
  """Creates a test for charger type detection and a battery current test.

  Args:
    args: A TestListArgs object.
    id_suffix: The suffix of charger tests.
  """
  OperatorTest(
      id='ChargerTypeDetection_' + id_suffix,
      label=_('Charger Type Detection'),
      pytest_name='ac_power',
      # Only CHG12 charger will be identified as 'Mains'.
      dargs=dict(
          power_type=args.smt_ac_type,
          online=True,
          retries=10))

  # Checks if battery current can reach certain values when charging
  # and discharging.
  charge_discharge_args = dict(
      id='ChargeDischargeCurrent_' + id_suffix,
      label=_('Charge Discharge Current'),
      exclusive_resources=[plugin.RESOURCE.POWER],
      pytest_name='battery_current',
      retries=1,
      dargs=dict(
          min_charging_current=150,
          min_discharging_current=400,
          timeout_secs=30,
          max_battery_level=90))
  OperatorTest(**charge_discharge_args)


def ManualExtDisplay(args):
  """Creates an external display test.

  Args:
    args: A TestListArgs object.
  """
  OperatorTest(
      id='ExtDisplay',
      label=_('External Display (Manual Test)'),
      has_automator=True,
      pytest_name='ext_display',
      dargs=dict(
          main_display='eDP-1',
          display_info=[('uUSB HDMI Dongle', 'HDMI-1')]))


def ManualSMTStart(args):
  """Creates a start test.

  Args:
    args: A TestListArgs object.
  """
  OperatorTest(
      id='Start',
      label=_('Start'),
      has_automator=True,
      pytest_name='start',
      never_fails=True,
      dargs=dict(
          press_to_continue=True,
          require_external_power=args.smt_enable_check_external_power,
          check_factory_install_complete=args.check_factory_install_complete))


def ReadDeviceDataFromVPD(args):
  """Reads device data from VPD.

  Most importantly, this reads 'mlb_serial_number' and
  'smt_complete').  If SMT is already complete, we need not (and cannot!)
  run the shopfloor steps again.

  Args:
    args: A TestListArgs object.
  """
  OperatorTest(
      id='ReadDeviceDataFromVPD',
      label=_('Read Device Data From VPD'),
      pytest_name='read_device_data_from_vpd')


def ScanMLB(args):
  """Lets operator input MLB serial number.

  This test can only be run if 'smt_complete' in device_data is not True.

  Args:
    args: A TestListArgs object.
  """
  dargs = dict(
      device_data_key='mlb_serial_number',
      event_log_key='mlb_serial_number',
      label=_('MLB Serial Number'),
      regexp=args.smt_mlb_serial_number_pattern)

  OperatorTest(
      id='ScanMLB',
      label=_('Scan MLB'),
      has_automator=True,
      pytest_name='scan',
      run_if='!device_data.smt_complete',
      dargs=dargs)


def ScanOperatorID(args):
  """Lets operator input MLB serial number.

  This test can only be run if 'smt_complete' in device_data is not True.

  Args:
    args: A TestListArgs object.
  """
  OperatorTest(
      id='ScanOperatorID',
      label=_('Scan Operator ID'),
      has_automator=True,
      pytest_name='scan',
      run_if='!device_data.smt_complete',
      dargs=dict(
          device_data_key='smt_operator_id',
          event_log_key='smt_operator_id',
          label=_('Operator ID'),
          regexp=r'.*'))


def ManualSMTShopFloor1(args):
  """Creates a test groups for shopfloor related tests.

  This test group should be in the beginning of SMT before testing other
  component tests.

  Args:
    args: A TestListArgs object.
  """
  with AutomatedSequence(id='ShopFloor1'):
    args.SyncShopFloor()
    ReadDeviceDataFromVPD(args)
    ScanMLB(args)
    ScanOperatorID(args)


def UpdateFirmware(args):
  """Creates a test group to update firmware and reboot.

  Args:
    args: A TestListArgs object.
  """
  if args.smt_update_firmware:
    with OperatorTest(
        id='FirmwareUpdate',
        label=_('Firmware Update')):

      OperatorTest(
          id='FirmwareUpdate',
          label=_('Firmware Update'),
          pytest_name='update_firmware')

      RebootStep(
          id='RebootAfterFirmwareUpdate',
          label=_('Reboot'),
          iterations=1)


def SMTShopFloor2(args):
  """Creates a test groups for shopfloor related tests.

  This test group should be in the end of SMT after testing other
  component tests.

  Args:
    args: A TestListArgs object.
  """
  with AutomatedSequence(id='ShopFloor2'):
    args.SyncShopFloor()

    # Writes 'smt_complete' into device_data to mark this DUT has finished
    # SMT tests. However, this DUT has not uploaded the report yet.
    OperatorTest(
        id='UpdateDeviceData',
        label=_('Update Device Data'),
        pytest_name='update_device_data',
        dargs=dict(data=dict(smt_complete=True)))

    # Writes 'smt_complete' and 'mlb_serial_number' into RW VPD. This will be
    # retained upon re-imaging.
    OperatorTest(
        id='WriteDeviceDataToVPD',
        label=_('Write Device Data To VPD'),
        pytest_name='write_device_data_to_vpd',
        require_run=Passed(
            args.smt_test_group_id + '.ShopFloor2.UpdateDeviceData'),
        dargs=dict(
            device_data_keys=[('factory.device_data.', 'mlb_serial_number'),
                              ('factory.device_data.', 'smt_complete')],
            vpd_section='rw'))

    args.SyncShopFloor('2')

    # Uploads SMT report to shopfloor.
    OperatorTest(
        id='UploadReport',
        pytest_name='call_shopfloor',
        dargs=dict(
            method='UploadReport',
            args=lambda env: [
                env.GetDeviceData()['mlb_serial_number'],
                # CreateReportArchiveBlob is a function;
                # call_shopfloor will execute it.  We don't
                # put it here since it may be megabytes long
                # and we don't want it logged.
                commands.CreateReportArchiveBlob,
                None,
                'SMT',
            ]))


def VerifyComponents(args):
  """Creates a test to verify components match hwid database.

  Args:
    args: A TestListArgs object.
  """
  FactoryTest(
      id='VerifyComponents',
      label=_('Verify Components'),
      pytest_name='verify_components',
      dargs=dict(
          component_list=[
              'audio_codec', 'bluetooth',
              'cpu', 'dram', 'embedded_controller', 'flash_chip',
              'pmic', 'storage', 'tpm', 'usb_hosts', 'wireless'],
          # We skipped ro_main_firmware and ro_ec_firmware here because
          # they will get updated in RunIn. Update firmware in SMT takes
          # too much time.
          ))


def SMTCountdown(args):
  """Creates a countdown test which will run in parallel with other tests.

  Args:
    args: A TestListArgs object.
  """
  OperatorTest(
      id='Countdown',
      label=_('Countdown'),
      pytest_name='countdown',
      dargs=dict(
          duration_secs=(args.smt_stress_duration_secs +
                         args.smt_thermal_load_duration_secs),
          title=_('Stress/Component Tests')))


def SMTStress(args):
  """Creates a stressapptest test to run StressAppTest for a short while.

  Args:
    args: A TestListArgs object.
  """
  FactoryTest(
      id='StressAppTest',
      label=_('Stress App Test'),
      pytest_name='stressapptest',
      exclusive_resources=[plugin.RESOURCE.CPU],
      dargs=dict(
          seconds=args.smt_stress_duration_secs))


def BasicWifi(args):
  """Creates a basic WiFi test checks if DUT scan any SSID.

  Args:
    args: A TestListArgs object.
  """
  FactoryTest(
      id='Wifi',
      label=_('Wifi'),
      pytest_name='wireless',
      retries=args.smt_retries_basic_wifi)


def I2CProbeThermalSensor(args):
  """Creates a test to probe thermal sensor on I2C bus.

  Args:
    args: A TestListArgs object.
  """
  FactoryTest(
      id='ThermalSensor',
      label=_('Thermal Sensor'),
      pytest_name='i2c_probe',
      dargs=dict(
          bus=7,
          addr=0x4c))


def I2CProbeTouchpad(args):
  """Creates a test to probe touchpad on I2C bus.

  Args:
    args: A TestListArgs object.
  """
  FactoryTest(
      id='Touchpad',
      label=_('Touchpad'),
      pytest_name='i2c_probe',
      dargs=dict(
          bus=1,
          addr=[0x25, 0x4b, 0x67]))


def I2CProbeTSU671(args):
  """Creates a test to check EC connected I2C device's ID.

  TSU6721 here is just an example. Replace it and the bus, spec with
  appropriate device for different boards.

  Args:
    args: A TestListArgs object.
  """
  FactoryTest(
      id='TSU6721',
      pytest_name='ectool_i2c_dev_id',
      dargs=dict(
          bus=0,
          spec=[(0x4a, 0x1, 0xa), (0x4a, 0x1, 0x12)]))


def CameraProbe(args, retries=None):
  """Creates a test to probe camera on USB bus.

  Args:
    args: A TestListArgs object.
    retries: The number of retries for the test.
  """
  FactoryTest(
      id='CameraProbe',
      label=_('Probe Camera'),
      pytest_name='usb_probe',
      retries=(retries if retries is not None
               else args.smt_retries_camera_probe),
      dargs=dict(search_string='Camera'))


def SysfsBattery(args):
  """Creates a test to check the existence and status of battery.

  Args:
    args: A TestListArgs object.
  """
  FactoryTest(
      id='Battery',
      label=_('Battery'),
      pytest_name='sysfs_battery')


def SMT3G(args, retries=None):
  """Creates a test to check the connection of 3G board with MLB.

  Devices all have 3G boards in SMT since normally we want to make MLB that
  can support both 3G/LTE model and WiFi model.
  But device may not have 3G/LTE board in full system, so if user wants to run
  this test on full system, this test should not be included on WiFi only model.

  Args:
    args: A TestListArgs object.
    retries: The number of retries for the test.
  """
  FactoryTest(
      id='3G',
      pytest_name='line_check_item',
      retries=(retries if retries is not None
               else args.smt_retries_3g),
      dargs=dict(
          title=_('3G Probing'),
          items=[(_('3G Probing'), 'cat /sys/class/net/wwan0/address', False)]))


def SMTThermalLoad(args, retries=None):
  """Creates a test to check thermal response under load.

  This test must not be run together with StressAppTest

  Args:
    args: A TestListArgs object.
    retries: The number of retries for the test.
  """
  FactoryTest(
      id='ThermalLoad',
      label=_('Thermal Load'),
      pytest_name='thermal_load',
      retries=(retries if retries is not None
               else args.smt_retries_thermal_load),
      dargs=dict(
          lower_threshold=args.smt_thremal_load_lower_threshold_deg_c,
          temperature_limit=args.smt_thremal_load_temperature_limit_deg_c,
          heat_up_timeout_secs=args.smt_thermal_load_heat_up_timeout_secs,
          duration_secs=args.smt_thermal_load_duration_secs))


def SMTComponents(args):
  """Creates a test group for components tests.

  Args:
    args: A TestListArgs object.
  """
  with FactoryTest(id='Components', label=_('Components'), parallel=True):
    SMTCountdown(args)
    SMTStress(args)
    BasicWifi(args)
    I2CProbeThermalSensor(args)
    I2CProbeTouchpad(args)
    I2CProbeTSU671(args)
    CameraProbe(args)
    SysfsBattery(args)
    if args.smt_expect_3g_modem:
      SMT3G(args)
    SMTThermalLoad(args)


def SMTLed(args):
  """Creates a test for LED.

  Args:
    args: A TestListArgs object.
  """
  OperatorTest(
      id='LED',
      label=_('LED'),
      has_automator=True,
      pytest_name='led')


def Keyboard(args):
  """Creates a test for keyboard.

  Args:
    args: A TestListArgs object.
  """
  OperatorTest(
      id='Keyboard',
      label=_('Keyboard'),
      has_automator=True,
      pytest_name='keyboard',
      dargs=dict(
          layout='ANSI',
          keyboard_device_name='cros-ec-i2c',
          skip_power_key=False))

# Can use it directly for manual SMT test.


def SMTAudioJack(args, retries=None):
  """Creates a test for audio jack.

  Args:
    args: A TestListArgs object.
    retries: The number of retries for the test.
  """
  OperatorTest(
      id='AudioJack',
      label=_('Audio Jack'),
      has_automator=True,
      pytest_name='audio_loop',
      dargs={'require_dongle': True,
             'check_dongle': True,
             'output_volume': 15,
             'initial_actions': [('1', 'init_audiojack')],
             'input_dev': ('Audio Card', '0'),
             'output_dev': ('Audio Card', '0'),
             'tests_to_conduct': [{'type': 'sinewav',
                                   'freq_threshold': 50,
                                   'rms_threshold': (0.08, None)}]},
      retries=retries)


def SpeakerDMic(args):
  """Creates a test for Digital Microphone.

  Args:
    args: A TestListArgs object.
  """
  OperatorTest(
      id='SpeakerDMic',
      label=_('Speaker/Microphone'),
      has_automator=True,
      pytest_name='audio_loop',
      dargs={'require_dongle': False,
             'check_dongle': True,
             'output_volume': 10,
             'initial_actions': [('1', 'init_speakerdmic')],
             'input_dev': ('Audio Card', '0'),
             'output_dev': ('Audio Card', '0'),
             'tests_to_conduct': [{'type': 'audiofun',
                                   'duration': 4,
                                   'threshold': 80}]})


def LidSwitch(args, retries=3):
  """Creates a test for lid switch.

  Args:
    args: A TestListArgs object.
    retries: The number of retries for the test.
  """
  OperatorTest(
      id='LidSwitch',
      label=_('Lid Switch'),
      has_automator=True,
      pytest_name='lid_switch',
      retries=retries)


def MicroUSBPerformance(args):
  """Creates a test for micro usb performance test through On-The-Go dongle.

  Args:
    args: A TestListArgs object.
  """
  OperatorTest(
      id='MicroUSBPerformance',
      label=_('Micro USB Performance'),
      has_automator=True,
      pytest_name='removable_storage',
      retries=1,
      dargs=dict(
          media='USB',
          # sysfs_path='/sys/devices/s5p-ehci/usb1/1-1/1-1:1.0',
          block_size=512 * 1024,
          perform_random_test=False,
          perform_sequential_test=True,
          sequential_block_count=8))


def BadBlocks(args):
  """Creates a test to check storage.

  Args:
    args: A TestListArgs object.
  """
  FactoryTest(
      id='BadBlocks',
      label=_('Bad Blocks'),
      pytest_name='bad_blocks',
      dargs=dict(max_bytes=30 * 1024 * 1024))


def PartitionTable(args):
  """Creates a test to check partition utilize most of the storage space.

  Args:
    args: A TestListArgs object.
  """
  FactoryTest(id='PartitionTable',
              label=_('Partition Table'),
              pytest_name='partition_table')


def VerifyRootPartition(args):
  """Creates a test to check kernel and part of rootfs of release image.

  Note that this test only checks max_bytes of rootfs to save time.

  Args:
    args: A TestListArgs object.
  """
  FactoryTest(
      id='VerifyRootPartition',
      label=_('Verify Root Partition'),
      pytest_name='verify_root_partition',
      dargs=dict(max_bytes=1024 * 1024))


def SMTFinish(args):
  """Creates a test for finishing smt.

  Args:
    args: A TestListArgs object.
  """
  OperatorTest(
      id='Finish',
      label=_('Finish'),
      has_automator=True,
      pytest_name='message',
      require_run=(Passed(args.smt_test_group_id + '.BarrierSMT')
                   if args.smt_require_run_for_finish else None),
      never_fails=True,
      dargs=dict(
          html=_('SMT tests finished, press SPACE to shutdown.\n')))


def ParallelTestGroup(args):
  """Create a parallel test group containing several tests.

  Args:
    args: A TestListArgs object.
  """
  with FactoryTest(id='ParallelTestGroup',
                   label=_('Parallel Test Group 1'),
                   parallel=True):
    SMTCharger(args)
    VerifyComponents(args)
    PartitionTable(args)
    VerifyRootPartition(args)
    BadBlocks(args)
    SpeakerDMic(args)


def TPM(args):
  """Creates a test for testing TPM endorsement key.

  Args:
    args: A TestListArgs object.
  """
  # Checks the endorsement key in TPM. This might not be enabled in earlier
  # build.
  with TestGroup(id='TPMVerifyEK', label=_('TPM Verify EK')):
    FactoryTest(
        id='RequestClearTPM',
        label=_('Request Clear TPM'),
        pytest_name='clear_tpm_owner_request')
    RebootStep(
        id='RebootToClearTPM',
        label=_('Reboot To Clear TPM'),
        iterations=1)
    FactoryTest(
        id='VerifyEK',
        label=_('Verify EK'),
        pytest_name='tpm_verify_ek')


def ManualSMTTests(args):
  """Creates manual SMT tests.

  Args:
    args: A TestListArgs object.
  """
  ManualSMTStart(args)
  ManualSMTShopFloor1(args)
  UpdateFirmware(args)

  ParallelTestGroup(args)

  LidSwitch(args)
  SMTAudioJack(args, retries=0)
  SMTLed(args)
  SMTComponents(args)
  Keyboard(args)
  MicroUSBPerformance(args)
  ManualExtDisplay(args)
  TPM(args)

  # Uploads test status and events to Shopfloor.
  args.SyncShopFloor()
  args.Barrier('SMTTests')

  # If all tests pass, mark the DUT as SMT complete.
  if args.factory_environment:
    SMTShopFloor2(args)
  args.Barrier('SMT')
  SMTFinish(args)
  HaltStep(id='Shutdown', label=_('Shutdown'), has_automator=True)


def SMT(args):
  """Creates SMT test list.

  Args:
    args: A TestListArgs object.
  """
  with TestGroup(id=args.smt_test_group_id):
    ManualSMTTests(args)
  # Place holder for alternative test list. User can add alternative
  # SMT test lists here e.g. BFT test list.
