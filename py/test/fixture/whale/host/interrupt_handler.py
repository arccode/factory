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

  _INPUT_INTERRUT_GPIO = 7

  def __init__(self, host, polld_port, servod_port, rpc_debug,
               polling_wait_secs):
    """Constructor.

    Args:
      host: BeagleBone's hostname or IP address.
      polld_port: port that polld listens.
      servod_port: port that servod listens.
      rpc_debug: True to enable XMLRPC debug message.
      polling_wait_secs: # seconds for polling button clicking event.
    """
    self._poll = poll_client.PollClient(host=host, tcp_port=polld_port,
                                        verbose=rpc_debug)

    self._servo = servo_client.ServoClient(host=host, port=servod_port,
                                           verbose=rpc_debug)

    self._polling_wait_secs = polling_wait_secs

    # Store last feedback value. The value is initialzed in the very first
    # ScanFeedback call.
    self._last_feedback = {}

  @TimeClassMethodDebug
  def Init(self):
    """Resets button latch and records feedback value."""
    for feedback_name in self._FEEDBACK_LIST:
      self._last_feedback[feedback_name] = self._servo.IsOn(feedback_name)
    self.ResetLatch()
    self.ResetInterrupt()

  @TimeClassMethodDebug
  def ScanButton(self):
    """Scans all buttons and invokes button click handler for clicked buttons.

    Returns:
      True if a button is clicked.
    """
    button_clicked = False
    operator_mode = not self._servo.IsOn(self._WHALE_DEBUG_MODE_EN)
    for button in self._BUTTON_LIST:
      clicked = self._servo.IsOn(button)
      if clicked:
        button_clicked = True
        if operator_mode and button not in self._OPERATOR_BUTTON_LIST:
          logging.debug('Supress button %s click because debug mode is off.',
                        button)
          continue

        # TODO(deanliao): calls button handler method.
        logging.info('Button %s clicked', button)
    return button_clicked

  @TimeClassMethodDebug
  def ScanFeedback(self):
    """Scans all feedback and invokes handler for those changed feedback.

    Returns:
      True if any feedback value is clicked.
    """
    feedback_changed = False
    for feedback_name in self._FEEDBACK_LIST:
      feedback_value = self._servo.IsOn(feedback_name)
      if self._last_feedback.get(feedback_name) != feedback_value:
        # TODO(deanliao): calls handler method.
        logging.info('Feedback %s value changed to %r', feedback_name,
                     feedback_value)
        self._last_feedback[feedback_name] = feedback_value
        feedback_changed = True
    return feedback_changed

  @TimeClassMethodDebug
  def ResetLatch(self):
    """Resets SR latch for buttons."""
    self._servo.Enable(self._CONTROL.INPUT_RESET)
    self._servo.Disable(self._CONTROL.INPUT_RESET)

  @TimeClassMethodDebug
  def WaitForInterrupt(self):
    logging.debug('Polling interrupt (GPIO %d %s) for %r seconds',
                  self._INPUT_INTERRUT_GPIO, self._poll.GPIO_EDGE_FALLING,
                  self._polling_wait_secs)
    if self._poll.PollGPIO(self._INPUT_INTERRUT_GPIO,
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
    # Touch I/O expander 0x77 byte-0.
    self._servo.IsOn(self._FIXTURE_FEEDBACK.FB1)
    # Touch I/O expander 0x77 byte-1.
    self._servo.IsOn(self._BUTTON.FIXTURE_START)

    # Touch I/O expander 0x75 byte-1
    # Note that we skip I/O expander 0x75 byte-0 as it contains no input
    # pin, won't trigger interrupt.
    self._servo.IsOn(self._PLANKTON_FEEDBACK.FB1)

    # Touch I/O expander 0x76, byte-0.
    self._servo.IsOn(self._WHALE_DEBUG_MODE_EN)
    # Touch I/O expander 0x76, byte-1.
    self._servo.IsOn(self._BUTTON.RESERVE_1)

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
  parser.add_option('', '--host', default='192.168.0.1', type=str,
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

  handler = InterruptHandler(options.host, options.polld_port,
                             options.servod_port, options.rpc_debug,
                             options.polling_wait_secs)
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
