#!/usr/bin/env python3
#
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Output factory report plugin.

A plugin to process archives which are uploaded py partners. This plugin will do
the following things:
  1. Download archives from Google Cloud Storage
  2. Decompress factory reports from the archive
  3. Process and parse factory report
  4. Generate a report event with some information
  5. Generate a process event with some process status during parsing
"""

import copy
import logging
import json
import multiprocessing
import os
import re
import shutil
import tarfile
import time
import zipfile

import yaml

from cros.factory.instalog import datatypes
from cros.factory.instalog import plugin_base
from cros.factory.instalog.utils.arg_utils import Arg
from cros.factory.instalog.utils import file_utils
from cros.factory.instalog.utils import gcs_utils
from cros.factory.instalog.utils import time_utils


_PROCESSES_NUMBER = 20
REPORT_EVENT_FIELD = {
    'apiVersion', 'dutDeviceId', 'stationDeviceId', 'stationInstallationId'
}
PATTERN_WP_STATUS = re.compile(r'WP: status: (\w+)')
PATTERN_WP = re.compile(r'WP: write protect is (\w+)\.')


class OutputFactoryReport(plugin_base.OutputPlugin):

  ARGS = [
      Arg('key_path', str,
          'Path to BigQuery/CloudStorage service account JSON key file.'),
  ]

  def __init__(self, *args, **kwargs):
    super(OutputFactoryReport, self).__init__(*args, **kwargs)
    self._gcs = None
    self._archive_path = None
    self._tmp_dir = None
    self._process_pool = None

  def SetUp(self):
    """Sets up the plugin."""
    self._gcs = gcs_utils.CloudStorage(self.args.key_path)
    self._archive_path = os.path.join(self.GetDataDir(), 'archive')
    self._tmp_dir = os.path.join(self.GetDataDir(), 'tmp')

    self._process_pool = multiprocessing.Pool(processes=_PROCESSES_NUMBER)

  def TearDown(self):
    if os.path.exists(self._tmp_dir):
      shutil.rmtree(self._tmp_dir)

    self._process_pool.close()
    self._process_pool.join()

  def Main(self):
    """Main thread of the plugin."""
    while not self.IsStopping():
      if not self.DownloadAndProcess():
        self.Sleep(1)

  def EmitAndCommit(self, events, event_stream):
    if self.Emit(events):
      event_stream.Commit()
    else:
      event_stream.Abort()

  def GetReportPath(self, report_id):
    return os.path.join(self._tmp_dir, 'report_%d' % report_id)

  def DownloadAndProcess(self):
    """Download Archive file from GCS and process it."""
    event_stream = self.NewStream()
    if not event_stream:
      return False

    event = event_stream.Next()
    if not event:
      event_stream.Commit()
      return False

    archive_process_event = datatypes.Event({
        '__process__': True,
        'status': [],
        'time': 0,
        'startTime': time.time(),
        'message': []
    })

    gcs_path = event.get('objectId', None)

    if not gcs_path:
      SetProcessEventStatus(100, archive_process_event, self.logger.name,
                            event.Serialize())
      self.EmitAndCommit([archive_process_event], event_stream)
      return True

    archive_process_event['uuid'] = gcs_path

    if os.path.exists(self._tmp_dir):
      shutil.rmtree(self._tmp_dir)
    file_utils.TryMakeDirs(self._tmp_dir)
    file_utils.TryUnlink(self._archive_path)

    # A log file may have multiple factory report files.
    self.info('Download log file from Google Storage: %s', gcs_path)
    if not self._gcs.DownloadFile(gcs_path, self._archive_path, overwrite=True):
      self.error('Failed to download the file: %s', gcs_path)
      event_stream.Abort()
      return False
    if self.IsStopping():
      return False

    report_events = [archive_process_event]
    async_results = []
    report_file_path = []
    total_reports = 0
    succeed = 0
    archive_obj = None
    try:
      if zipfile.is_zipfile(self._archive_path):
        archive_obj = zipfile.ZipFile(self._archive_path, 'r')
        for member_name in archive_obj.namelist():
          if self.IsStopping():
            return False
          if not member_name.endswith('.rpt.xz'):
            continue

          report_path = self.GetReportPath(total_reports)
          report_file_path.append(member_name)
          with open(report_path, 'wb') as dst_f:
            with archive_obj.open(member_name, 'r') as src_f:
              shutil.copyfileobj(src_f, dst_f)
          total_reports += 1
      elif tarfile.is_tarfile(self._archive_path):
        archive_obj = tarfile.open(self._archive_path, 'r')
        for archive_member in archive_obj:
          if self.IsStopping():
            return False
          if not archive_member.name.endswith('.rpt.xz'):
            continue

          report_path = self.GetReportPath(total_reports)
          report_file_path.append(archive_member.name)
          with open(report_path, 'wb') as f:
            report_obj = archive_obj.extractfile(archive_member)
            shutil.copyfileobj(report_obj, f)
          total_reports += 1
      else:
        # We only support tar file and zip file.
        SetProcessEventStatus(200, archive_process_event, self.logger.name)
        self.EmitAndCommit(report_events, event_stream)
        return True
    except Exception as e:
      SetProcessEventStatus(299, archive_process_event, self.logger.name, e)
      self.exception('Exception encountered when decompressing archive file')
      self.EmitAndCommit(report_events, event_stream)
      return True
    finally:
      try:
        if archive_obj:
          archive_obj.close()
      except Exception:
        self.exception('Exception encountered when closing archive object')

    archive_process_event['decompressEndTime'] = time.time()

    try:
      for report_i in range(total_reports):
        # TODO(chuntsen): Find a way to stop process pool.
        report_path = self.GetReportPath(report_i)
        report_time = time.mktime(
            time.strptime(report_file_path[report_i].rpartition('-')[-1],
                          '%Y%m%dT%H%M%SZ.rpt.xz'))
        if (archive_process_event['time'] == 0 or
            report_time < archive_process_event['time']):
          archive_process_event['time'] = report_time
        uuid = time_utils.TimedUUID()
        report_event = datatypes.Event({
            '__report__': True,
            'uuid': uuid,
            'objectId': gcs_path,
            'reportFilePath': report_file_path[report_i],
            'time': report_time,
            'serialNumbers': {}
        })
        process_event = datatypes.Event({
            '__process__': True,
            'uuid': uuid,
            'time': report_time,
            'startTime': time.time(),
            'status': [],
            'message': []
        })
        async_results.append(
            self._process_pool.apply_async(
                DecompressAndParse, (report_path, report_event, process_event,
                                     self._tmp_dir, self.logger.name)))

      for report_i in range(total_reports):
        # TODO(chuntsen): Find a way to stop process pool.
        async_result = async_results[report_i]
        report_event = None
        try:
          report_event, process_event = async_result.get()
        except Exception as e:
          SetProcessEventStatus(399, process_event, self.logger.name, e)
          self.exception('Exception encountered when processing factory report')
        if report_event:
          report_events.append(report_event)
          succeed += 1
        process_event['duration'] = (
            process_event['endTime'] - process_event['startTime'])
        report_events.append(process_event)
        if succeed % 100 == 0:
          self.info('Parsed %d/%d reports', succeed, total_reports)

      self.info('Parsed %d/%d reports', succeed, total_reports)
    except Exception:
      self.exception('Exception encountered')

    archive_process_event['endTime'] = time.time()
    archive_process_event['duration'] = (
        archive_process_event['endTime'] - archive_process_event['startTime'])
    self.EmitAndCommit(report_events, event_stream)
    return True


def DecompressAndParse(report_path, report_event, process_event, tmp_dir,
                       logger_name):
  """Decompress factory report and parse it."""
  with file_utils.TempDirectory(dir=tmp_dir) as report_dir:
    if not tarfile.is_tarfile(report_path):
      SetProcessEventStatus(300, process_event, logger_name)
      process_event['endTime'] = time.time()
      return None, process_event
    report_tar = tarfile.open(report_path, 'r:xz')
    report_tar.extractall(report_dir)
    process_event['decompressEndTime'] = time.time()

    testlog_path = os.path.join(report_dir, 'var', 'factory', 'testlog',
                                'events.json')
    eventlog_path = os.path.join(report_dir, 'events')
    if os.path.exists(eventlog_path):
      eventlog_report_event, process_event = ParseEventlogEvents(
          eventlog_path, copy.deepcopy(report_event), process_event,
          logger_name)
      if eventlog_report_event:
        report_event = eventlog_report_event
    else:
      SetProcessEventStatus(400, process_event, logger_name)
    if os.path.exists(testlog_path):
      testlog_report_event, process_event = ParseTestlogEvents(
          testlog_path, copy.deepcopy(report_event), process_event, logger_name)
      if testlog_report_event:
        report_event = testlog_report_event
    else:
      SetProcessEventStatus(500, process_event, logger_name)
    process_event['endTime'] = time.time()
    return report_event, process_event


def ParseEventlogEvents(path, report_event, process_event, logger_name):
  """Parse Eventlog file."""
  logger = logging.getLogger(logger_name)

  try:
    for event in yaml.safe_load_all(open(path, 'r')):
      if event:
        if not isinstance(event, dict):
          # TODO(chuntsen): Add a process event.
          continue

        def GetField(field, dct, key, is_string=True):
          if key in dct:
            if not is_string or isinstance(dct[key], str):
              report_event[field] = dct[key]
            else:
              SetProcessEventStatus(401, process_event, logger_name)
              report_event[field] = str(dct[key])

        serial_numbers = event.get('serial_numbers', {})
        for sn_key, sn_value in serial_numbers.items():
          if not isinstance(sn_value, str):
            SetProcessEventStatus(401, process_event, logger_name)
            sn_value = str(sn_value)
          report_event['serialNumbers'][sn_key] = sn_value

        event_name = event.get('EVENT', None)
        if event_name == 'system_details':
          crossystem = event.get('crossystem', {})
          GetField('hwid', crossystem, 'hwid')
          if 'hwid' in report_event:
            report_event['modelName'] = report_event['hwid'].split(' ')[0]
          GetField('fwid', crossystem, 'fwid')
          GetField('roFwid', crossystem, 'ro_fwid')
          GetField('wpswBoot', crossystem, 'wpsw_boot')
          GetField('wpswCur', crossystem, 'wpsw_cur')
          GetField('ecWpDetails', event, 'ec_wp_status')
          if 'ecWpDetails' in report_event:
            result = PATTERN_WP_STATUS.findall(report_event['ecWpDetails'])
            if len(result) == 1:
              report_event['ecWpStatus'] = result[0]
            result = PATTERN_WP.findall(report_event['ecWpDetails'])
            if len(result) == 1:
              report_event['ecWp'] = result[0]
          GetField('biosWpDetails', event, 'bios_wp_status')
          if 'biosWpDetails' in report_event:
            result = PATTERN_WP_STATUS.findall(report_event['biosWpDetails'])
            if len(result) == 1:
              report_event['biosWpStatus'] = result[0]
            result = PATTERN_WP.findall(report_event['biosWpDetails'])
            if len(result) == 1:
              report_event['biosWp'] = result[0]
          GetField('modemStatus', event, 'modem_status')
          GetField('platformName', event, 'platform_name')
        elif event_name == 'finalize_image_version':
          GetField('factoryImageVersion', event, 'factory_image_version')
          GetField('releaseImageVersion', event, 'release_image_version')
        elif event_name == 'preamble':
          GetField('toolkitVersion', event, 'toolkit_version')
        elif event_name == 'test_states':

          def ParseTestStates(test_states, test_states_list):
            if 'subtests' in test_states:
              for subtest in test_states['subtests']:
                ParseTestStates(subtest, test_states_list)
            if 'status' in test_states:
              test_states_list.append(
                  (test_states['path'], test_states['status']))

          test_states_list = []
          testlist_name = None
          testlist_station_set = set()

          ParseTestStates(event['test_states'], test_states_list)
          for test_path, unused_test_status in test_states_list:
            if ':' in test_path:
              testlist_name, test_path = test_path.split(':')
            testlist_station = test_path.split('.')[0]
            testlist_station_set.add(testlist_station)

          report_event['testStates'] = test_states_list
          if testlist_name:
            report_event['testlistName'] = testlist_name
          report_event['testlistStation'] = json.dumps(
              list(testlist_station_set))
    return report_event, process_event
  except Exception as e:
    SetProcessEventStatus(499, process_event, logger_name, e)
    logger.exception('Failed to parse eventlog events')
    return None, process_event


def ParseTestlogEvents(path, report_event, process_event, logger_name):
  """Parse Testlog file."""
  logger = logging.getLogger(logger_name)

  try:
    with open(path, 'r') as f:
      for line in f:
        # Remove null characters because of file sync issue.
        # See http://b/163472674 .
        if '\0' in line:
          SetProcessEventStatus(501, process_event, logger_name)
        event = datatypes.Event.Deserialize(line.strip('\0'))

        if 'serialNumbers' in event:
          for sn_key, sn_value in event['serialNumbers'].items():
            if not isinstance(sn_value, str):
              SetProcessEventStatus(502, process_event, logger_name)
              sn_value = str(sn_value)
            report_event['serialNumbers'][sn_key] = sn_value
        if 'time' in event:
          report_event['dutTime'] = event['time']

        for field in REPORT_EVENT_FIELD:
          if field in event:
            report_event[field] = event[field]

        if event.get('testType', None) == 'hwid':
          data = event.get('parameters', {}).get('phase', {}).get('data', {})
          if len(data) == 1 and 'textValue' in data[0]:
            report_event['phase'] = data[0]['textValue']
    return report_event, process_event
  except Exception as e:
    SetProcessEventStatus(599, process_event, logger_name, e)
    logger.exception('Failed to parse testlog events')
    return None, process_event


# pylint: disable=unused-argument
def SetProcessEventStatus(code, process_event, logger_name, message=None):
  """Set status and message to process_event."""
  # TODO(chuntsen): Finish this error code system.


if __name__ == '__main__':
  plugin_base.main()
