# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The creation of generic Google required test list.

This file implements GRT method to create generic Google requied test list.
"""


import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import _
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
          label=_('Verify Root Partition'),
          pytest_name='verify_root_partition')

      args.Barrier('GrtVerifyRootPartition',
                   pass_without_prompt=True,
                   accessibility=True)

    if args.factory_environment:
      with OperatorTest(id='ShopFloor', label=_('ShopFloor')):
        # Double checks the serial number is correct.
        # The one in device_data matches the one on the sticker.
        OperatorTest(
            id='Scan',
            label=_('Scan Serial Number'),
            has_automator=True,
            pytest_name='scan',
            dargs=dict(
                label=_('Device Serial Number'),
                check_device_data_key='serial_number',
                regexp=args.grt_serial_number_format))

        # Write HWID again in case there is any component replacement or HWID
        # database change.
        OperatorTest(
            id='WriteHWID',
            label=_('Write HWID'),
            pytest_name='hwid_v3')

        args.Barrier('GRTVerifyHWID', pass_without_prompt=True)

    if args.detailed_cellular_tests:
      # 3G model only. Checks there is no sim card tray.
      OperatorTest(
          id='CheckNoSIMCardTray',
          label=_('Check No SIM Card Tray'),
          pytest_name='probe_sim_card_tray',
          dargs=dict(tray_already_present=False),
          run_if=args.HasCellular)

      # 3G model only. Checks there is no sim card.
      OperatorTest(
          id='CheckSIMCardNotPresent',
          label=_('Check SIM Card Not Present'),
          pytest_name='probe_sim',
          run_if=args.HasCellular,
          dargs=dict(only_check_simcard_not_present=True))

      # LTE model only. Gets the IMEI and ICCID the last time in case
      # LTE sim card or module was replaced before finalize.
      OperatorTest(
          id='ProbeLTEIMEIICCID',
          label=_('Probe LTE IMEI ICCID'),
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
        label=_('Request Clear TPM'),
        pytest_name='clear_tpm_owner_request')

    # Reboot to clear TPM.
    RebootStep(
        id='RebootToClearTPM',
        label=_('Reboot To Clean TPM'),
        iterations=1)

    args.Barrier('GRTReadyToFinalize', pass_without_prompt=True)

    if args.factory_environment:
      OperatorTest(
          id='Finish',
          label=_('Finish'),
          has_automator=True,
          pytest_name='message',
          require_run=(Passed('GoogleRequiredTests.BarrierGRTReadyToFinalize')
                       if args.grt_require_run_for_finish else None),
          never_fails=True,
          dargs=dict(
              html=_('GRT tests finished, press SPACE to finalize.\n')))

      # THIS IS A GOOGLE REQUIRED TEST.
      # PLEASE DO NOT REMOVE THIS TEST IN PRODUCTION RELEASES.
      OperatorTest(
          id='Finalize',
          label=_('Finalize'),
          has_automator=True,
          pytest_name='finalize',
          dargs=dict(
              allow_force_finalize=args.grt_allow_force_finalize,
              write_protection=args.grt_write_protect,
              upload_method=args.grt_report_upload_method,
              secure_wipe=args.grt_factory_secure_wipe,
              min_charge_pct=args.grt_finalize_battery_min_pct,
              sync_event_logs=args.enable_flush_event_logs,
              waive_tests=args.grt_waive_tests,
              enforced_release_channels=args.grt_enforced_release_channels
          ))
