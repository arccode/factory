# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Shutdown factory test."""

import logging
import os
import time
import unittest
from jsonrpclib import ProtocolError

import factory_common  # pylint: disable=W0611
from cros.factory import event_log
from cros.factory.test import factory
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils
from cros.factory.test.args import Arg
from cros.factory.test.event import Event, EventClient
from cros.factory.test.factory import TestState


# File that suppresses reboot if present (e.g., for development).
NO_REBOOT_FILE = '/var/log/factory.noreboot'
_DICT_OPERATION = {
    'reboot': u'重新启动',
    'full_reboot': u'深度重启',
    'halt': u'关机'
}
_SHUTDOWN_COMMENCING_MSG = lambda operation, delay: test_ui.MakeLabel(
    'System is going to %s in %d seconds.' % (operation, delay),
    u'系统将在 %d 秒后%s.' %
    (delay, _DICT_OPERATION.get(operation, operation)))
_SHUTDOWN_COMPLETE_MSG = lambda operation: test_ui.MakeLabel(
    'Verifying system state after %s' % operation,
    u'%s后验证系统状态' % _DICT_OPERATION.get(operation, operation))
_TEST_TITLE = lambda operation: test_ui.MakeLabel(
    'Shutdown Test (%s)' % operation,
    u'关机测试 (%s)' % _DICT_OPERATION.get(operation, operation))
_CSS = 'body { font-size: 2em; }'


class ShutdownError(Exception):
  """Shutdown operation error."""
  pass


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
          default=False)
  ]

  def setUp(self):
    assert self.args.operation in (factory.ShutdownStep.REBOOT,
                                   factory.ShutdownStep.FULL_REBOOT,
                                   factory.ShutdownStep.HALT)
    self.ui = test_ui.UI(css=_CSS)
    self.template = ui_templates.OneSection(self.ui)
    self.template.SetTitle(_TEST_TITLE(self.args.operation))
    self.goofy = factory.get_state_instance()
    self.test = self.test_info.ReadTestList().lookup_path(self.test_info.path)
    self.test_state = self.goofy.get_test_state(self.test_info.path)

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
        'time': time.time() + self.args.delay_secs,
        'operation': self.args.operation,
        'iteration': iteration,
        'iterations': self.test.iterations,
    }

    # Create a new (threaded) event client since we
    # don't want to use the event loop for this.
    with EventClient() as event_client:
      event_client.post_event(
          Event(Event.Type.PENDING_SHUTDOWN, **pending_shutdown_data))
      aborted = event_client.wait(
          lambda event: event.type == Event.Type.CANCEL_SHUTDOWN,
          timeout=self.args.delay_secs) is not None
      if aborted:
        event_client.post_event(Event(Event.Type.PENDING_SHUTDOWN))
      return aborted

  def Shutdown(self):
    """Commences shutdown process by invoking Goofy's shutdown method."""
    if os.path.exists(NO_REBOOT_FILE):
      raise ShutdownError(
          'Skipped shutdown since %s is present' % NO_REBOOT_FILE)

    if utils.are_shift_keys_depressed():
      logging.info('Shift keys are depressed; cancelling restarts')
      # Abort shutdown
      self.goofy.CancelPendingTests()
      raise ShutdownError('Shutdown aborted with double shift keys')

    if self.PromptCancelShutdown(self.test_state.shutdown_count + 1):
      factory.console.info('Shutdown aborted by operator')
      event_log.Log('reboot_cancelled')
      raise ShutdownError('Shutdown aborted by operator')

    try:
      self.goofy.UIPresenterCountdown(
          'Reboot test in progress...',
          self.args.max_reboot_time_secs,
          'Reboot test failed.')
    except ProtocolError:
      # The presenter may be absent (e.g. during run-in). Ignore error
      # in this case.
      pass
    self.goofy.Shutdown(self.args.operation)

    time.sleep(self.args.wait_shutdown_secs)
    self.ui.Fail('System did not shutdown in %d seconds.' %
                 self.args.wait_shutdown_secs)

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
      if status == TestState.FAILED:
        raise ShutdownError(error_msg)

    last_shutdown_time = self.goofy.GetLastShutdownTime()
    if not last_shutdown_time:
      LogAndEndTest(status=TestState.FAILED,
                    error_msg=('Unable to read shutdown_time; '
                               'unexpected shutdown during reboot?'))

    now = time.time()
    logging.info('%.03f s passed since reboot', now - last_shutdown_time)

    if last_shutdown_time > now:
      LogAndEndTest(status=TestState.FAILED,
                    error_msg='Time moved backward during reboot')
    elif (self.args.operation == factory.ShutdownStep.REBOOT and
          self.args.max_reboot_time_secs and
          (now - last_shutdown_time > self.args.max_reboot_time_secs)):
      # A reboot took too long; fail.  (We don't check this for
      # HaltSteps, because the machine could be halted for a
      # very long time, and even unplugged with battery backup,
      # thus hosing the clock.)
      LogAndEndTest(
          status=TestState.FAILED,
          error_msg=('More than %d s elapsed during reboot '
                     '(%.03f s, from %s to %s)' % (
                         self.args.max_reboot_time_secs,
                         now - last_shutdown_time,
                         utils.TimeString(last_shutdown_time),
                         utils.TimeString(now))),
          duration=(now - last_shutdown_time))
      self.goofy.LogStartupMessages()
    elif self.test_state.shutdown_count > self.test.iterations:
      # Shut down too many times
      LogAndEndTest(status=TestState.FAILED, error_msg='Too many shutdowns')
      self.goofy.LogStartupMessages()

    elif self.args.check_tag_file and self.CheckShutdownFailureTagFile():
      LogAndEndTest(status=TestState.FAILED,
                    error_msg='Found shutdown fail tag file')

    # Good!
    LogAndEndTest(status=TestState.PASSED,
                  duration=(now - last_shutdown_time),
                  error_msg=None)

  def runTest(self):
    post_shutdown_tag = state.POST_SHUTDOWN_TAG % self.test_info.path
    if self.goofy.get_shared_data(post_shutdown_tag, True):
      # Only do post shutdown verification once.
      self.template.SetState(_SHUTDOWN_COMPLETE_MSG(self.args.operation))
      self.goofy.del_shared_data(post_shutdown_tag)
      self.PostShutdown()
    else:
      self.template.SetState(
          _SHUTDOWN_COMMENCING_MSG(self.args.operation, self.args.delay_secs))
      self.Shutdown()
