#!/usr/bin/env python
# Copyright 2012 The Chromium OS Authors. All rights reserved.
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

import factory_common  # pylint: disable=unused-import
from cros.factory.shopfloor import factory_server
from cros.factory.test.env import paths
from cros.factory.umpire.client import umpire_server_proxy
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils


REGISTRATION_CODE_LOG_CSV = 'registration_code_log.csv'


class FactoryServerTest(unittest.TestCase):

  def setUp(self):
    """Starts shop floor server and creates client proxy."""
    # pylint: disable=protected-access
    self.base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    self.data_dir = tempfile.mkdtemp(prefix='shopfloor_data.')
    self.auto_archive_logs = os.path.join(self.data_dir, 'auto-archive-logs')
    self.logs_dir = os.path.join(self.data_dir, time.strftime('logs.%Y%m%d'))
    self.reports_dir = os.path.join(
        self.data_dir, factory_server.REPORTS_DIR,
        time.strftime(factory_server.LOGS_DIR_FORMAT))
    self.aux_logs_dir = os.path.join(
        self.data_dir, factory_server.AUX_LOGS_DIR,
        time.strftime(factory_server.LOGS_DIR_FORMAT))
    self.events_dir = os.path.join(
        self.data_dir, factory_server.EVENTS_DIR)
    self.parameters_dir = os.path.join(self.data_dir, 'parameters')
    self.registration_code_log = (
        os.path.join(self.data_dir, REGISTRATION_CODE_LOG_CSV))
    csv_source = os.path.join(self.base_dir, 'testdata', 'devices.csv')
    csv_work = os.path.join(self.data_dir, 'devices.csv')
    aux_csv_source = os.path.join(self.base_dir, 'testdata', 'aux_mlb.csv')
    aux_csv_work = os.path.join(self.data_dir, 'aux_mlb.csv')

    shutil.copyfile(csv_source, csv_work)
    shutil.copyfile(aux_csv_source, aux_csv_work)

    self.server_port = net_utils.FindUnusedTCPPort()
    # Use factory_server.py (or the SHOPFLOOR_SERVER_CMD environment
    # variable if set).
    cmd = os.environ.get(
        'SHOPFLOOR_SERVER_CMD',
        'python %s' % os.path.join(
            self.base_dir, 'factory_server.py')).split(' ')

    cmd.extend([
        '-a', net_utils.LOCALHOST, '-p', str(self.server_port),
        '-d', self.data_dir,
        '--auto-archive-logs', os.path.join(self.auto_archive_logs,
                                            'logs.DATE.tar.bz2')])
    self.process = process_utils.Spawn(cmd, log=True)
    self.proxy = umpire_server_proxy.TimeoutUmpireServerProxy(
        'http://%s:%s' % (net_utils.LOCALHOST, self.server_port),
        allow_none=True)

    def _ServerUp():
      try:
        self.proxy.Ping()
        return True
      except Exception:
        return False
    sync_utils.WaitFor(_ServerUp, 2)

  def tearDown(self):
    """Terminates shop floor server"""
    self.process.terminate()
    self.process.wait()
    shutil.rmtree(self.data_dir)

  def _CreateFileAndContextAsFilename(self, filename):
    file_utils.TryMakeDirs(os.path.dirname(filename))
    with open(filename, 'w') as fd:
      fd.write(os.path.basename(filename))

  def testListParameters(self):
    # Make few temporary files.
    wifi_production = set(['rf/wifi/parameters.production'])
    wifi_calibration = set(['rf/wifi/calibration_config.1',
                            'rf/wifi/calibration_config.2'])
    cell_production = set(['rf/cell/parameters.production'])

    for filename in wifi_production | wifi_calibration | cell_production:
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
    wifi_production = 'parameters.production'
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

  def testSaveAuxLog(self):
    self.proxy.SaveAuxLog('foo/bar', factory_server.Binary('Blob'))
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
      file_utils.TryMakeDirs(os.path.dirname(factory_log_path))
      open(factory_log_path, 'w').close()
      return process_utils.Spawn([
          'tar', '-c' + ('j' if compress else '') + 'f', '-', '-C', tmp,
          content_path.lstrip('/')], check_output=True).stdout_data
    finally:
      shutil.rmtree(tmp)

  def testUploadCorruptReport_Empty(self):
    self.assertRaisesRegexp(
        xmlrpclib.Fault,
        'This does not look like a tar archive',
        self.proxy.UploadReport, 'CR001020', factory_server.Binary(''), 'foo')

  def testUploadCorruptReport_MissingLog(self):
    self.assertRaisesRegexp(
        xmlrpclib.Fault,
        paths.FACTORY_LOG_PATH_ON_DEVICE.lstrip('/') + ' missing',
        self.proxy.UploadReport, 'CR001020',
        factory_server.Binary(self._MakeTarFile('foo')), 'foo')

  def testUploadCorruptReport_CorruptBZ2(self):
    tbz2 = self._MakeTarFile('foo')
    tbz2 = tbz2[:-1]  # Truncate the file
    self.assertRaisesRegexp(
        xmlrpclib.Fault,
        'Compressed file ends unexpectedly',
        self.proxy.UploadReport, 'CR001020',
        factory_server.Binary(tbz2), 'foo')

  def testUploadReport(self):
    self.proxy.SetReportHourlyRotation(False)
    # Upload simple blob
    blob = self._MakeTarFile(paths.FACTORY_LOG_PATH_ON_DEVICE)

    report_name = 'simple_blob.rpt.bz2'
    report_path = os.path.join(self.reports_dir, report_name)
    self.proxy.UploadReport('CR001020', factory_server.Binary(blob),
                            report_name)
    self.assertEquals(blob, open(report_path).read())
    self.assertTrue(re.match(r'^[0-9a-f]{32}\s',
                             open(report_path + '.md5').read()))

    # Try to upload to invalid serial number
    self.assertRaises(xmlrpclib.Fault, self.proxy.UploadReport, 'CR00200', blob)

    # Move the report to yesterday's dir.  "Insert" some media and
    # check that the logs are archived.
    yesterday_localtime = time.localtime(time.time() - 24 * 60 * 60)
    yesterday = time.strftime(factory_server.LOGS_DIR_FORMAT,
                              yesterday_localtime)
    shutil.move(self.reports_dir, os.path.join(
        self.data_dir, factory_server.REPORTS_DIR, yesterday))

    os.makedirs(self.auto_archive_logs)
    dest_path = os.path.join(
        self.auto_archive_logs,
        time.strftime('logs.%Y%m%d.tar.bz2', yesterday_localtime))

    def _CheckArchive():
      return os.path.exists(dest_path)
    sync_utils.WaitFor(_CheckArchive, 3)

  def testLogRegistrationCode(self):
    valid_code = ('000000000000000000000000000000000000'
                  '0000000000000000000000000000190a55ad')
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
    board = 'MAGICA'
    hwid = 'MAGICA MADOKA A-A 1214'
    csv_name = os.path.splitext(REGISTRATION_CODE_LOG_CSV)[0]
    self.proxy.UploadCSVEntry(csv_name, [board, valid_code, valid_code, timestamp, hwid])

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


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
