#!/usr/bin/env python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handles Whale's button click event."""

import logging
import optparse
import sys
import time

import factory_common  # pylint: disable=W0611
from cros.factory.test.fixture.whale import servo_client
from cros.factory.test.fixture.whale.host import poll_client
from cros.factory.test.utils import Enum

ActionType = Enum(['CLOSE_COVER', 'HOOK_COVER', 'PUSH_NEEDLE',
                   'PLUG_LATERAL', 'FIXTURE_STARTED'])

def TimeClassMethodDebug(func):
  """A decorator to log method running time on debug level."""
  def Wrapped(*args, **kwargs):
    logging.debug('Invoking %s()', func.__name__)
    start_time = time.time()
    result = func(*args, **kwargs)
    logging.debug('%s() finished in %.4f secs', func.__name__,
                  time.time() - start_time)
    return result
  return Wrapped


class InterruptHandler(object):
  """Waits for Whale's I/O expanders' interrupt and dispatches it.

  It connects to BeagleBone's servod and polld, where servod is used to get
  I/O expanders' input status and reset SR latches; polld is used to wait
  GPIO 7, the interrupt pin from Whale's I/O expanders.
  """
  # Shortcuts to Whale's button and control dict.
  # pylint: disable=E1101
  _BUTTON = servo_client.WHALE_BUTTON
  _CONTROL = servo_client.WHALE_CONTROL
  _FIXTURE_FEEDBACK = servo_client.FIXTURE_FEEDBACK
  _PLANKTON_FEEDBACK = servo_client.PLANKTON_FEEDBACK
  _WHALE_DEBUG_MODE_EN = servo_client.WHALE_DEBUG_MODE_EN

  # List of buttons and feedbacks to scan.
  # Difference between button and feedback is: button is latched;
  #     no latch for feedback.
  _BUTTON_LIST = servo_client.WHALE_BUTTONS
  _FEEDBACK_LIST = servo_client.WHALE_FEEDBACKS

  # Buttons that operator can use (non debug mode).
  _OPERATOR_BUTTON_LIST = (_BUTTON.FIXTURE_START, _BUTTON.FIXTURE_STOP)

  _INPUT_LIST = _BUTTON_LIST + _FEEDBACK_LIST

  _INPUT_INTERRUPT_GPIO = 7

  def __init__(self, use_polld, host, polld_port, servod_port, rpc_debug,
               polling_wait_secs):
    """Constructor.

    Args:
      use_polld: True to use polld to poll GPIO port on remote server, or False
                 to poll local GPIO port directly.
      host: BeagleBone's hostname or IP address.
      polld_port: port that polld listens.
      servod_port: port that servod listens.
      rpc_debug: True to enable XMLRPC debug message.
      polling_wait_secs: # seconds for polling button clicking event.

    """
    self._poll = poll_client.PollClient(use_polld=use_polld, host=host,
                                        tcp_port=polld_port, verbose=rpc_debug)

    self._servo = servo_client.ServoClient(host=host, port=servod_port,
                                           verbose=rpc_debug)

    self._polling_wait_secs = polling_wait_secs

    # Store last feedback value. The value is initialzed in the very first
    # ScanFeedback call.
    self._last_feedback = {}

    self._starting_fixture_action = None
    self._starting_fixture_flag = False

  @TimeClassMethodDebug
  def Init(self):
    """Resets button latch and records feedback value."""
    self._last_feedback = self._servo.MultipleIsOn(self._FEEDBACK_LIST)
    self.ResetLatch()
    self.ResetInterrupt()
    self._servo.Disable(self._CONTROL.FIXTURE_PLUG_LATERAL)
    self._servo.Disable(self._CONTROL.FIXTURE_PUSH_NEEDLE)
    self._servo.Disable(self._CONTROL.FIXTURE_HOOK_COVER)
    self._servo.Disable(self._CONTROL.FIXTURE_CLOSE_COVER)

  @TimeClassMethodDebug
  def _HandleStopFixture(self):
    """Stop Fixture Step"""
    logging.debug('[Stopping fixture...]')
    while True:
      feedback_status = self._servo.MultipleIsOn(self._FEEDBACK_LIST)
      if (not feedback_status[self._FIXTURE_FEEDBACK.FB7] or
          not feedback_status[self._FIXTURE_FEEDBACK.FB9]):
        logging.debug('[HandleStopFixture] -> FIXTURE_PLUG_LATERAL')
        self._servo.Disable(self._CONTROL.FIXTURE_PLUG_LATERAL)
        continue

      if (not feedback_status[self._FIXTURE_FEEDBACK.FB1] or
          not feedback_status[self._FIXTURE_FEEDBACK.FB3]):
        logging.debug('[HandleStopFixture] -> FIXTURE_PUSH_NEEDLE')
        self._servo.Disable(self._CONTROL.FIXTURE_PUSH_NEEDLE)
        continue

      if (feedback_status[self._FIXTURE_FEEDBACK.FB5] and
          feedback_status[self._FIXTURE_FEEDBACK.FB6]):
        logging.debug('[HandleStopFixture] -> FIXTURE_HOOK_COVER')
        self._servo.Disable(self._CONTROL.FIXTURE_HOOK_COVER)
        continue

      if (feedback_status[self._FIXTURE_FEEDBACK.FB12] or
          not feedback_status[self._FIXTURE_FEEDBACK.FB11]):
        logging.debug('[HandleStopFixture] -> FIXTURE_CLOSE_COVER')
        self._servo.Disable(self._CONTROL.FIXTURE_CLOSE_COVER)
        continue

      if feedback_status[self._FIXTURE_FEEDBACK.FB11]:
        self._starting_fixture_action = None
        logging.debug('[Fixture stopped]')
        break

  @TimeClassMethodDebug
  def _HandleStartFixtureFeedbackChange(self, feedback_status):
    """Processing Start Fixture feedback information"""
    if self._servo.IsOn(self._BUTTON.FIXTURE_START):

      if (self._starting_fixture_action == ActionType.CLOSE_COVER and
          feedback_status[self._FIXTURE_FEEDBACK.FB12]):
        logging.debug('[HandleStartFBChange] -> CHANGLE TO HOOK_COVER')
        self._starting_fixture_action = ActionType.HOOK_COVER

      elif (self._starting_fixture_action == ActionType.HOOK_COVER and
            feedback_status[self._FIXTURE_FEEDBACK.FB5] and
            feedback_status[self._FIXTURE_FEEDBACK.FB6]):
        logging.debug('[HandleStartFBChange] -> PUSH_NEEDLE')
        self._starting_fixture_action = ActionType.PUSH_NEEDLE

      elif (self._starting_fixture_action == ActionType.PUSH_NEEDLE and
            feedback_status[self._FIXTURE_FEEDBACK.FB2] and
            feedback_status[self._FIXTURE_FEEDBACK.FB4]):
        logging.debug('[HandleStartFBChange] ->PLUG_LATERAL')
        self._starting_fixture_action = ActionType.PLUG_LATERAL

      elif (self._starting_fixture_action == ActionType.PLUG_LATERAL and
            feedback_status[self._FIXTURE_FEEDBACK.FB8] and
            feedback_status[self._FIXTURE_FEEDBACK.FB10]):
        logging.debug('[START] CYLIDER ACTION is done...')
        self._starting_fixture_action = ActionType.FIXTURE_STARTED

  @TimeClassMethodDebug
  def _HandleStartFixture(self):
    """Start Fixture Step"""
    logging.debug('[Fixture Start ...]')

    if not self._starting_fixture_flag:
      return

    if self._starting_fixture_action == ActionType.FIXTURE_STARTED:
      logging.debug('[HandleStartFixture] ACTION = FIXTURE_STARTED')
      return

    if self._starting_fixture_action is None:
      logging.debug('[HandleStartFixture] ACTION = None')
      self._starting_fixture_action = ActionType.CLOSE_COVER

    if self._starting_fixture_action == ActionType.CLOSE_COVER:
      logging.debug('[HandleStartFixture] ACTION = CLOSE_COVER')
      self._servo.Enable(self._CONTROL.FIXTURE_CLOSE_COVER)

    elif self._starting_fixture_action == ActionType.HOOK_COVER:
      logging.debug('[HandleStartFixture] ACTION = HOOK_COVER')
      self._servo.Enable(self._CONTROL.FIXTURE_HOOK_COVER)

    elif self._starting_fixture_action == ActionType.PUSH_NEEDLE:
      logging.debug('[HandleStartFixture] ACTION = PUSH_NEEDLE')
      self._servo.Enable(self._CONTROL.FIXTURE_PUSH_NEEDLE)

    elif self._starting_fixture_action == ActionType.PLUG_LATERAL:
      logging.debug('[HandleStartFixture] ACTION = PLUG_LATERAL')
      self._servo.Enable(self._CONTROL.FIXTURE_PLUG_LATERAL)

  @TimeClassMethodDebug
  def ScanButton(self):
    """Scans all buttons and invokes button click handler for clicked buttons.

    Returns:
      True if a button is clicked.
    """
    logging.debug('[Scanning button....]')
    status = self._servo.MultipleIsOn(self._BUTTON_LIST)

    if status[self._BUTTON.FIXTURE_STOP]:
      self._starting_fixture_flag = False
      self._HandleStopFixture()
      return True

    if self._starting_fixture_flag and not status[self._BUTTON.FIXTURE_START]:
      self._starting_fixture_flag = False
      self._HandleStopFixture()
      return False

    button_clicked = any(status.values())

    if not button_clicked:
      return False

    operator_mode = not self._servo.IsOn(self._WHALE_DEBUG_MODE_EN)
    for button, clicked in status.iteritems():
      if not clicked:
        continue

      if operator_mode and button not in self._OPERATOR_BUTTON_LIST:
        logging.debug('Supress button %s click because debug mode is off.',
                      button)
        continue

      if button == self._BUTTON.FIXTURE_START:
        if self._starting_fixture_action == ActionType.FIXTURE_STARTED:
          logging.debug('[START] ACTION = FIXTURE_STARTED')
          self._starting_fixture_flag = False
        else:
          self._starting_fixture_flag = True
          self._HandleStartFixture()

      logging.info('Button %s clicked', button)
    return button_clicked

  @TimeClassMethodDebug
  def ScanFeedback(self):
    """Scans all feedback and invokes handler for those changed feedback.

    Returns:
      True if any feedback value is clicked.
    """
    logging.debug('[Scanning feedback....]')
    feedback_status = self._servo.MultipleIsOn(self._FEEDBACK_LIST)
    feedback_changed = False
    for name, value in feedback_status.iteritems():
      if self._last_feedback[name] == value:
        continue

      self._HandleStartFixtureFeedbackChange(feedback_status)
      logging.info('Feedback %s value changed to %r', name, value)
      self._last_feedback[name] = value
      feedback_changed = True

    return feedback_changed

  @TimeClassMethodDebug
  def ResetLatch(self):
    """Resets SR latch for buttons."""
    self._servo.Click(self._CONTROL.INPUT_RESET)

  @TimeClassMethodDebug
  def WaitForInterrupt(self):
    logging.debug('Polling interrupt (GPIO %d %s) for %r seconds',
                  self._INPUT_INTERRUPT_GPIO, self._poll.GPIO_EDGE_FALLING,
                  self._polling_wait_secs)
    if self._poll.PollGPIO(self._INPUT_INTERRUPT_GPIO,
                           self._poll.GPIO_EDGE_FALLING,
                           self._polling_wait_secs):
      logging.debug('Interrupt polled')
    else:
      logging.debug('Polling interrupt timeout')

  @TimeClassMethodDebug
  def ResetInterrupt(self):
    """Resets I/O expanders' interrupt.

    We have four I/O expanders (TCA9539), three of them have inputs. As
    BeagleBone can only accept one interrupt, we cascade two expanders'
    (0x75, 0x77) INT to 0x76 input pins. So any input changes from 0x75, 0x76,
    0x77 will generate interrupt to BeagleBone.

    According to TCA9539 manual:
        "resetting the interrupt circuit is achieved when data on the port is
         changed to the original setting or data is read from the port that
         generated the interrupt. ... Because each 8-bit port is read
         independently, the interrupt caused by port 0 is not cleared by a read
         of port 1, or vice versa",
    to reset interrupt, we need to read each changing bit. However, as servod
    reads a byte each time we read an input pin, so we only need to read 0x77
    byte-0, byte-1, 0x75 byte-1, and 0x76 byte-0, byte-1, in sequence to reset
    INT. The reason to read in sequence is that we need to read 0x76 at last
    as 0x77 and 0x75 INT reset could change P02 and P03 pin in 0x76.
    """
    # Touch I/O expander 0x77 byte 0 & 1, 0x75 byte 1, 0x76 byte 0 & 1.
    # Note that we skip I/O expander 0x75 byte-0 as it contains no input
    # pin, won't trigger interrupt.
    self._servo.MultipleGet([
        self._FIXTURE_FEEDBACK.FB1, self._BUTTON.FIXTURE_START,
        self._PLANKTON_FEEDBACK.FB1, self._WHALE_DEBUG_MODE_EN,
        self._BUTTON.RESERVE_1])

  def Run(self):
    """Waits for Whale's button click interrupt and dispatches it."""
    while True:
      button_clicked = self.ScanButton()
      feedback_changed = self.ScanFeedback()
      # The reason why we don't poll interrupt right after reset latch is that
      # it might be possible that a button is clicked after latch is cleared
      # but before I/O expander is touched. In this case, the button is latched
      # but the interrupt is consumed (after touching I/O expander) so that the
      # following click of that button won't trigger interrupt again, and
      # polling is blocked.
      #
      # The solution is to read button again without waiting for interrupt.
      if button_clicked or feedback_changed:
        if button_clicked:
          self.ResetLatch()
        self.ResetInterrupt()
        continue

      self.WaitForInterrupt()


