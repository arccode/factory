# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Shutdown/Reboot the device.

Description
-----------
This test halts or reboots the device.
This test provides three types of shutdown: reboot, full reboot, and direct EC
reboot. A reboot is leveraging the external binary 'shutdown' for rebooting, a
full reboot halts the device, then trigger a ec reboot, and a direct EC reboot
triggers a hard reset directly.

A direct EC reboot is suggested if in developmental phase, a firmware update is
triggered when system is powered on, which might cause a normal reboot fail.

Test Procedure
--------------
If argument `check_gpt` is set to True (default), it checks if partitions are
good for the next boot. Then, it reboots / halts the device according to the
argument `operation`.

Dependency
----------
* If DUT is a remote device, and argument `check_gpt` is set to True( default),
  it depends on the external binary 'cgpt' or 'partx' to read GPT info.
* Depends on the external binary 'shutdown' to perform the operation.
* Depends on the external binary 'ectool' to perform a full reboot and a direct
  EC reboot.

Examples
--------
To reboot the device after a 5-second delay, add this in test list::

  {
    "pytest_name": "shutdown",
    "args": {
      "operation": "reboot"
    }
  }

This also checks the GPT info to ensure partitions look good for the next boot.

To shutdown the device with a maximum 60-second waiting::

  {
    "pytest_name": "shutdown",
    "args": {
      "operation": "halt"
    }
  }
