#!/usr/bin/env python

# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for shop floor server."""

from __future__ import print_function

import logging
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
import xmlrpclib

import factory_common  # pylint: disable=W0611
from cros.factory import shopfloor
from cros.factory.shopfloor import factory_update_server
from cros.factory.test import factory
from cros.factory.test import utils
from cros.factory.umpire.client import umpire_server_proxy
from cros.factory.utils import net_utils
from cros.factory.utils import test_utils
from cros.factory.utils.process_utils import Spawn


class ShopFloorServerTest(unittest.TestCase):
  def setUp(self):
    '''Starts shop floor server and creates client proxy.'''
    # pylint: disable=W0212
    self.server_port = test_utils.FindUnusedTCPPort()
    self.base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    self.data_dir = tempfile.mkdtemp(prefix='shopfloor_data.')
    self.auto_archive_logs = os.path.join(self.data_dir, 'auto-archive-logs')
    self.logs_dir = os.path.join(self.data_dir, time.strftime('logs.%Y%m%d'))
    self.reports_dir = os.path.join(
        self.data_dir, shopfloor.REPORTS_DIR,
        time.strftime(shopfloor.LOGS_DIR_FORMAT))
    self.aux_logs_dir = os.path.join(
        self.data_dir, shopfloor.AUX_LOGS_DIR,
        time.strftime(shopfloor.LOGS_DIR_FORMAT))
    self.events_dir = os.path.join(
        self.data_dir, shopfloor.EVENTS_DIR)
    self.parameters_dir = os.path.join(self.data_dir, 'parameters')
    self.registration_code_log = (
        os.path.join(self.data_dir, shopfloor.REGISTRATION_CODE_LOG_CSV))
    csv_source = os.path.join(self.base_dir, 'testdata', 'devices.csv')
    csv_work = os.path.join(self.data_dir, 'devices.csv')
    aux_csv_source = os.path.join(self.base_dir, 'testdata', 'aux_mlb.csv')
    aux_csv_work = os.path.join(self.data_dir, 'aux_mlb.csv')

    shutil.copyfile(csv_source, csv_work)
    shutil.copyfile(aux_csv_source, aux_csv_work)
    os.mkdir(os.path.join(self.data_dir, shopfloor.UPDATE_DIR))
    os.mkdir(os.path.join(self.data_dir, shopfloor.UPDATE_DIR, 'factory'))

    factory_update_server.poll_interval_sec = 0.1
    # Use shopfloor_server.py (or the SHOPFLOOR_SERVER_CMD environment
    # variable if set).
    cmd = os.environ.get(
        'SHOPFLOOR_SERVER_CMD',
        'python %s' % os.path.join(
            self.base_dir, 'shopfloor_server.py')).split(' ')

    cmd.extend([
        '-q', '-a', net_utils.LOCALHOST, '-p', str(self.server_port),
        '-m', 'cros.factory.shopfloor.simple_shopfloor',
        '-d', self.data_dir,
        '--auto-archive-logs', os.path.join(self.auto_archive_logs,
                                            'logs.DATE.tar.bz2')])
    self.process = Spawn(cmd, log=True)
    self.proxy = umpire_server_proxy.TimeoutUmpireServerProxy(
        'http://%s:%s' % (net_utils.LOCALHOST, self.server_port),
        allow_none=True)
    # Waits the server to be ready, up to 1 second.
    for _ in xrange(10):
      try:
        self.proxy.Ping()
        break
      except:  # pylint: disable=W0702
        time.sleep(0.1)
        continue
    else:
      self.fail('Server never came up')

  def tearDown(self):
    '''Terminates shop floor server'''
    self.process.terminate()
    self.process.wait()
    shutil.rmtree(self.data_dir)

  def testCheckSN(self):
    # Valid serial numbers range from CR001001 to CR001025
    for i in range(25):
      serial = 'CR0010%02d' % (i + 1)
      self.assertTrue(self.proxy.CheckSN(serial))

    # Test invalid serial numbers
    self.assertRaises(xmlrpclib.Fault, self.proxy.CheckSN, '0000')
    self.assertRaises(xmlrpclib.Fault, self.proxy.CheckSN, 'garbage')
    self.assertRaises(xmlrpclib.Fault, self.proxy.CheckSN, '')
    self.assertRaises(xmlrpclib.Fault, self.proxy.CheckSN, None)
    self.assertRaises(xmlrpclib.Fault, self.proxy.CheckSN, 'CR001000')
    self.assertRaises(xmlrpclib.Fault, self.proxy.CheckSN, 'CR001026')

  def _CreateFileAndContextAsFilename(self, filename):
    utils.TryMakeDirs(os.path.dirname(filename))
    with open(filename, "w") as fd:
      fd.write(os.path.basename(filename))

  def testListParameters(self):
    # Make few temporary files.
    wifi_production = set(["rf/wifi/parameters.production"])
    wifi_calibration = set(["rf/wifi/calibration_config.1",
                            "rf/wifi/calibration_config.2"])
    cell_production = set(["rf/cell/parameters.production"])

    for filename in (wifi_production | wifi_calibration | cell_production):
      self._CreateFileAndContextAsFilename(
          os.path.join(self.parameters_dir, filename))
    self.assertEqual(set(self.proxy.ListParameters('rf/wifi/*')),
                     (wifi_production | wifi_calibration))
    self.assertEqual(set(self.proxy.ListParameters('rf/wifi/calibration*')),
                     wifi_calibration)
    # Because ListParameters is not recursive, this should be empty set.
    self.assertEqual(set(self.proxy.ListParameters('*')), set())
    self.assertEqual(set(self.proxy.ListParameters('rf/*/parameters.*')),
                     (wifi_production | cell_production))
    # Listing files outside parameters directory should raise an exception.
    self.assertRaises(xmlrpclib.Fault, self.proxy.ListParameters, 'rf/../../*')

  def testGetParameter(self):
    wifi_production = "parameters.production"
    relpath = os.path.join('rf/wifi/', wifi_production)
    self._CreateFileAndContextAsFilename(
        os.path.join(self.parameters_dir, relpath))
    # Get valid parameter.
    self.assertEquals(wifi_production, self.proxy.GetParameter(relpath).data)
    # Get parameter that doesn't exist
    self.assertRaises(xmlrpclib.Fault, self.proxy.GetParameter, relpath + 'foo')
    self.assertRaises(xmlrpclib.Fault, self.proxy.GetParameter, 'rf/wifi')
    # Get parameter outside parameters folder.
    self.assertRaises(
        xmlrpclib.Fault, self.proxy.GetParameter, '../devices.csv')

  def testGetHWID(self):
    # Valid HWIDs range from CR001001 to CR001025
    for i in range(25):
      serial = 'CR0010%02d' % (i + 1)
      result = self.proxy.GetHWID(serial)
      self.assertTrue(result.startswith('MAGICA '))
      self.assertEqual(len(result.split(' ')), 4)

  def testGetHWIDUpdater(self):
    self.assertEquals(None, self.proxy.GetHWIDUpdater())

    # Add a HWID updater; the update server will start serving it within
    # a second.
    with open(os.path.join(self.data_dir, shopfloor.UPDATE_DIR,
                           'hwid_updater.sh'), 'w') as f:
      f.write('foobar')

    for _ in xrange(20):
      updater = self.proxy.GetHWIDUpdater()
      if updater:
        self.assertEqual('foobar', updater.data)
        break
      time.sleep(0.1)
    else:
      self.fail('HWID updater was never picked up')

    # Add another file; now there should be no updater returned since
    # this is an invalid state.
    open(os.path.join(self.data_dir, shopfloor.UPDATE_DIR,
                      'hwid_updater2.sh'), 'w').close()
    for _ in xrange(20):
      if self.proxy.GetHWIDUpdater() is None:
        break  # Good!
      time.sleep(0.1)
    else:
      self.fail('HWID updater never reverted to None')

  def testGetVPD(self):
    # VPD fields defined in simple.csv
    RO_FIELDS = ('keyboard_layout', 'initial_locale', 'initial_timezone')
    RW_FIELDS_SET1 = ('wifi_mac', 'cellular_mac')
    RW_FIELDS_SET2 = ('wifi_mac', )

    vpd = self.proxy.GetVPD('CR001005')
    for field in RO_FIELDS:
      self.assertTrue(field in vpd['ro'] and vpd['ro'][field])
    for field in RW_FIELDS_SET1:
      self.assertTrue(field in vpd['rw'] and vpd['rw'][field])
    self.assertEqual(vpd['ro']['keyboard_layout'], 'xkb:us::eng')
    self.assertEqual(vpd['ro']['initial_locale'], 'en-US')
    self.assertEqual(vpd['ro']['initial_timezone'], 'America/Los_Angeles')
    self.assertEqual(vpd['rw']['wifi_mac'], '0b:ad:f0:0d:15:05')
    self.assertEqual(vpd['rw']['cellular_mac'], '70:75:65:6c:6c:65')

    vpd = self.proxy.GetVPD('CR001016')
    for field in RO_FIELDS:
      self.assertTrue(field in vpd['ro'] and vpd['ro'][field])
    for field in RW_FIELDS_SET2:
      self.assertTrue(field in vpd['rw'] and vpd['rw'][field])
    self.assertEqual(vpd['ro']['keyboard_layout'], 'xkb:us:intl:eng')
    self.assertEqual(vpd['ro']['initial_locale'], 'nl')
    self.assertEqual(vpd['ro']['initial_timezone'], 'Europe/Amsterdam')
    self.assertEqual(vpd['rw']['wifi_mac'], '0b:ad:f0:0d:15:10')
    self.assertEqual(vpd['rw']['cellular_mac'], '')

    # Checks MAC addresses
    for i in range(25):
      serial = 'CR0010%02d' % (i + 1)
      vpd = self.proxy.GetVPD(serial)
      wifi_mac = vpd['rw']['wifi_mac']
      self.assertEqual(wifi_mac, "0b:ad:f0:0d:15:%02x" % (i + 1))
      if i < 5:
        cellular_mac = vpd['rw']['cellular_mac']
        self.assertEqual(cellular_mac, "70:75:65:6c:6c:%02x" % (i + 0x61))

    # Checks invalid serial numbers
    self.assertRaises(xmlrpclib.Fault, self.proxy.GetVPD, 'MAGICA')
    return True

  def testSaveAuxLog(self):
    self.proxy.SaveAuxLog('foo/bar', shopfloor.Binary('Blob'))
    self.assertEquals(
        'Blob',
        open(os.path.join(self.aux_logs_dir, 'foo/bar')).read())

  def _MakeTarFile(self, content_path, compress=True):
    """Makes a tar archive containing a single empty file.

    Args:
      content_path: The path to the empty file within the archive.

    Returns: The tar archive contents as a string.
    """
    tmp = tempfile.mkdtemp('tar')
    try:
      factory_log_path = os.path.join(
          tmp, content_path.lstrip('/'))
      utils.TryMakeDirs(os.path.dirname(factory_log_path))
      open(factory_log_path, 'w').close()
      return Spawn([
          'tar', '-c' + ('j' if compress else '') + 'f', '-', '-C', tmp,
          content_path.lstrip('/')],
                   check_output=True).stdout_data
    finally:
      shutil.rmtree(tmp)

  def testUploadCorruptReport_Empty(self):
    self.assertRaisesRegexp(
        xmlrpclib.Fault,
        'This does not look like a tar archive',
        self.proxy.UploadReport, 'CR001020', shopfloor.Binary(''), 'foo')

  def testUploadCorruptReport_MissingLog(self):
    self.assertRaisesRegexp(
        xmlrpclib.Fault,
        factory.FACTORY_LOG_PATH_ON_DEVICE.lstrip('/') + ' missing',
        self.proxy.UploadReport, 'CR001020',
        shopfloor.Binary(self._MakeTarFile('foo')), 'foo')

  def testUploadCorruptReport_CorruptBZ2(self):
    tbz2 = self._MakeTarFile('foo')
    tbz2 = tbz2[:-1]  # Truncate the file
    self.assertRaisesRegexp(
        xmlrpclib.Fault,
        'Compressed file ends unexpectedly',
        self.proxy.UploadReport, 'CR001020',
        shopfloor.Binary(tbz2), 'foo')

  def testUploadReportWithHourlyRotation(self):
    # Other things should be well covered by the testUploadReport.
    # We only test if the hourly rotating directory created as expected.
    blob = self._MakeTarFile(factory.FACTORY_LOG_PATH_ON_DEVICE)

    report_name = 'hourly_report_blob.rpt.bz2'
    # Test the SetReportHourlyRotation is working.
    self.assertFalse(self.proxy.SetReportHourlyRotation(False))
    self.assertTrue(self.proxy.SetReportHourlyRotation(True))
    expected_report_path = os.path.join(
        self.proxy.GetReportsDir(), report_name)
    # TODO(itspeter): It might be a risk of low possibility that hour of
    # getting the path are different when the RPC call is actually made.
    # A re-run of make test should immediate fix that : )
    self.proxy.UploadReport('CR001020', shopfloor.Binary(blob),
                            report_name)
    self.assertEquals(blob, open(expected_report_path).read())

  def testUploadEventWithHourlyRotataion(self):
    # Other things should be well covered by the testUploadEvent.
    # We only test if the hourly rotating directory created as expected.
    # Test the SetEventHourlyRotation is working.
    self.assertFalse(self.proxy.SetEventHourlyRotation(False))
    self.assertTrue(self.proxy.SetEventHourlyRotation(True))
    incremental_event_file = os.path.join(
        self.proxy.GetIncrementalEventsDir(), 'LOG_tradasai')
    self.assertTrue(self.proxy.UploadEvent('LOG_tradasai',
                                           'PREAMBLE\n---\nEVENT_1\n'))
    # There is a low possibility flaky that hour of getting the path
    # are different when the RPC call is actually made.
    # A re-run of make test should immediate fix that : )
    self.assertTrue(os.path.isfile(incremental_event_file))
    with open(incremental_event_file, 'r') as f:
      events = [event.strip() for event in f.read().split('---')]
      self.assertEqual(events[0], 'PREAMBLE')
      self.assertEqual(events[1], 'EVENT_1')

  def testUploadReport(self):
    # Upload simple blob
    blob = self._MakeTarFile(factory.FACTORY_LOG_PATH_ON_DEVICE)

    report_name = 'simple_blob.rpt.bz2'
    report_path = os.path.join(self.reports_dir, report_name)
    self.proxy.UploadReport('CR001020', shopfloor.Binary(blob),
                            report_name)
    self.assertEquals(blob, open(report_path).read())
    self.assertTrue(re.match('^[0-9a-f]{32}\s',
                             open(report_path + '.md5').read()))

    # Try to upload to invalid serial number
    self.assertRaises(xmlrpclib.Fault, self.proxy.UploadReport, 'CR00200', blob)

    # Move the report to yesterday's dir.  "Insert" some media and
    # check that the logs are archived.
    yesterday_localtime = time.localtime(time.time() - 24*60*60)
    yesterday = time.strftime(shopfloor.LOGS_DIR_FORMAT, yesterday_localtime)
    shutil.move(self.reports_dir,
                os.path.join(self.data_dir, shopfloor.REPORTS_DIR, yesterday))

    os.makedirs(self.auto_archive_logs)
    dest_path = os.path.join(
        self.auto_archive_logs,
        time.strftime('logs.%Y%m%d.tar.bz2', yesterday_localtime))
    for _ in xrange(20):
      if os.path.exists(dest_path):
        break
      time.sleep(.1)
    else:
      self.fail('%s was never created' % dest_path)

  def testFinalize(self):
    self.proxy.Finalize('CR001024')
    self.assertRaises(xmlrpclib.Fault, self.proxy.Finalize, '0999')

  def testGetTestMd5sum(self):
    shutil.copyfile(os.path.join(os.path.dirname(__file__),
                                 'testdata', 'factory.tar.bz2'),
                    os.path.join(self.data_dir, shopfloor.UPDATE_DIR,
                                 'factory.tar.bz2'))

    # It should be unpacked within a second.
    for _ in xrange(20):
      md5sum = self.proxy.GetTestMd5sum()
      if md5sum:
        self.assertEqual('18cac06201e65e060f757193c153cacb', md5sum)
        break
      time.sleep(0.1)
    else:
      self.fail('No update found')

  def testGetTestMd5sumWithoutMd5sumFile(self):
    self.assertTrue(self.proxy.GetTestMd5sum() is None)

  def testGetRegistrationCodeMap(self):
    self.assertEquals(
        {'user': ('000000000000000000000000000000000000'
                  '0000000000000000000000000000190a55ad'),
         'group': ('010101010101010101010101010101010101'
                   '010101010101010101010101010162319fcc')},
        self.proxy.GetRegistrationCodeMap('CR001001'))

    # Make sure it was logged.
    log = open(self.registration_code_log).read()
    self.assertTrue(re.match(
        '^MAGICA,'
        '000000000000000000000000000000000000'
        '0000000000000000000000000000190a55ad,'
        '010101010101010101010101010101010101'
        '010101010101010101010101010162319fcc,'
        '\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d,'
        'MAGICA MADOKA A-A 1214\n', log), repr(log))

  def testLogRegistrationCode(self):
    valid_code = ('000000000000000000000000000000000000'
                  '0000000000000000000000000000190a55ad')
    invalid_code = '1' + valid_code[1:]

    # This should work.
    self.proxy.LogRegistrationCodeMap(
        'MAGICA MADOKA A-A 1214', {'user': valid_code, 'group': valid_code})

    for invalid_map in ({'user': invalid_code, 'group': valid_code},
                        {'user': valid_code, 'group': invalid_code}):
      self.assertRaisesRegexp(
          Exception, "CRC of '10+190a55ad' is invalid",
          self.proxy.LogRegistrationCodeMap,
          'MAGICA MADOKA A-A 1214', invalid_map)

  def testUploadEvent(self):
    # A new event file should be created.
    self.assertTrue(self.proxy.UploadEvent('LOG_C835C718',
                                           'PREAMBLE\n---\nEVENT_1\n'))
    event_file = os.path.join(self.events_dir, 'LOG_C835C718')
    self.assertTrue(os.path.isfile(event_file))

    # Additional events should be appended to existing event files.
    self.assertTrue(self.proxy.UploadEvent('LOG_C835C718',
                                           '---\nEVENT_2\n'))
    with open(event_file, 'r') as f:
      events = [event.strip() for event in f.read().split('---')]
      self.assertEqual(events[0], 'PREAMBLE')
      self.assertEqual(events[1], 'EVENT_1')
      self.assertEqual(events[2], 'EVENT_2')

  def testGetDeviceData(self):
    self.assertEqual({'serial_number': 'MLB00001',
                      'has_lte': True},
                     self.proxy.GetAuxData('mlb', 'MLB00001'))


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