def ParseArgs():
  """Parses command line arguments.

  Returns:
    tuple (options, args) from optparse.parse_args().
  """
  parser = optparse.OptionParser(usage='usage: %prog [options]')
  parser.description = '%prog handles Whale button click event.'
  parser.add_option('-d', '--debug', action='store_true', default=False,
                    help='enable debug messages')
  parser.add_option('', '--rpc_debug', action='store_true', default=False,
                    help='enable debug messages for XMLRPC call')
  parser.add_option('', '--use_polld', action='store_true', default=False,
                    help='whether to use polld (for polling GPIO port on '
                    'remote server) or poll local GPIO port, default: %default')
  parser.add_option('', '--host', default='127.0.0.1', type=str,
                    help='hostname of server, default: %default')
  parser.add_option('', '--polld_port', default=9998, type=int,
                    help='port that polld listens, default: %default')
  parser.add_option('', '--servod_port', default=9999, type=int,
                    help='port that servod listens, default: %default')
  parser.add_option('', '--polling_wait_secs', default=5, type=int,
                    help=('# seconds for polling button clicking event, '
                          'default: %default'))

  return parser.parse_args()


def main():
  options = ParseArgs()[0]
  logging.basicConfig(
      level=logging.DEBUG if options.debug else logging.INFO,
      format='%(asctime)s - %(levelname)s - %(message)s')

  handler = InterruptHandler(options.use_polld, options.host,
                             options.polld_port, options.servod_port,
                             options.rpc_debug, options.polling_wait_secs)
  handler.Init()
  handler.Run()


if __name__ == '__main__':
  try:
    main()
  except KeyboardInterrupt:
    sys.exit(0)
  except poll_client.PollClientError as e:
    sys.stderr.write(e.message + '\n')
    sys.exit(1)
