# -*- mode: python; coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The creation of generic Google required test list.

This file implements GRT method to create generic Google requied test list.
"""


import factory_common  # pylint: disable=W0611
from cros.factory.test.test_lists.test_lists import AutomatedSequence
from cros.factory.test.test_lists.test_lists import FactoryTest
from cros.factory.test.test_lists.test_lists import OperatorTest
from cros.factory.test.test_lists.test_lists import Passed
from cros.factory.test.test_lists.test_lists import RebootStep


def GRT(args):
  """Creates Google required test list.

  Args:
    args: A TestListArgs object.
  """
  with AutomatedSequence(id='GoogleRequiredTests'):
    # Checks release image root partition.
    if args.fully_imaged:
      OperatorTest(
          id='VerifyRootPartition',
          label_zh=u'验证根磁區',
          pytest_name='verify_root_partition')

      args.Barrier('GrtVerifyRootPartition',
                   pass_without_prompt=True,
                   accessibility=True)

    if args.factory_environment:
      with OperatorTest(id='ShopFloor', label_zh=u'ShopFloor'):
        # Double checks the serial number is correct.
        # The one in device_data matches the one on the sticker.
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

        # Write HWID again in case there is any component replacement or HWID
        # database change.
        OperatorTest(
            id='WriteHWID',
            label_zh=u'硬体代号',
            pytest_name='hwid_v3')

        args.Barrier('GRTVerifyHWID', pass_without_prompt=True)

    if args.detailed_cellular_tests:
      # 3G model only. Checks there is no sim card tray.
      OperatorTest(
          id='CheckNoSIMCardTray',
          label_zh=u'检查是否无 SIM 卡盘',
          pytest_name='probe_sim_card_tray',
          dargs=dict(tray_already_present=False),
          run_if=args.HasCellular)

      # 3G model only. Checks there is no sim card.
      OperatorTest(
          id='CheckSIMCardNotPresent',
          label_zh=u'检查 SIM 卡不存在',
          pytest_name='probe_sim',
          run_if=args.HasCellular,
          dargs=dict(only_check_simcard_not_present=True))

      # LTE model only. Gets the IMEI and ICCID the last time in case
      # LTE sim card or module was replaced before finalize.
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

    # Requests to clear TPM at next boot.
    FactoryTest(
        id='RequestClearTPM',
        label_zh=u'请求清除 TPM',
        pytest_name='clear_tpm_owner_request')

    # Reboot to clear TPM.
    RebootStep(
        id='RebootToClearTPM',
        label_zh=u'重新开机',
        iterations=1)

    args.Barrier('GRTReadyToFinalize', pass_without_prompt=True)

    if args.factory_environment:
      OperatorTest(
          id='Finish',
          label_zh=u'结束',
          has_automator=True,
          pytest_name='message',
          require_run=(Passed('GoogleRequiredTests.BarrierGRTReadyToFinalize')
                       if args.grt_require_run_for_finish else None),
          never_fails=True,
          dargs=dict(
              html_en='GRT tests finished, press SPACE to finalize.\n',
              html_zh='GRT 测试结束，按下空白键最终程序\n'))

      # THIS IS A GOOGLE REQUIRED TEST.
      # PLEASE DO NOT REMOVE THIS TEST IN PRODUCTION RELEASES.
      OperatorTest(
          id='Finalize',
          label_zh=u'最终程序',
          has_automator=True,
          pytest_name='finalize',
          dargs=dict(
              allow_force_finalize=args.grt_allow_force_finalize,
              write_protection=args.grt_write_protect,
              upload_method=args.grt_report_upload_method,
              secure_wipe=args.grt_factory_secure_wipe,
              min_charge_pct=args.grt_finalize_battery_min_pct,
              hwid_version=3,
              sync_event_logs=args.enable_flush_event_logs,
              waive_tests=args.grt_waive_tests,
              enforced_release_channels=args.grt_enforced_release_channels
          ))
