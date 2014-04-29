# -*- mode: python; coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The creation of generic Run-In test list.

This file implements RunIn method to create generic Run-In test list.
"""


import factory_common  # pylint: disable=W0611
from cros.factory.test.test_lists.test_lists import AutomatedSequence
from cros.factory.test.test_lists.test_lists import FactoryTest
from cros.factory.test.test_lists.test_lists import OperatorTest
from cros.factory.test.test_lists.test_lists import Passed
from cros.factory.test.test_lists.test_lists import RebootStep
from cros.factory.test.test_lists.test_lists import TestGroup


HOURS = 60 * 60


def RunIn(args, group_suffix=''):
  """Creates RunIn test list.

  Args:
    args: A TestListArgs object.
    group_suffix: Suffix for this TestGroup.
  """
  group_id = 'RunIn' + group_suffix
  with TestGroup(id=group_id):
    OperatorTest(
        id='Start',
        label_zh=u'开始',
        has_automator=True,
        pytest_name='start',
        never_fails=True,
        dargs=dict(
            # Requires pressing space to quickly check keyboard because RunIn
            # starts after full assembly and keyboard may fail on a few DUTs.
            press_to_continue=True,
            require_external_power=True,
            require_shop_floor='defer' if args.enable_shopfloor else False))

    # Checks if a designated charger is attached. If the AC plug only accept
    # the designated type, this test is not necessary.
    OperatorTest(
        id='ChargerTypeDetection',
        label_zh=u'充电器型号识别',
        pytest_name='ac_power',
        # Only CHG12 charger will be identified as 'Mains'.
        dargs=dict(
            power_type=args.run_in_ac_type,
            online=True,
            # wait for 60 seconds.
            retries=60))

    args.Barrier('RunInChargerTypeDetection',
                 pass_without_prompt=True,
                 accessibility=True)

    if args.factory_environment:
      # The image installed on DUT may be outdated since the time between SMT
      # and Run-In can be several monthgs. In this station we can let DUT do
      # image re-install using netboot.
      if args.run_in_update_image_version:
        with OperatorTest(
            id='ImageUpdate',
            label_zh=u'映像更新'):
          args.SyncShopFloor(update_without_prompt=True)

          # Writes mlb_serial_number and smt_complete into VPD
          # (Vital Product Data) so it will be availabe after re-imaging.
          OperatorTest(
              id='WriteDeviceDataToVPD',
              label_zh='机器资料写入到 VPD',
              pytest_name='write_device_data_to_vpd',
              dargs=dict(
                  device_data_keys=[
                      ('factory.device_data.', 'mlb_serial_number'),
                      ('factory.device_data.', 'smt_complete')],
                  vpd_section='rw'))

          # Checks image version is not lower than certain version. If it is,
          # flash netboot firmware and do netboot install.
          # Note that VPD will be retained using flash_netboot tool.
          OperatorTest(
              id='CheckVersion',
              label_zh=u'检查版本',
              pytest_name='check_image_version',
              dargs=dict(
                  min_version=args.run_in_update_image_version,
                  loose_version=True,
                  require_space=False))

      if args.run_in_update_firmware:
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

    if args.factory_environment:
      with OperatorTest(id='ShopFloor'):
        args.SyncShopFloor()

        # Read device data from VPD (most importantly,
        # 'mlb_serial_number' and 'smt_complete').  If SMT is
        # already complete, we need not (and cannot!) run the
        # shopfloor steps in SMT again.
        # Note that currently user has to implement the hook to skip all SMT
        # tests if there is 'smt_complete' in device_data.
        # If it is not implemented, they only those tests with
        # run_if='!device_data.smt_complete' will be skipped.
        # TODO(cychiang) Let goofy support smt_complete instead of relying on
        # hooks.
        OperatorTest(
            id='ReadDeviceDataFromVPD',
            label_zh='从 VPD 读机器资料',
            pytest_name='read_device_data_from_vpd')

        # Note that if there is any device info that is needed from shopfloor,
        # DUT should get the info in this station. User has to implement
        # GetDeviceInfo in shopfloor module.
        # Here we list device informaion that should be fetched from shopfloor
        # server.
        # 1. Component that is not probeable from system. For example:
        #   'component.antenna': antenna vendor
        #   'component.keyboard': keyboard model
        #   'color': DUT color.
        # 2. Device SKU information like 3G or LTE model. Fox example:
        #   'component.has_cellular': for 3G model. Use this to enable/disable
        #     some tests in the test list.
        #   'component.has_lte': for LTE model. Use this to enable/disable
        #     some tests in the test list.
        #   'region': The region is the key for other setting including
        #     'initial_locale', 'initial_timezone', 'keyboard_layout' and we use
        #     'region' in VPD test to determine those values.
        # 3. Codes related to group/user like 'gbind_attribute' and
        #     'ubind_attribute'.
        # 4. Information that shopfloor has and will be used during the testing
        #   flow.
        #   For example:
        #   'serial_number: system serial number.
        #   'golden_iccid': The ICCID of LTE SIM card, which will be matched to
        #     the probed ICCID.
        #   'golden_imei': The IMEI of LTE module, which will be matched to the
        #     probed IMEI.
        #   'line': The line number in multi-line scenario, where we use
        #     line to decide which AP to associate with.
        # Note that it is not required these items being fetched from
        # shopfloor. If user wants to input these items by hand, he can use
        # select_components pytest for selection.
        # For items that is not selectable, like gbind_attribute,
        # ubind_attribute, golden_iccid, golden_imei, serial number, user can
        # use scan pytest.
        if args.run_in_set_device_info_from_shopfloor:
          OperatorTest(
              id='GetDeviceInfo',
              pytest_name='call_shopfloor',
              dargs=dict(
                  method='GetDeviceInfo',
                  args=lambda env: [
                      env.GetDeviceData()['mlb_serial_number'],
                      ],
                  action='update_device_data'))

          # This test has two meaning:
          # 1. For normal flow, MLB serial number is correct, serial number
          # fetched from shopfloor using MLB serial number as key is correct.
          # This test can check if serial number sticker on the machine is
          # correct.
          # 2. When a DUT is finalized, factory related device data in RW VPD
          # like 'mlb_serial_number' and 'smt_complete' are deleted. Operator
          # needs to type MLB serial number and and add smt_complete, since
          # MLB serial number sticker is no longer available. We should check if
          # MLB serial number is correct. We scan serial number on the sticker
          # of the machine and see if it matches serial number fetched from
          # shopfloor server using MLB serial number as key.
          OperatorTest(
              id='Scan',
              label_zh=u'扫描机器编号',
              has_automator=True,
              pytest_name='scan',
              dargs=dict(
                  label_en='Device Serial Number',
                  label_zh='机器编号',
                  check_device_data_key='serial_number',
                  regexp=args.grt_serial_number_format))

        else:
          OperatorTest(
              id='SetDeviceInfo',
              label_en='Set DeviceInfo',
              label_zh='设定机器资讯',
              pytest_name='select_components',
              dargs=dict(
                  comps=dict(
                      has_cellular=('component.has_cellular',
                          ['true', 'false']),
                      has_lte=('component.has_lte', ['true', 'false']),
                      color=('color',
                          ['red', 'green', 'blue', 'yellow', 'black']),
                      line=('line', ['A', 'B', 'C', 'D']),
                      region=('region', ['us', 'gb']))))

          OperatorTest(
              id='ScanSerialNumber',
              label_zh=u'扫描机器编号',
              pytest_name='scan',
              dargs = dict(
                device_data_key='serial_number',
                event_log_key='serial_number',
                label_en='Serial Number',
                label_zh='机器编号',
                regexp=args.grt_serial_number_format))

          OperatorTest(
              id='ScanGoldenICCID',
              label_zh=u'扫描 GoldenICCID',
              pytest_name='scan',
              run_if=args.HasLTE,
              dargs = dict(
                device_data_key='golden_iccid',
                label_en='golden_iccid',
                label_zh='机器编号',
                regexp=args.run_in_golden_iccid_format))

          OperatorTest(
              id='ScanGoldenIMEI',
              label_zh=u'扫描 GoldenIMEI',
              pytest_name='scan',
              run_if=args.HasLTE,
              dargs = dict(
                device_data_key='golden_imei',
                label_en='golden_imei',
                label_zh='机器编号',
                regexp=args.run_in_golden_imei_format))

          OperatorTest(
              id='ScanGbindAttribute',
              label_zh=u'扫描 gbind_attribute',
              pytest_name='scan',
              dargs = dict(
                device_data_key='gbind_attribute',
                label_en='Group code',
                label_zh='Group 编号'))

          OperatorTest(
              id='ScanUbindAttribute',
              label_zh=u'扫描 ubind_attribute',
              pytest_name='scan',
              dargs = dict(
                device_data_key='ubind_attribute',
                label_en='User code',
                label_zh='User 编号'))


        # For LTE model only. Note that different factory can have different
        # testing sequences of LTE model. The tests set in this test list are
        # just examples.
        # LTE model has SIM card inserted after assembly before entering RunIn.
        # This test checks SIM card tray detection pin is already high.
        OperatorTest(
            id='CheckLTESIMCardTray',
            label_zh=u'检查 LTE SIM 卡盘',
            pytest_name='probe_sim_card_tray',
            dargs=dict(tray_already_present=True),
            run_if=args.HasLTE)

        # For LTE model only. This test item will be skipped if GetDeviceInfo
        # does not get device_data.component.has_lte = True.
        # In this test, IMEI of LTE module and ICCID of LTE SIM card will be
        # probed and saved in device_data. They will be matched in hwid rule
        # to golden IMEI and golden ICCID fetched from shopfloor.
        OperatorTest(
            id='ProbeLTEIMEIICCID',
            label_zh=u'提取 LTE IMEI ICCID',
            pytest_name='probe_cellular_info',
            run_if=args.HasLTE,
            dargs=dict(
               probe_meid=False,
               probe_imei=False,
               probe_lte_imei=True,
               probe_lte_iccid=True))

        # Writes VPD values into RO/RW VPD. This includes at least
        # 'serial_number', 'region', 'ubind_attribute', 'gbind_attribute',
        # 'initial_locale', 'keyboard_layout', 'initial_timezone'.
        OperatorTest(
            id='VPD',
            label_zh=u'产品资讯 (VPD)',
            pytest_name='vpd',
            dargs=dict(
                use_shopfloor_device_data=True,
                rlz_brand_code=args.rlz_brand_code,
                customization_id=args.customization_id,
                extra_device_data_fields=[('ro', 'color')]))

        # For 3G model only. Some modem can only do testing in Generic UMTS
        # mode.
        FactoryTest(
            id='SwitchToWCDMAFirmware',
            label_zh=u'切换数据机至 WCDMA 韧体',
            pytest_name='cellular_switch_firmware',
            run_if=args.HasCellular,
            dargs=dict(target='Generic UMTS'))

        # Enable this station if user wants to do a control run of new factory
        # image on a range of serial numbers. We put update steps here after
        # scan so unit gets serial number in their device_data.
        if args.run_in_control_run_update_image_version:
          with OperatorTest(
              id='ImageUpdateControlRun',
              label_zh=u'映像更新 ControlRun'):

            # Only availabe on DUT which satifies
            # args.SelectedForControlRunImageUpdate.
            # Writes mlb_serial_number and smt_complete into VPD so it will be
            # availabe after re-imaging.
            OperatorTest(
                id='WriteDeviceDataToVPD',
                label_zh='机器资料写入到 VPD',
                pytest_name='write_device_data_to_vpd',
                run_if=args.SelectedForControlRunImageUpdate,
                dargs=dict(
                    device_data_keys=[
                        ('factory.device_data.', 'mlb_serial_number'),
                        ('factory.device_data.', 'smt_complete')],
                    vpd_section='rw'))

            # Checks image version is not lower than certain version. If it is,
            # flash control run netboot firmware and do netboot install.
            # control run netboot firmware will seek different conf file on
            # shopfloor server so it will download control images.
            # Note that VPD will be retained using flash_netboot tool.
            OperatorTest(
                id='CheckVersion',
                label_zh=u'检查版本',
                pytest_name='check_image_version',
                run_if=args.SelectedForControlRunImageUpdate,
                dargs=dict(
                    min_version=args.run_in_control_run_update_image_version,
                    netboot_fw=args.run_in_control_run_netboot_firmware,
                    loose_version=True,
                    require_space=False))

        # Enable this station if user wants to do a control run of new
        # firmware on a range of serial numbers. We put update steps here after
        # scan so unit gets serial number.
        if args.run_in_control_run_firmware_update:
          OperatorTest(
              id='FirmwareUpdate',
              label_zh=u'韧体更新',
              pytest_name='update_firmware',
              run_if=args.SelectedForControlRunFirmwareUpdate)

          RebootStep(
              id='RebootAfterFirmwareUpdate',
              label_zh=u'重新开机',
              iterations=1,
              run_if=args.SelectedForControlRunFirmwareUpdate)

        # Write HWID to check components are correct.
        OperatorTest(
            id='WriteHWID',
            label_zh=u'硬体代号',
            pytest_name='hwid_v3')

        # Machine will be on carousel after this point.
        # Prompt to continue.
        args.Barrier('RunInSyncShopFloor',
                     pass_without_prompt=False,
                     accessibility=True)

    # After putting on carousel, we need to make sure charger is working.
    OperatorTest(
        id='ChargerTypeDetectionCarousel',
        label_zh=u'充电器型号识别',
        pytest_name='ac_power',
        # Only CHG12 charger will be identified as 'Mains'.
        dargs=dict(
            power_type=args.run_in_ac_type,
            online=True,
            # wait for 60 seconds.
            retries=60))

    args.Barrier('RunInChargerTypeDetectionCarousel',
                 pass_without_prompt=True,
                 accessibility=True)

    # For 3G model only. There should be no sim card tray at this point.
    OperatorTest(
        id='ProbeSIMCardTrayNotPresent',
        label_zh=u'SIM 卡卡盘不存在',
        pytest_name='probe_sim_card_tray',
        dargs=dict(tray_already_present=False),
        run_if=args.HasCellular)

    args.Barrier('RunInProbeSIM',
                 pass_without_prompt=True,
                 accessibility=True)

    # Checks hardware write protect is on.
    FactoryTest(
        id='WriteProtectSwitch',
        label_zh=u'硬体写入保护开关',
        pytest_name='write_protect_switch')

    args.Barrier('RunInWriteProtectSwitch',
                 pass_without_prompt=True,
                 accessibility=True)

    # Probes thermal sensor since we will use thermal sensor during stress
    # test.
    FactoryTest(
        id='ThermalSensor',
        label_zh=u'温度感应器',
        pytest_name='i2c_probe',
        dargs=dict(
            bus=7,
            addr=0x4c))

    args.Barrier('RunInThermalSensor',
                 pass_without_prompt=True,
                 accessibility=True)

    # Checks kernel and rootfs partition of release image.
    if args.fully_imaged:
      OperatorTest(
          id='VerifyRootPartition',
          label_zh=u'验证根磁區',
          pytest_name='verify_root_partition',
          dargs=dict(
              kern_a_device='mmcblk0p4',
              root_device='mmcblk0p5'))

      args.Barrier('RunInVerifyRootPartition',
                   pass_without_prompt=True,
                   accessibility=True)

    # Checks storage using badblocks command. If DUT is fully imaged, we can use
    # free space in stateful partition. If DUT is installed by
    # chromeos-install, there will be no free space in stateful partition,
    # and we have to use 'file' mode.
    OperatorTest(
        id='BadBlocks',
        label_zh=u'毁损扇區',
        pytest_name='bad_blocks',
        # When run alone, this takes ~.5s/MiB (for four passes).  We'll do a
        # gigabyte, which takes about about 9 minutes.
        dargs=dict(
            timeout_secs=120,
            log_threshold_secs=10,
            max_bytes=1024 * 1024 * 1024,
            mode=('stateful_partition_free_space' if args.fully_imaged
                  else 'file')))

    args.Barrier('RunInBadBlocks',
                 pass_without_prompt=True,
                 accessibility=True)

    # Reboots before stress test so DUT is in a fresh state. Note that we
    # might not want to add this step if we are trying to find what might
    # be wrong if machine is not in a fresh state.
    RebootStep(
        id='RebootBeforeStress',
        label_zh=u'重新开机',
        iterations=1)

    # Runs stress tests in parallel.
    # TODO(bhthompson): add in video and audio tests
    with AutomatedSequence(id='Stress', label_zh=u'集合压力测试'):
      # Runs WebGL operations to check graphic chip.
      OperatorTest(
          id='Graphics',
          label_zh=u'图像',
          pytest_name='webgl_aquarium',
          backgroundable=True,
          dargs=dict(duration_secs=args.run_in_stress_duration_secs))

      # Runs camera in parallel with other stress tests so it is easier
      # to trigger other possible hardware/software error.
      # Watch if the LED light of camera is on to check if camera is in
      # operation.
      FactoryTest(
          id='Camera',
          label_zh=u'相机',
          backgroundable=True,
          pytest_name='camera',
          dargs=dict(
              face_recognition=False,
              timeout_secs=args.run_in_stress_duration_secs,
              show_image=False,
              timeout_run=True))

      # Runs StressAppTest to stresses CPU and checks memory and storage.
      FactoryTest(
          id='StressAppTest',
          label_zh=u'压力测试',
          autotest_name='hardware_SAT',
          backgroundable=True,
          dargs=dict(
              drop_caches=True,
              free_memory_fraction=0.75,
              seconds=args.run_in_stress_duration_secs,
              wait_secs=60))

      # Logs system status and monitors temperature, AC status.
      # If AC is unplugged for more than args.run_in_countdown_ac_secs,
      # The test will fail and stop all tests.
      FactoryTest(
          id='Countdown',
          label_zh=u'倒数计时',
          backgroundable=True,
          pytest_name='countdown',
          dargs=dict(
              title_en='Run-In Tests',
              title_zh='烧机测试',
              duration_secs=args.run_in_stress_duration_secs,
              log_interval=args.run_in_countdown_log_interval_secs,
              grace_secs=args.run_in_countdown_grace_secs,
              temp_max_delta=args.run_in_countdown_temp_max_delta_deg_c,
              temp_criteria=args.run_in_countdown_temp_criteria))

    args.Barrier('RunInStress',
                 pass_without_prompt=True,
                 accessibility=True)

    # Reboots before dozing stress test so DUT is in a fresh state. Note that we
    # might not want to add this step if we are trying to find what might
    # be wrong if machine is not in a fresh state.
    RebootStep(
        id='Reboot1',
        label_zh=u'重新开机',
        iterations=1)

    args.Barrier('RunInReboot1',
                 pass_without_prompt=True,
                 accessibility=True)

    # Runs StressAppTest in parallel with suspend/resume so it will be easier
    # to detect bad memory.
    with AutomatedSequence(id='DozingStress', label_zh=u'睡眠内存压力测试'):
      # if StressAppTest fails here, it's likely memory issue.
      FactoryTest(
          id='StressAppTest',
          label_zh=u'压力测试',
          autotest_name='hardware_SAT',
          backgroundable=True,
          dargs=dict(
              drop_caches=True,
              free_memory_fraction=0.85,
              seconds=args.run_in_dozing_stress_duration_secs))

      # Takes about 30 minutes for 60 iterations
      FactoryTest(
          id='SuspendResume',
          label_en='SuspendResume (%d %s)' % (
              args.run_in_resume_iterations,
              'time' if args.run_in_resume_iterations == 1 else 'times'),
          label_zh=u'睡眠、唤醒 (%s 次)' % args.run_in_resume_iterations,
          pytest_name='suspend_resume',
          backgroundable=True,
          retries=1, # workaround for premature awake failure
          dargs=dict(
              cycles=args.run_in_resume_iterations,
              suspend_delay_min_secs=28,
              suspend_delay_max_secs=30,
              resume_early_margin_secs=1))

      # Logs system status and monitors temperature, AC status.
      # If AC is unplugged for more than args.run_in_countdown_ac_secs,
      # The test will fail and stop all tests.
      OperatorTest(
          id='Countdown',
          label_zh=u'倒数计时',
          backgroundable=True,
          pytest_name='countdown',
          dargs=dict(
              title_en='Dozing Stress Tests',
              title_zh='睡眠内存压力测试',
              duration_secs=args.run_in_dozing_stress_duration_secs,
              log_interval=args.run_in_countdown_log_interval_secs,
              grace_secs=args.run_in_countdown_grace_secs,
              temp_max_delta=args.run_in_countdown_temp_max_delta_deg_c,
              temp_criteria=args.run_in_countdown_temp_criteria))

    args.Barrier('RunInDozingStress',
                 pass_without_prompt=True,
                 accessibility=True)

    # Stress test for reboot.
    RebootStep(
        id='Reboot2',
        label_en='Reboot (%s %s)' % (
            args.run_in_reboot_seq_iterations,
            'time' if args.run_in_reboot_seq_iterations == 1 else 'times'),
        label_zh=u'重新开机 (%s 次)' % args.run_in_reboot_seq_iterations,
        iterations=args.run_in_reboot_seq_iterations)

    args.Barrier('RunInReboot2',
                 pass_without_prompt=True,
                 accessibility=True)

    # Regulates charge level to a accepted starting point, then test
    # charging and discharging speed.
    OperatorTest(
        id='Charger',
        label_zh=u'充电器',
        exclusive=['CHARGER'],
        pytest_name='charger',
        dargs=dict(
           min_starting_charge_pct=args.min_charge_pct,
           max_starting_charge_pct=args.max_charge_pct,
           # Allow 7 hours to charge up to min_charge_pct, in
           # case we start with an empty battery.
           starting_timeout_secs=7 * HOURS,
           check_battery_current=False,
           use_percentage=False,
           charger_type=args.run_in_ac_type,
           spec_list=[
               # Discharge 30 mAh within 600 s.  Should take ~150
               # s; load is about -700-1100 mA.
               (-30, 600, 2),
               # Charge 20 mAh within 1600 s.  Should take ~800 s;
               # current is about 75-140 mA.  Note that if a SW
               # bug causes Python task to occupy 100% CPU, this
               # test may fail due to lower-than-expected charging
               # current.
               (20, 1600, 1),
                   ]))

    args.Barrier('RunInCharger',
                 pass_without_prompt=True,
                 accessibility=True)

    # Checks release image again to make sure we did not break it in all the
    # tests above.
    if args.fully_imaged:
      OperatorTest(
          id='VerifyRootPartition2',
          label_zh=u'验证根磁區2',
          pytest_name='verify_root_partition',
          dargs=dict(
             kern_a_device='mmcblk0p4',
             root_device='mmcblk0p5'))

      args.Barrier('RunInVerifyRootPartition2',
                   pass_without_prompt=True,
                   accessibility=True)
    # Charges battery to args.run_in_blocking_charge_pct. There will be no
    # AC power during FATP process, so we must make sure DUT battery has enough
    # charge before leaving RunIn.
    OperatorTest(
        id='Charge',
        label_zh=u'充电',
        pytest_name='blocking_charge',
        exclusive=['CHARGER'],
        dargs=dict(
            timeout_secs=7200,
            target_charge_pct=args.run_in_blocking_charge_pct))

    # Disables charge manager here so we can have more charge when we
    # leave RunIn. Otherwise the charge will be regulated by charge manager.
    args.Barrier('RunIn', charge_manager=False, accessibility=True)

    if args.run_in_prompt_at_finish:
      # Disables charge manager here so we can have more charge when we
      # leave RunIn.
      OperatorTest(
          id='Finish',
          label_zh=u'结束',
          pytest_name='message',
          exclusive=['CHARGER'],
          require_run=(
              Passed(group_id + '.BarrierRunIn')
              if args.run_in_require_run_for_finish and args.enable_barriers
              else None),
          never_fails=True,
          dargs=dict(
              html_en='RunIn tests finished, press SPACE to continue.\n',
              html_zh='RunIn 测试结束，按下空白键继续\n'))