"""

import logging
import os
import re
import time

from cros.factory.device import device_utils
from cros.factory.test import event as test_event
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test.test_lists import test_object
from cros.factory.test import test_case
from cros.factory.test.utils import audio_utils
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sys_utils
from cros.factory.utils import time_utils
from cros.factory.utils import type_utils


# File that suppresses reboot if present (e.g., for development).
NO_REBOOT_FILE = '/var/log/factory.noreboot'

SHUTDOWN_TYPES = test_object.ShutdownStep.ShutdownTypes

_DICT_OPERATION_LABEL = {
    SHUTDOWN_TYPES.reboot: _('reboot'),
    SHUTDOWN_TYPES.full_reboot: _('full reboot'),
    SHUTDOWN_TYPES.halt: _('halt'),
    SHUTDOWN_TYPES.direct_ec_reboot: _('direct ec reboot')
}


class ShutdownError(Exception):
  """Shutdown operation error."""


class Checkpoint:
  def __init__(self, name, func):
    self.name = name
    self.func = func

  def __call__(self):
    return self.func()

  def __str__(self):
    return '<Checkpoint: %s>' % self.name

  def __repr__(self):
    return self.__str__()


class ShutdownTest(test_case.TestCase):
  """Factory test for shutdown operations (reboot, full_reboot, halt, or
  direct_ec_reboot).

  This test has two stages.  The Shutdown() method is the first stage which
  happens before the system actually shuts down; the PostShutdown() method
  serves as a callback for Goofy after the system is back from the shutdown.

  To start a shutdown operation, the Shutdown() method is called to commence a
  shutdown process through Goofy, which brings down the system.  When the system
  is up again and Goofy detects a shutdown happened when this test was active,
  it sets up its run queue to invoke the PostShutdown() method which does all
  the verifications to make sure the shutdown operation was successful.
  """
  ARGS = [
      Arg('operation', SHUTDOWN_TYPES,
          ("The command to run to perform the shutdown ('reboot', "
           "'full_reboot', 'halt', or 'direct_ec_reboot').")),
      Arg('delay_secs', int,
          'Number of seconds the operator has to abort the shutdown.',
          default=5),
      Arg('max_reboot_time_secs', int,
          ('Maximum amount of time allowed between reboots. If this threshold '
           'is exceeded, the reboot is considered failed.'), default=180),
      Arg('wait_shutdown_secs', int,
          'Number of seconds to wait for system shutdown.', default=60),
      Arg('check_tag_file', bool, 'Checks shutdown failure tag file',
          default=False),
      Arg('check_audio_devices', int,
          ('Check total number of audio devices. None for non-check.'),
          default=None),
      Arg('check_gpt', bool, 'Check GPT info before shutdown/reboot.',
          default=True)
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui.ToggleTemplateClass('font-large', True)
    self.operation_label = _DICT_OPERATION_LABEL.get(self.args.operation,
                                                     self.args.operation)
    self.ui.SetTitle(
        _('Shutdown Test ({operation})', operation=self.operation_label))
    self.goofy = state.GetInstance()
    self.test_state = self.goofy.GetTestState(self.test_info.path)
    self.remaining_time = 0

  def PromptCancelShutdown(self, iteration):
    """Shows prompt on Goofy UI for user to cancel shutdown.

    Args:
      iteration: The current iteration of shutdown.

    Returns:
      A boolean indicating whether shutdown is cancelled.
    """
    # TODO (jcliang): Move the UI for cancelling shutdown from Goofy to this
    # test.
    pending_shutdown_data = {
        'delay_secs': self.args.delay_secs,
        'operation': self.args.operation,
        'iteration': iteration,
        'iterations': self.test_state.iterations,
        'wait_shutdown_secs': self.args.wait_shutdown_secs,
    }

    with test_event.BlockingEventClient() as event_client:
      event_client.post_event(
          test_event.Event(
              test_event.Event.Type.PENDING_SHUTDOWN, **pending_shutdown_data))
      aborted = event_client.wait(
          lambda event: event.type == test_event.Event.Type.CANCEL_SHUTDOWN,
          timeout=self.args.delay_secs) is not None
      if aborted:
        event_client.post_event(
            test_event.Event(test_event.Event.Type.PENDING_SHUTDOWN))
      return aborted

  def Shutdown(self):
    """Commences shutdown process by invoking Goofy's shutdown method."""
    if os.path.exists(NO_REBOOT_FILE):
      raise ShutdownError(
          'Skipped shutdown since %s is present' % NO_REBOOT_FILE)

    expected_device_number = self.args.check_audio_devices
    if expected_device_number:
      total_device_number = audio_utils.GetTotalNumberOfAudioDevices()
      message = 'Expect %d audio devices, found %d' % (expected_device_number,
                                                       total_device_number)
      logging.info(message)
      if expected_device_number != total_device_number:
        raise ShutdownError(message)

    if self.PromptCancelShutdown(self.test_state.shutdown_count + 1):
      session.console.info('Shutdown aborted by operator')
      event_log.Log('reboot_cancelled')
      raise ShutdownError('Shutdown aborted by operator')

    try:
      self.goofy.Shutdown(self.args.operation)

      self.Sleep(self.args.wait_shutdown_secs)
    except type_utils.TestFailure:
      return
    self.FailTask(
        'System did not shutdown in %s seconds.' % self.args.wait_shutdown_secs)

  def CheckShutdownFailureTagFile(self):
    """Checks if there is any shutdown failure tag file.

    '/mnt/stateful_partition/umount-encrypted.log' and
    '/mnt/stateful_partition/shutdown_stateful_umount_failure' are the
    shutdown failure tag file.

    Returns:
      Returns True if there is shutdown failure tag file. False otherwise.
    """
    fail_shutdown = False
    files_to_check_not_exist = [
        '/mnt/stateful_partition/umount-encrypted.log',
        '/mnt/stateful_partition/shutdown_stateful_umount_failure'
    ]
    for path in files_to_check_not_exist:
      if os.path.exists(path):
        fail_shutdown = True
        with open(path) as f:
          content = f.read()
        logging.error('Reboot bad file path %s found:\n %s', path, content)
    return fail_shutdown

  def PostShutdown(self):
    """Post-shutdown verifications."""
    def LogAndEndTest(status, error_msg, **kw):
      event_log.Log('rebooted', status=status, error_msg=error_msg, **kw)
      testlog.LogParam('status', status)
      for k, v in kw.items():
        testlog.LogParam(k, v)
      logging.info('Rebooted: status=%s, %s', status,
                   (('error_msg=%s' % error_msg) if error_msg else None))
      if status == state.TestState.FAILED:
        raise ShutdownError(error_msg)

    last_shutdown_time = self.goofy.GetLastShutdownTime()
    if not last_shutdown_time:
      LogAndEndTest(status=state.TestState.FAILED,
                    error_msg=('Unable to read shutdown_time; '
                               'unexpected shutdown during reboot?'))

    now = time.time()
    logging.info('%.03f s passed since reboot', now - last_shutdown_time)

    if last_shutdown_time > now:
      LogAndEndTest(status=state.TestState.FAILED,
                    error_msg=('Time moved backward during reboot '
                               '(before=%s, after=%s)' %
                               (last_shutdown_time, now)))
    elif (self.args.operation == SHUTDOWN_TYPES.reboot and
          self.args.max_reboot_time_secs and
          (now - last_shutdown_time > self.args.max_reboot_time_secs)):
      # A reboot took too long; fail.  (We don't check this for
      # HaltSteps, because the machine could be halted for a
      # very long time, and even unplugged with battery backup,
      # thus hosing the clock.)
      LogAndEndTest(
          status=state.TestState.FAILED,
          error_msg=('More than %d s elapsed during reboot '
                     '(%.03f s, from %s to %s)' % (
                         self.args.max_reboot_time_secs,
                         now - last_shutdown_time,
                         time_utils.TimeString(last_shutdown_time),
                         time_utils.TimeString(now))),
          duration=(now - last_shutdown_time))
      logging.info(self.dut.GetStartupMessages())
    elif self.test_state.shutdown_count > self.test_state.iterations:
      # Shut down too many times
      LogAndEndTest(status=state.TestState.FAILED,
                    error_msg=('Too many shutdowns (count=%s)' %
                               self.test_state.shutdown_count))
      logging.info(self.dut.GetStartupMessages())

    elif self.args.check_tag_file and self.CheckShutdownFailureTagFile():
      LogAndEndTest(status=state.TestState.FAILED,
                    error_msg='Found shutdown fail tag file')

    # Good!
    LogAndEndTest(status=state.TestState.PASSED,
                  duration=(now - last_shutdown_time),
                  error_msg=None)

  def RemoteShutdown(self):
    DUT_READY_CHECKPOINT = Checkpoint(
        'DUT has already booted up', self.dut.IsReady)
    DUT_NOT_READY_CHECKPOINT = Checkpoint(
        'DUT has already powered down', lambda: not self.dut.IsReady())
    # We don't know the Remote DUT is really shutdown or not while the link is
    # down, so wait the wait_shutdown_secs to ensure the DUT is completely halt.
    DUT_WAIT_SHUTDOWN = Checkpoint(
        'Wait for DUT shutdown', lambda: self.remaining_time < 1)
    # In order to update the remaining time, we choose the period less than 1
    # second
    POLLING_PERIOD = 0.1

    self.PreShutdown()

    end_time = time.time() + self.args.wait_shutdown_secs
    if self.args.operation in (SHUTDOWN_TYPES.reboot,
                               SHUTDOWN_TYPES.full_reboot,
                               SHUTDOWN_TYPES.direct_ec_reboot):
      checkpoints = [DUT_NOT_READY_CHECKPOINT, DUT_READY_CHECKPOINT]
    else:
      checkpoints = [DUT_NOT_READY_CHECKPOINT, DUT_WAIT_SHUTDOWN]
    # TODO(akahuang): Make shutdown command as system module
    command_table = {
        SHUTDOWN_TYPES.reboot: ['shutdown -r now'],
        SHUTDOWN_TYPES.full_reboot: [
            'ectool reboot_ec cold at-shutdown', 'shutdown -h now'
        ],
        SHUTDOWN_TYPES.halt: ['shutdown -h now'],
        SHUTDOWN_TYPES.direct_ec_reboot: ['ectool reboot_ec cold']
    }
    for command in command_table[self.args.operation]:
      self.dut.Call(command)
    while checkpoints:
      self.remaining_time = end_time - time.time()
      if self.remaining_time < 0:
        raise ShutdownError('%s are not completed in %s secs.' %
                            (checkpoints, self.args.wait_shutdown_secs))
      self.ui.SetState(
          _('Remote DUT is performing {operation}, '
            'timeout in {delay} seconds.',
            operation=self.operation_label,
            delay=self.remaining_time))
      logging.debug('Checking %s...', checkpoints[0])
      if checkpoints[0]():
        logging.info('%s is passed.', checkpoints[0])
        checkpoints.pop(0)
      self.Sleep(POLLING_PERIOD)

  def LocalShutdown(self):
    key_post_shutdown = state.KEY_POST_SHUTDOWN % self.test_info.path
    post_shutdown = self.goofy.DataShelfGetValue(key_post_shutdown, True)
    if post_shutdown:
      # Only do post shutdown verification once.
      self.ui.SetState(
          _('Verifying system state after {operation}',
            operation=self.operation_label))
      self.goofy.DataShelfDeleteKeys(key_post_shutdown)

      if post_shutdown['goofy_error']:
        raise ShutdownError(post_shutdown['goofy_error'])
      self.PostShutdown()
    else:
      self.PreShutdown()
      self.ui.SetState(
          _('System is going to {operation} in {delay} seconds.',
            operation=self.operation_label,
            delay=self.args.delay_secs))
      self.Shutdown()

  def PreShutdown(self):
    if self.args.check_gpt:
      self.CheckGPT()

  def _GetActiveKernelPartition(self):
    rootfs_path = str(self.dut.CheckOutput(['rootdev', '-s'])).strip()
    rootfs_idx = int(re.search(r'\d+$', rootfs_path).group(0))
    kernel_idx = rootfs_idx - 1
    return kernel_idx

  def CheckGPT(self):
    """Check GPT to see if the layout looks good for the next boot."""
    kernel_partitions = [2, 4]  # KERN-A/B
    dev = str(self.dut.CheckOutput(['rootdev', '-s', '-d'])).strip()
    pm = sys_utils.PartitionManager(dev, self.dut)

    for idx in kernel_partitions:
      if not pm.IsChromeOsKernelPartition(idx):
        raise ShutdownError(
            'Partition %d should be a Chrome OS kernel partition' % idx)
      if not pm.IsChromeOsRootFsPartition(idx + 1):
        raise ShutdownError(
            'Partition %d should be a Chrome OS rootfs partition' % (idx + 1))

    active_partition = self._GetActiveKernelPartition()
    if active_partition not in kernel_partitions:
      raise ShutdownError(
          'Active partition %d should be one of %r' % (
              active_partition, kernel_partitions))

    if not pm.GetAttributeSuccess(active_partition):
      raise ShutdownError(
          'Active partition %d should be marked success.' % active_partition)

    active_partition_priority = pm.GetAttributePriority(active_partition)
    for idx in kernel_partitions:
      if idx == active_partition:
        continue
      idx_priority = pm.GetAttributePriority(idx)
      if idx_priority >= active_partition_priority:
        raise ShutdownError(
            'Active kernel partition %d is with priority %d, which should not '
            'be lower (or equal) to other kernel partition %d (priority=%d)' %
            (active_partition, active_partition_priority, idx, idx_priority))

  def runTest(self):
    if self.dut.link.IsLocal():
      self.LocalShutdown()
    else:
      self.RemoteShutdown()
