# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Shutdown factory test."""

import jsonrpclib
import logging
import os
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import event as test_event
from cros.factory.test import event_log
from cros.factory.test import factory
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import audio_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sys_utils
from cros.factory.utils import time_utils


# File that suppresses reboot if present (e.g., for development).
NO_REBOOT_FILE = '/var/log/factory.noreboot'
_DICT_OPERATION_LABEL = {
    'reboot': _('reboot'),
    'full_reboot': _('full reboot'),
    'halt': _('halt')
}
_SHUTDOWN_COMMENCING_MSG = lambda operation, delay: (
    i18n_test_ui.MakeI18nLabel(
        'System is going to {operation} in {delay} seconds.',
        operation=_DICT_OPERATION_LABEL.get(operation, operation),
        delay=delay))
_REMOTE_SHUTDOWN_PROGRESS_MSG = lambda operation, delay: (
    i18n_test_ui.MakeI18nLabel(
        'Remote DUT is performing {operation}, timeout in {delay} seconds.',
        operation=_DICT_OPERATION_LABEL.get(operation, operation),
        delay=delay))
_SHUTDOWN_COMPLETE_MSG = lambda operation: i18n_test_ui.MakeI18nLabel(
    'Verifying system state after {operation}',
    operation=_DICT_OPERATION_LABEL.get(operation, operation))
_TEST_TITLE = lambda operation: i18n_test_ui.MakeI18nLabel(
    'Shutdown Test ({operation})',
    operation=_DICT_OPERATION_LABEL.get(operation, operation))
_CSS = 'body { font-size: 2em; }'


class ShutdownError(Exception):
  """Shutdown operation error."""
  pass


class Checkpoint(object):
  def __init__(self, name, func):
    self.name = name
    self.func = func

  def __call__(self):
    return self.func()

  def __str__(self):
    return '<Checkpoint: %s>' % self.name

  def __repr__(self):
    return self.__str__()


