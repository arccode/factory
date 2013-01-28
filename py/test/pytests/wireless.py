# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''A factory test for basic Wifi and LTE connectivity.

The test accepts a list of wireless services, checks for their signal strength,
connects to them, and optionally tests data transmission by connecting to an
URL.
'''

import dbus
import logging
import sys
import time
import unittest
import urllib2

from cros.factory.test import factory
from cros.factory.test.args import Arg

try:
  sys.path.append('/usr/local/lib/flimflam/test')
  import flimflam  # pylint: disable=F0401
except:  # pylint: disable=W0702
  pass


def FlimGetService(flim, name):
  timeout = time.time() + 10
  while time.time() < timeout:
    service = flim.FindElementByPropertySubstring('Service', 'Name', name)
    if service:
      return service
    time.sleep(0.5)


def FlimGetServiceProperty(service, prop):
  timeout = time.time() + 10
  while time.time() < timeout:
    try:
      properties = service.GetProperties()
    except dbus.exceptions.DBusException as e:
      logging.exception('Error reading service property')
      time.sleep(1)
    else:
      return properties[prop]
  raise e


class WirelessTest(unittest.TestCase):
  ARGS = [
    Arg('services', (list, str),
        'A list of Wifi or LTE service names to test.'),
    Arg('min_signal_quality', int,
        'Minimun signal strength required. (range from 0 to 100)',
        optional=True),
    Arg('test_url', str, 'URL for testing data transmission.',
        optional=True),
  ]

  def runTest(self):
    flim = flimflam.FlimFlam(dbus.SystemBus())
    if not isinstance(self.args.services, list):
      self.args.services = [self.args.services]
    for name in self.args.services:
      service = FlimGetService(flim, name)
      if service is None:
        self.fail('Unable to find service %s' % name)

      if self.args.min_signal_quality is not None:
        strength = int(FlimGetServiceProperty(service, 'Strength'))
        factory.console.info('Service %s signal strength %d', name, strength)
        if strength < self.args.min_signal_quality:
          self.fail('Service %s signal strength %d < %d' %
                    (name, strength, self.args.min_signal_quality))

      if FlimGetServiceProperty(service, 'IsActive'):
        logging.debug('Already connected to %s', name)
      else:
        logging.debug('Connecting to %s', name)
        success, diagnostics = flim.ConnectService(service=service)
        if not success:
          self.fail('Unable to connect to %s, diagnostics %s' % (name,
                                                                 diagnostics))

      if self.args.test_url is not None:
        logging.debug('Try connecting to %s', self.args.test_url)
        try:
          urllib2.urlopen(self.args.test_url, timeout=10)
        except urllib2.HTTPError as e:
          factory.console.info('Connected to %s but got status code %d',
                               self.args.test_url, e.code)
        else:
          factory.console.info('Successfully connected to %s',
                               self.args.test_url)

      logging.debug('Disconnecting %s', name)
      flim.DisconnectService(service)
