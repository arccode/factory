# -*- mode: python; coding: utf-8 -*-
#
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
      label_zh=u'充电器型号识别',
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
      label_zh=u'充放电电流測試',
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
      label_zh=u'外接显示(人工測試)',
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
      label_zh=u'开始',
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
      label_zh='从 VPD 读机器资料',
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
      label_en='MLB Serial Number',
      label_zh='母板编号',
      regexp=args.smt_mlb_serial_number_pattern)

  OperatorTest(
      id='ScanMLB',
      label_zh=u'扫描母板编号',
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
      label_zh=u'扫描作业员 ID',
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
        label_zh=u'韧体更新'):

      OperatorTest(
          id='FirmwareUpdate',
          label_zh=u'韧体更新',
          pytest_name='update_firmware')

      RebootStep(
          id='RebootAfterFirmwareUpdate',
          label_zh=u'重新开机',
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
        label_zh='更新机器资料',
        pytest_name='update_device_data',
        dargs=dict(data=dict(smt_complete=True)))

    # Writes 'smt_complete' and 'mlb_serial_number' into RW VPD. This will be
    # retained upon re-imaging.
    OperatorTest(
        id='WriteDeviceDataToVPD',
        label_zh='机器资料写入到 VPD',
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
      label_zh=u'验证元件',
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
      label_zh=u'倒数计时',
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
      label_zh=u'压力测试',
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
      label_zh=u'无线网路',
      pytest_name='wireless',
      retries=args.smt_retries_basic_wifi)


def I2CProbeThermalSensor(args):
  """Creates a test to probe thermal sensor on I2C bus.

  Args:
    args: A TestListArgs object.
  """
  FactoryTest(
      id='ThermalSensor',
      label_zh=u'温度感应器',
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
      label_zh=u'触控板',
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
      label_zh=u'相机',
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
      label_zh=u'电池',
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
          title_en='3G Probing',
          title_zh=u'3G測試',
          items=[('3G Probing', u'3G測試',
                  'cat /sys/class/net/wwan0/address',
                  False)]))


def SMTThermalLoad(args, retries=None):
  """Creates a test to check thermal response under load.

  This test must not be run together with StressAppTest

  Args:
    args: A TestListArgs object.
    retries: The number of retries for the test.
  """
  FactoryTest(
      id='ThermalLoad',
      label_zh=u'温度压力',
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
  with FactoryTest(id='Components', label_zh=u'元件', parallel=True):
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
      label_zh=u'LED',
      has_automator=True,
      pytest_name='led')


def Keyboard(args):
  """Creates a test for keyboard.

  Args:
    args: A TestListArgs object.
  """
  OperatorTest(
      id='Keyboard',
      label_zh=u'键盘',
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
      label_zh=u'音源孔',
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
      label_zh=u'喇叭/麦克风',
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
      label_zh=u'上盖开关',
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
      label_zh=u'微型 USB 效能测试',
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
      label_zh=u'毁损扇區',
      pytest_name='bad_blocks',
      dargs=dict(max_bytes=30 * 1024 * 1024))


def PartitionTable(args):
  """Creates a test to check partition utilize most of the storage space.

  Args:
    args: A TestListArgs object.
  """
  FactoryTest(id='PartitionTable',
              label_zh=u'分区表',
              pytest_name='partition_table')


def VerifyRootPartition(args):
  """Creates a test to check kernel and part of rootfs of release image.

  Note that this test only checks max_bytes of rootfs to save time.

  Args:
    args: A TestListArgs object.
  """
  FactoryTest(
      id='VerifyRootPartition',
      label_zh=u'验证根磁區',
      pytest_name='verify_root_partition',
      dargs=dict(max_bytes=1024 * 1024))


def SMTFinish(args):
  """Creates a test for finishing smt.

  Args:
    args: A TestListArgs object.
  """
  OperatorTest(
      id='Finish',
      label_zh=u'结束',
      has_automator=True,
      pytest_name='message',
      require_run=(Passed(args.smt_test_group_id + '.BarrierSMT')
                   if args.smt_require_run_for_finish else None),
      never_fails=True,
      dargs=dict(
          html_en='SMT tests finished, press SPACE to shutdown.\n',
          html_zh='SMT 测试结束，按下空白键关机\n'))


def ParallelTestGroup(args):
  """Create a parallel test group containing several tests.

  Args:
    args: A TestListArgs object.
  """
  with FactoryTest(id='ParallelTestGroup', label_zh=u'平行测试群组1',
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
  with TestGroup(id='TPMVerifyEK', label_zh=u'TPM 证书'):
    FactoryTest(
        id='RequestClearTPM',
        label_zh=u'请求清除 TPM',
        pytest_name='clear_tpm_owner_request')
    RebootStep(
        id='RebootToClearTPM',
        label_zh=u'重新开机',
        iterations=1)
    FactoryTest(
        id='VerifyEK',
        label_zh=u'TPM 证书',
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
  HaltStep(id='Shutdown', label_zh=u'关机', has_automator=True)


def SMT(args):
  """Creates SMT test list.

  Args:
    args: A TestListArgs object.
  """
  with TestGroup(id=args.smt_test_group_id):
    ManualSMTTests(args)
  # Place holder for alternative test list. User can add alternative
  # SMT test lists here e.g. BFT test list.
