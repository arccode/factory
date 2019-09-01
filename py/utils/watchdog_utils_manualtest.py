#!/usr/bin/env python2
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import errno
import functools
import logging
import unittest

import factory_common  # pylint: disable=unused-import
# Since this script would be run as main, we can't use relative import here.
from cros.factory.utils import watchdog_utils


def AllowIOError(func):
  @functools.wraps(func)
  def _inner(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except IOError as e:
      if e.errno not in [errno.ENOTTY, errno.EOPNOTSUPP]:
        raise
      errtype = 'OSError' if e.errno == errno.ENOTTY else 'IOError'
      logging.info('%s - %s (%d) %s', func.__name__, errtype, e.errno,
                   e.strerror)
      return None
  return _inner


class WatchdogTest(unittest.TestCase):

  def setUp(self):
    self.watchdog = watchdog_utils.Watchdog()

  def tearDown(self):
    self.watchdog.Stop()
    self.watchdog = None

  def _CheckOption(self, flag):
    ident = self.watchdog.GetSupport()
    options = ident['options']
    return options & flag

  def testGetSupport(self):
    ident = self.watchdog.GetSupport()
    options = ident['options']
    logging.info('options = 0x%08X', options)
    option_flags = []
    if options & watchdog_utils.WDIOF_OVERHEAT:
      option_flags.append('overheat')
    if options & watchdog_utils.WDIOF_FANFAULT:
      option_flags.append('fan_fault')
    if options & watchdog_utils.WDIOF_EXTERN1:
      option_flags.append('external_relay_1')
    if options & watchdog_utils.WDIOF_EXTERN2:
      option_flags.append('external_relay_2')
    if options & watchdog_utils.WDIOF_POWERUNDER:
      option_flags.append('power_under')
    if options & watchdog_utils.WDIOF_CARDRESET:
      option_flags.append('card_reset')
    if options & watchdog_utils.WDIOF_POWEROVER:
      option_flags.append('power_over')
    if options & watchdog_utils.WDIOF_SETTIMEOUT:
      option_flags.append('set_timeout')
    if options & watchdog_utils.WDIOF_MAGICCLOSE:
      option_flags.append('magic_close')
    if options & watchdog_utils.WDIOF_PRETIMEOUT:
      option_flags.append('pre_timeout')
    if options & watchdog_utils.WDIOF_ALARMONLY:
      option_flags.append('alarm_only')
    if options & watchdog_utils.WDIOF_KEEPALIVEPING:
      option_flags.append('keepalive_ping')
    logging.info('option flags: %s', ' '.join(option_flags))
    logging.info('firmware_version = 0x%08x', ident['firmware_version'])
    logging.info('identity = %s', ident['identity'])

  @AllowIOError
  def testGetStatus(self):
    logging.info('status = %d', self.watchdog.GetStatus())

  @AllowIOError
  def testGetBootStatus(self):
    logging.info('boot status = 0x%08X', self.watchdog.GetBootStatus())

  @AllowIOError
  def testGetTemp(self):
    logging.info('temp = %d', self.watchdog.GetTemp())

  @AllowIOError
  def testGetTimeout(self):
    for timeout in xrange(10, 15):
      self.watchdog.SetTimeout(timeout)
      ret = self.watchdog.GetTimeout()
      logging.info('set timeout(%d), get timeout(%d)', timeout, ret)
      self.assertEqual(timeout, ret)

  @AllowIOError
  def testGetPreTimeout(self):
    for timeout in xrange(1, 5):
      self.watchdog.SetPreTimeout(timeout)
      ret = self.watchdog.GetPreTimeout()
      logging.info('set pretimeout(%d), get pretimeout(%d)', timeout, ret)
      self.assertEqual(timeout, ret)

  @AllowIOError
  def testGetTimeLeft(self):
    logging.info('timeleft = %d', self.watchdog.GetTimeLeft())


if __name__ == '__main__':
  logging.basicConfig(level=logging.ERROR, format='%(levelname)5s %(message)s')
  unittest.main()
