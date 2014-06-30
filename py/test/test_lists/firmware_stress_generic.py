# -*- mode: python; coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""A small set of firmware stress tests."""


import factory_common  # pylint: disable=W0611
from cros.factory.test.test_lists.test_lists import AutomatedSequence
from cros.factory.test.test_lists.test_lists import FactoryTest
from cros.factory.test.test_lists.test_lists import OperatorTest
from cros.factory.test.test_lists.test_lists import RebootStep
from cros.factory.test.test_lists.test_lists import TestGroup


HOURS = 60 * 60


def RunIn(args, group_suffix='FirmwareStress'):
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

    # Charges battery to args.run_in_blocking_charge_pct.
    OperatorTest(
        id='Charge',
        label_zh=u'充电',
        pytest_name='blocking_charge',
        exclusive=['CHARGER'],
        dargs=dict(
            timeout_secs=7200,
            target_charge_pct=args.run_in_blocking_charge_pct))

    if args.run_in_prompt_at_finish:
      # Disables charge manager here so we can have more charge when we
      # leave RunIn.
      OperatorTest(
          id='Finish',
          label_zh=u'结束',
          has_automator=True,
          pytest_name='message',
          exclusive=['CHARGER'],
          never_fails=True,
          dargs=dict(
              html_en='RunIn tests finished, press SPACE to continue.\n',
              html_zh='RunIn 测试结束，按下空白键继续\n'))