class ShutdownTest(unittest.TestCase):
  """Factory test for shutdown operations (reboot, full_reboot, or halt).

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
      Arg('operation', str,
          ("The command to run to perform the shutdown ('reboot', "
           "'full_reboot', or 'halt').")),
      Arg('delay_secs', int,
          'Number of seconds the operator has to abort the shutdown.',
          default=5),
      Arg('max_reboot_time_secs', int,
          ('Maximum amount of time allowed between reboots. If this threshold '
           'is exceeded, the reboot is considered failed.'),
          default=180, optional=True),
      Arg('wait_shutdown_secs', int,
          'Number of seconds to wait for system shutdown.', default=60),
      Arg('check_tag_file', bool, 'Checks shutdown failure tag file',
          default=False),
      Arg('check_audio_devices', int,
          ('Check total number of audio devices. None for non-check.'),
          default=None, optional=True),
  ]

  def setUp(self):
    assert self.args.operation in (factory.ShutdownStep.REBOOT,
                                   factory.ShutdownStep.FULL_REBOOT,
                                   factory.ShutdownStep.HALT)
    self.dut = device_utils.CreateDUTInterface()
    self.ui = test_ui.UI(css=_CSS)
    self.template = ui_templates.OneSection(self.ui)
    self.template.SetTitle(_TEST_TITLE(self.args.operation))
    self.goofy = state.get_instance()
    self.test = self.test_info.ReadTestList().LookupPath(self.test_info.path)
    self.test_state = self.goofy.get_test_state(self.test_info.path)
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
        'iterations': self.test.iterations,
        'wait_shutdown_secs': self.args.wait_shutdown_secs,
    }

    # Create a new (threaded) event client since we
    # don't want to use the event loop for this.
    with test_event.EventClient() as event_client:
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
      factory.console.info('Shutdown aborted by operator')
      event_log.Log('reboot_cancelled')
      raise ShutdownError('Shutdown aborted by operator')

    try:
      if self.args.operation == factory.ShutdownStep.HALT:
        self.goofy.UIPresenterCountdown(
            'Shutdown test in progress...',
            self.args.wait_shutdown_secs,
            'Shutdown test succeeded.',
            False)
      else:
        self.goofy.UIPresenterCountdown(
            'Reboot test in progress...',
            self.args.max_reboot_time_secs,
            'Reboot test failed.')
    except jsonrpclib.ProtocolError:
      # The presenter may be absent (e.g. during run-in). Ignore error
      # in this case.
      pass
    self.goofy.Shutdown(self.args.operation)

    time.sleep(self.args.wait_shutdown_secs)
    error_msg = 'System did not shutdown in %s seconds.' % (
        self.args.wait_shutdown_secs)
    self.ui.Fail(error_msg)
    raise ShutdownError(error_msg)

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
      logging.info('Rebooted: status=%s, %s', status,
                   (('error_msg=%s' % error_msg) if error_msg else None))
      if status == factory.TestState.FAILED:
        raise ShutdownError(error_msg)

    last_shutdown_time = self.goofy.GetLastShutdownTime()
    if not last_shutdown_time:
      LogAndEndTest(status=factory.TestState.FAILED,
                    error_msg=('Unable to read shutdown_time; '
                               'unexpected shutdown during reboot?'))

    now = time.time()
    logging.info('%.03f s passed since reboot', now - last_shutdown_time)

    if last_shutdown_time > now:
      LogAndEndTest(status=factory.TestState.FAILED,
                    error_msg='Time moved backward during reboot')
    elif (self.args.operation == factory.ShutdownStep.REBOOT and
          self.args.max_reboot_time_secs and
          (now - last_shutdown_time > self.args.max_reboot_time_secs)):
      # A reboot took too long; fail.  (We don't check this for
      # HaltSteps, because the machine could be halted for a
      # very long time, and even unplugged with battery backup,
      # thus hosing the clock.)
      LogAndEndTest(
          status=factory.TestState.FAILED,
          error_msg=('More than %d s elapsed during reboot '
                     '(%.03f s, from %s to %s)' % (
                         self.args.max_reboot_time_secs,
                         now - last_shutdown_time,
                         time_utils.TimeString(last_shutdown_time),
                         time_utils.TimeString(now))),
          duration=(now - last_shutdown_time))
      logging.info(sys_utils.GetStartupMessages(self.dut))
    elif self.test_state.shutdown_count > self.test.iterations:
      # Shut down too many times
      LogAndEndTest(status=factory.TestState.FAILED,
                    error_msg='Too many shutdowns')
      logging.info(sys_utils.GetStartupMessages(self.dut))

    elif self.args.check_tag_file and self.CheckShutdownFailureTagFile():
      LogAndEndTest(status=factory.TestState.FAILED,
                    error_msg='Found shutdown fail tag file')

    # Good!
    LogAndEndTest(status=factory.TestState.PASSED,
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

    end_time = time.time() + self.args.wait_shutdown_secs
    if self.args.operation in (factory.ShutdownStep.REBOOT,
                               factory.ShutdownStep.FULL_REBOOT):
      checkpoints = [DUT_NOT_READY_CHECKPOINT, DUT_READY_CHECKPOINT]
    else:
      checkpoints = [DUT_NOT_READY_CHECKPOINT, DUT_WAIT_SHUTDOWN]
    # TODO(akahuang): Make shutdown command as system module
    command_table = {
        factory.ShutdownStep.REBOOT: ['shutdown -r now'],
        factory.ShutdownStep.FULL_REBOOT: ['ectool reboot_ec cold at-shutdown',
                                           'shutdown -r now'],
        factory.ShutdownStep.HALT: ['shutdown -h now']}
    for command in command_table[self.args.operation]:
      self.dut.Call(command)
    while checkpoints:
      self.remaining_time = end_time - time.time()
      if self.remaining_time < 0:
        raise ShutdownError('%s are not completed in %s secs.' %
                            (checkpoints, self.args.wait_shutdown_secs))
      self.template.SetState(_REMOTE_SHUTDOWN_PROGRESS_MSG(
          self.args.operation, self.remaining_time))
      logging.debug('Checking %s...', checkpoints[0])
      if checkpoints[0]():
        logging.info('%s is passed.', checkpoints[0])
        checkpoints.pop(0)
      time.sleep(POLLING_PERIOD)

  def LocalShutdown(self):
    key_post_shutdown = state.KEY_POST_SHUTDOWN % self.test_info.path
    post_shutdown = self.goofy.get_shared_data(key_post_shutdown, True)
    if post_shutdown:
      # Only do post shutdown verification once.
      self.template.SetState(_SHUTDOWN_COMPLETE_MSG(self.args.operation))
      self.goofy.del_shared_data(key_post_shutdown)

      if post_shutdown['goofy_error']:
        raise ShutdownError(post_shutdown['goofy_error'])
      self.PostShutdown()
    else:
      self.template.SetState(
          _SHUTDOWN_COMMENCING_MSG(self.args.operation, self.args.delay_secs))
      self.Shutdown()

  def runTest(self):
    if self.dut.link.IsLocal():
      self.LocalShutdown()
    else:
      self.RemoteShutdown()
