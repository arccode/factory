# -*- coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''A factory test for basic Wifi and LTE connectivity.

The test accepts a list of wireless services, checks for their signal strength,
connects to them, and optionally tests data transmission by connecting to an
URL.
'''

import dbus
import logging
import os
import sys
import tempfile
import time
import unittest
import urllib2

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import Log
from cros.factory.system.service_manager import GetServiceStatus
from cros.factory.system.service_manager import SetServiceStatus
from cros.factory.system.service_manager import Status
from cros.factory.test import factory
from cros.factory.test.args import Arg
from cros.factory.utils.net_utils import GetWLANInterface
from cros.factory.utils.net_utils import GetEthernetIp
from cros.factory.utils.process_utils import Spawn, CheckOutput

try:
  sys.path.append('/usr/local/lib/flimflam/test')
  import flimflam  # pylint: disable=F0401
except:  # pylint: disable=W0702
  pass


_SERVICE_LIST = ['shill', 'shill_respawn', 'wpasupplicant',
                 'modemmanager']


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

def FlimConfigureService(flim, name, password):
  wlan_dict = {
      'Type': 'wifi',
      'Mode': 'managed',
      'AutoConnect': False,
      'SSID': name}
  if password:
    wlan_dict['Security'] = 'psk'
    wlan_dict['Passphrase'] = password

  flim.manager.ConfigureService(wlan_dict)

class WirelessTest(unittest.TestCase):
  ARGS = [
    Arg('services', (list, tuple),
        'A list of Wifi or LTE service (name, password) tuple to test.'
        ' e.g. [("ssid1", "password1"), ("ssid2", "password2")].'
        ' Set password to None or "" if it is open network.'
        'If services are not specified, this test will check for any AP',
        optional=True),
    Arg('min_signal_quality', int,
        'Minimun signal strength required. (range from 0 to 100)',
        optional=True),
    Arg('test_url', str, 'URL for testing data transmission.',
        optional=True),
    Arg('throughput_threshold', (int, float),
        'Required minimum throughput in bytes/sec.',
        optional=True, default=None),
    Arg('md5sum', str, 'md5sum of the test file in test_url',
        optional=True),
    Arg('msecs_before_retries', int,
        'Milliseconds before next retry when downloading the file.',
        optional=True, default=1000),
  ]

  def _DownloadFileAndMeasureThroughput(self):
    '''Tries to download a file, checks its md5sum, and measures throughput.

    This function uses the following data members:
      self.args.test_url: the URL to download.
      self.args.md5sum: the expected md5sum of the file.
      self.args.msecs_before_retries: delay before next retry.

    Returns:
      A dict containing:
        result: True if the function successfully downloaded the file and
            verified its md5sum, False otherwise.
        file_size: file size in bytes.
        time_spent: time spent in seconds.
        throughput: throughput in bytes/seccond.
      file_size, time_spent, and throughput are valid only if result is True.
    '''
    logging.info('Try connecting to %s', self.args.test_url)
    for i in range(5): # pylint: disable=W0612
      try:
        remote_file = urllib2.urlopen(self.args.test_url, timeout=2)
      except urllib2.HTTPError as e:
        factory.console.info(
            'Connected to %s but got status code %d: %s.',
            self.args.test_url, e.code, e.reason)
      except urllib2.URLError as e:
        factory.console.info(
            'Failed to connect to %s: %s.', self.args.test_url, e.reason)
      else:
        with tempfile.NamedTemporaryFile() as local_file:
          # Download file and measure time.
          start = time.time()
          file_content = remote_file.read()
          time_spent = time.time() - start
          local_file.write(file_content)
          local_file.flush()
          os.fdatasync(local_file)
          # Calculate size and throughput.
          file_size = os.path.getsize(local_file.name)
          throughput = file_size / time_spent
          # Calculate md5sum.
          md5sum_output = CheckOutput(['md5sum', local_file.name],
                                      log=True).strip().split()[0]
        logging.info('Got local file md5sum %s', md5sum_output)
        logging.info('Golden file md5sum %s', self.args.md5sum)
        if md5sum_output == self.args.md5sum:
          factory.console.info(
              'Successfully connected to %s, file size: %d bytes, '
              'time spent: %f sec, throughput: %d bytes/sec',
              self.args.test_url, file_size, time_spent, throughput)
          return {'result': True,
                  'file_size': file_size,
                  'time_spent': time_spent,
                  'throughput': throughput}
      # If failed, delay before retry.
      time.sleep(self.args.msecs_before_retries / 1000.0)

    return {'result': False,
            'file_size': 0,
            'time_spent': 0,
            'throughput': 0}

  def setUp(self):
    for service in _SERVICE_LIST:
      if GetServiceStatus(service) == Status.STOP:
        SetServiceStatus(service, Status.START)
    dev = GetWLANInterface()
    if not dev:
      self.fail('No wireless interface')
    else:
      logging.info('ifconfig %s up', dev)
      Spawn(['ifconfig', dev, 'up'], check_call=True, log=True)

  def runTest(self):
    flim = flimflam.FlimFlam(dbus.SystemBus())

    if self.args.services is None:
      # Basic wifi test -- succeeds if it can see any AP
      found_ssids = set([])
      for service in flim.GetObjectList('Service'):
        service_type = FlimGetServiceProperty(service, 'Type')
        service_name = FlimGetServiceProperty(service, 'Name')
        if service_type != 'wifi':
          continue
        if service_name is None:
          continue
        found_ssids.add(service_name)
      if not found_ssids:
        self.fail("No SSIDs found.")
      logging.info('found SSIDs: %s', ', '.join(found_ssids))
    else:
      # Test Wifi signal strength for each service
      if not isinstance(self.args.services, list):
        self.args.services = [self.args.services]
      for name, password in self.args.services:
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
          logging.warning('Already connected to %s', name)
        else:
          logging.info('Connecting to %s', name)
          FlimConfigureService(flim, name, password)
          success, diagnostics = flim.ConnectService(service=service)
          if not success:
            self.fail('Unable to connect to %s, diagnostics %s' % (name,
                                                                   diagnostics))
          else:
            factory.console.info('Successfully connected to service %s' % name)

        ethernet_ip = GetEthernetIp()
        if ethernet_ip:
          self.fail('Still got ethernet ip %r' % ethernet_ip)

        Spawn(['ifconfig'], check_call=True, log=True)

        # Try to download file if needed.
        if self.args.test_url is not None:
          ret = self._DownloadFileAndMeasureThroughput()
          Log('downloading_file',
              result=ret['result'],
              file_size=ret['file_size'],
              time_spent=ret['time_spent'],
              throughput=ret['throughput'])
          if not ret['result']:
            self.fail('Failed to connect to url %s' % self.args.test_url)
          if (self.args.throughput_threshold is not None and
              ret['throughput'] < self.args.throughput_threshold):
            self.fail(
                "Throughput: %f < %f bytes/sec didn't meet the requirement." % (
                    ret['throughput'], self.args.throughput_threshold))

        logging.info('Disconnecting %s', name)
        flim.DisconnectService(service)
