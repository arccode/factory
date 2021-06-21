#!/usr/bin/env python3
#
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Output factory report plugin.

A plugin to process archives which are uploaded py partners. This plugin will do
the following things:
  1. Download an archive from Google Cloud Storage
  2. Decompress factory reports from the archive
  3. Process and parse factory reports
  4. Generate report events with some information
  5. Generate process events with process status during parsing
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
import traceback
import zipfile

import yaml

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_base
from cros.factory.instalog.utils.arg_utils import Arg
from cros.factory.instalog.utils import file_utils
from cros.factory.instalog.utils import gcs_utils
from cros.factory.instalog.utils import time_utils
from cros.factory.instalog.utils import type_utils


_PROCESSES_NUMBER = 20
REPORT_EVENT_FIELD = {
    'apiVersion', 'dutDeviceId', 'stationDeviceId', 'stationInstallationId'
}
PATTERN_WP_STATUS = re.compile(r'WP: status: (\w+)')
PATTERN_WP = re.compile(r'WP: write protect is (\w+)\.')
PATTERN_SERIAL_NUMBER = re.compile(r'^\s*serial_number: .*$', re.M)
PATTERN_MLB_SERIAL_NUMBER = re.compile(r'^\s*mlb_serial_number: .*$', re.M)
yaml_loader = yaml.CBaseLoader if yaml.__with_libyaml__ else yaml.BaseLoader


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
    if not yaml.__with_libyaml__:
      self.info('Please install LibYAML to speed up this plugin.')
    while not self.IsStopping():
      if not self.DownloadAndProcess():
        self.Sleep(1)

  def EmitAndCommit(self, events, event_stream):
    if self.Emit(events):
      event_stream.Commit()
    else:
      event_stream.Abort()

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
        'time': 0,  # The partitioned table on BigQuery need this field.
        'startTime': time.time(),
        'message': []
    })

    gcs_path = event.get('objectId', None)

    if not gcs_path:
      SetProcessEventStatus(ERROR_CODE.EventNoObjectId, archive_process_event,
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
      return True
    self.info('Download succeed!')

    report_parser = ReportParser(gcs_path, self._archive_path, self._tmp_dir,
                                 self.logger)
    report_events = report_parser.ProcessArchive(archive_process_event,
                                                 self._process_pool)
    self.EmitAndCommit(report_events, event_stream)
    return True


class ReportParser(log_utils.LoggerMixin):
  """A parser to process report archives."""

  def __init__(self, gcs_path, archive_path, tmp_dir, logger=logging):
    """Sets up the parser.

    Args:
      gcs_path: Path to the archive on Google Cloud Storage.
      archive_path: Path to the archive on disk.
      tmp_dir: Temporary directory.
      logger: Logger to use.
    """
    self._archive_path = archive_path
    self._tmp_dir = tmp_dir
    self._gcs_path = gcs_path
    self.logger = logger

  def GetReportPath(self, report_id):
    return os.path.join(self._tmp_dir, 'report_%d' % report_id)

  def ProcessArchive(self, archive_process_event, process_pool):
    """Processes the archive."""
    report_events = [archive_process_event]
    succeed = 0
    async_results = []
    args_queue = multiprocessing.Queue()
    decompress_process = None

    try:
      # TODO(chuntsen): Find a way to stop process pool.
      if zipfile.is_zipfile(self._archive_path):
        decompress_process = multiprocessing.Process(
            target=self.DecompressZipArchive, args=(args_queue, ))
      elif tarfile.is_tarfile(self._archive_path):
        decompress_process = multiprocessing.Process(
            target=self.DecompressTarArchive, args=(args_queue, ))
      else:
        # We only support tar file and zip file.
        SetProcessEventStatus(ERROR_CODE.ArchiveInvalidFormat,
                              archive_process_event)
        return report_events
      decompress_process.start()

      received_obj = args_queue.get()
      # End the process when we receive None.
      while received_obj is not None:
        if isinstance(received_obj, Exception):
          break
        async_results.append(
            process_pool.apply_async(self.ProcessReport, received_obj))
        received_obj = args_queue.get()

      try:
        if isinstance(received_obj, Exception):
          raise received_obj
        decompress_process.join(1)
        decompress_process.close()
        args_queue.close()
        archive_process_event['decompressEndTime'] = time.time()
      except Exception as e:
        SetProcessEventStatus(ERROR_CODE.ArchiveUnknownError,
                              archive_process_event, e)
        self.exception('Exception encountered when decompressing archive file')
        return report_events

      total_reports = len(async_results)
      for async_result in async_results:
        # TODO(chuntsen): Find a way to stop process pool.
        report_event, process_event = async_result.get()

        report_time = report_event['time']
        if (archive_process_event['time'] == 0 or
            report_time < archive_process_event['time']):
          archive_process_event['time'] = report_time

        if report_event:
          report_events.append(report_event)
          succeed += 1
        process_event['duration'] = (
            process_event['endTime'] - process_event['startTime'])
        report_events.append(process_event)
        if succeed % 1000 == 0:
          self.info('Parsed %d/%d reports', succeed, total_reports)

      self.info('Parsed %d/%d reports', succeed, total_reports)
    except Exception:
      self.exception('Exception encountered')

    archive_process_event['endTime'] = time.time()
    archive_process_event['duration'] = (
        archive_process_event['endTime'] - archive_process_event['startTime'])
    return report_events

  def DecompressZipArchive(self, args_queue):
    """Decompresses the ZIP format archive.

    Args:
      args_queue: Process shared queue to send messages.  A message can be
                  arguments for ProcessReport(), exception or None.
    """
    try:
      total_reports = 0
      with zipfile.ZipFile(self._archive_path, 'r') as archive_obj:
        for member_name in archive_obj.namelist():
          if not self.IsValidReportName(member_name):
            continue

          report_path = self.GetReportPath(total_reports)
          with open(report_path, 'wb') as dst_f:
            with archive_obj.open(member_name, 'r') as report_obj:
              shutil.copyfileobj(report_obj, dst_f)
          args_queue.put((member_name, report_path))
          total_reports += 1
    except Exception as e:
      args_queue.put(e)
    finally:
      args_queue.put(None)

  def DecompressTarArchive(self, args_queue):
    """Decompresses the tar archive with compression.

    Args:
      args_queue: Process shared queue to send messages.  A message can be
                  arguments for ProcessReport(), exception or None.
    """
    try:
      total_reports = 0
      # The 'r|*' mode will process data as a stream of blocks, and it may
      # faster than normal 'r:*' mode.
      with tarfile.open(self._archive_path, 'r|*') as archive_obj:
        for archive_member in archive_obj:
          member_name = archive_member.name
          if not self.IsValidReportName(member_name):
            continue

          report_path = self.GetReportPath(total_reports)
          with open(report_path, 'wb') as dst_f:
            report_obj = archive_obj.extractfile(archive_member)
            shutil.copyfileobj(report_obj, dst_f)
          args_queue.put((member_name, report_path))
          total_reports += 1
    except Exception as e:
      args_queue.put(e)
    finally:
      args_queue.put(None)

  def IsValidReportName(self, name):
    name = os.path.basename(name)
    # Report name format: {stage}{opt_name}-{serial}-{gmtime}.rpt.xz
    if name.endswith('.rpt.xz'):
      return True
    # Report name format: {gmtime}_{serial}.tar.xz
    if name.endswith('.tar.xz'):
      try:
        time.strptime(name.partition('_')[0], '%Y%m%dT%H%M%SZ')
        return True
      except ValueError:
        pass
    return False

  def ProcessReport(self, report_file_path, report_path):
    """Processes the factory report.

    Args:
      report_file_path: Path to the factory report in archive.
      report_path: Path to the factory report on disk.

    Returns:
      report_event: A report event with information in the factory report.
      process_event: A process event with process information.
    """
    uuid = time_utils.TimedUUID()
    report_event = datatypes.Event({
        '__report__': True,
        'uuid': uuid,
        'time': 0,  # The partitioned table on BigQuery need this field.
        'objectId': self._gcs_path,
        'reportFilePath': report_file_path,
        'serialNumbers': {}
    })
    process_event = datatypes.Event({
        '__process__': True,
        'uuid': uuid,
        'time': 0,  # The partitioned table on BigQuery need this field.
        'startTime': time.time(),
        'status': [],
        'message': []
    })
    try:
      report_basename = os.path.basename(report_file_path)
      if report_basename.endswith('.tar.xz'):
        # Report name format: {gmtime}_{serial}.tar.xz
        report_time = time.mktime(
            time.strptime(report_basename.partition('_')[0], '%Y%m%dT%H%M%SZ'))
      else:
        # Report name format: {stage}{opt_name}-{serial}-{gmtime}.rpt.xz
        report_time = time.mktime(
            time.strptime(
                report_basename.rpartition('-')[-1], '%Y%m%dT%H%M%SZ.rpt.xz'))
      report_event['time'] = report_time
      process_event['time'] = report_time
      report_event, process_event = self.DecompressAndParse(
          report_path, report_event, process_event)
    except Exception as e:
      SetProcessEventStatus(ERROR_CODE.ReportUnknownError, process_event, e)
      self.exception('Exception encountered when processing factory report')
    finally:
      file_utils.TryUnlink(report_path)
    return report_event, process_event

  def DecompressAndParse(self, report_path, report_event, process_event):
    """Decompresses the factory report and parse it."""
    with file_utils.TempDirectory(dir=self._tmp_dir) as report_dir:
      if not tarfile.is_tarfile(report_path):
        SetProcessEventStatus(ERROR_CODE.ReportInvalidFormat, process_event)
        process_event['endTime'] = time.time()
        return None, process_event
      report_tar = tarfile.open(report_path, 'r|xz')
      report_tar.extractall(report_dir)
      process_event['decompressEndTime'] = time.time()

      eventlog_path = os.path.join(report_dir, 'events')
      if os.path.exists(eventlog_path):
        eventlog_report_event, process_event = self.ParseEventlogEvents(
            eventlog_path, copy.deepcopy(report_event), process_event)
        if eventlog_report_event:
          report_event = eventlog_report_event
      else:
        SetProcessEventStatus(ERROR_CODE.EventlogFileNotFound, process_event)

      testlog_path = os.path.join(report_dir, 'var', 'factory', 'testlog',
                                  'events.json')
      if os.path.exists(testlog_path):
        testlog_report_event, process_event = self.ParseTestlogEvents(
            testlog_path, copy.deepcopy(report_event), process_event)
        if testlog_report_event:
          report_event = testlog_report_event
      else:
        SetProcessEventStatus(ERROR_CODE.TestlogFileNotFound, process_event)
      process_event['endTime'] = time.time()
      return report_event, process_event

  def ParseEventlogEvents(self, path, report_event, process_event):
    """Parses Eventlog file."""

    def SetSerialNumber(sn_key, sn_value):
      if not isinstance(sn_value, str):
        SetProcessEventStatus(ERROR_CODE.EventlogWrongType, process_event)
        sn_value = str(sn_value)
      if sn_value != 'null':
        report_event['serialNumbers'][sn_key] = sn_value

    END_TOKEN = '---\n'

    try:
      data_lines = ''
      for line in open(path, 'r'):
        if line != END_TOKEN:
          # If the log file is not sync to disk correctly, it may have null
          # characters. The data after the last null character should be the
          # first line of a new event.
          if '\0' in line:
            splited_line = line.split('\0')
            data_lines += splited_line[0]
            SetProcessEventStatus(ERROR_CODE.EventlogNullCharactersExist,
                                  process_event, data_lines)

            data_lines = splited_line[-1]
          else:
            data_lines += line
        else:
          raw_event = data_lines
          data_lines = ''
          event = None
          try:
            event = yaml.load(raw_event, yaml_loader)

            if not isinstance(event, dict):
              SetProcessEventStatus(ERROR_CODE.EventlogBrokenEvent,
                                    process_event, raw_event)
              continue

            def GetField(field, dct, key, is_string=True):
              if key in dct:
                if not is_string or isinstance(dct[key], str):
                  if dct[key] != 'null':
                    report_event[field] = dct[key]
                else:
                  SetProcessEventStatus(ERROR_CODE.EventlogWrongType,
                                        process_event)
                  report_event[field] = str(dct[key])

            serial_numbers = event.get('serial_numbers', {})
            if not isinstance(serial_numbers, dict):
              SetProcessEventStatus(ERROR_CODE.EventlogWrongType, process_event)
            else:
              for sn_key, sn_value in serial_numbers.items():
                SetSerialNumber(sn_key, sn_value)

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
                result = PATTERN_WP_STATUS.findall(
                    report_event['biosWpDetails'])
                if len(result) == 1:
                  report_event['biosWpStatus'] = result[0]
                result = PATTERN_WP.findall(report_event['biosWpDetails'])
                if len(result) == 1:
                  report_event['biosWp'] = result[0]
              GetField('modemStatus', event, 'modem_status')
              GetField('platformName', event, 'platform_name')
            elif event_name == 'scan':
              for sn_key in ['serial_number', 'mlb_serial_number']:
                if event.get('key', None) == sn_key and 'value' in event:
                  SetSerialNumber(sn_key, event['value'])
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
          except yaml.YAMLError as e:
            SetProcessEventStatus(ERROR_CODE.EventlogBrokenEvent, process_event,
                                  e)
          except Exception as e:
            SetProcessEventStatus(ERROR_CODE.EventlogUnknownError,
                                  process_event, e)

      # There should not have data after the last END_TOKEN.
      if data_lines:
        SetProcessEventStatus(ERROR_CODE.EventlogBrokenEvent, process_event,
                              data_lines)

      # Some reports doesn't have serial_numbers field. However, serial numbers
      # are very important in a report_event, so we try to parse them again.
      content = None
      for sn_key, pattern in [('serial_number', PATTERN_SERIAL_NUMBER),
                              ('mlb_serial_number', PATTERN_MLB_SERIAL_NUMBER)]:
        if sn_key not in report_event['serialNumbers']:
          if not content:
            content = file_utils.ReadFile(path)
          line_list = pattern.findall(content)
          sn_list = []
          for line in line_list:
            try:
              sn = yaml.load(line, yaml_loader)[sn_key]
              if sn != 'null':
                sn_list.append(sn)
            except Exception:
              pass
          if len(sn_list) > 0:
            # We use the most frequent value.
            sn_value = max(set(sn_list), key=sn_list.count)
            SetSerialNumber(sn_key, sn_value)

      return report_event, process_event
    except Exception as e:
      SetProcessEventStatus(ERROR_CODE.EventlogUnknownError, process_event, e)
      self.exception('Failed to parse eventlog events')
      return None, process_event

  def ParseTestlogEvents(self, path, report_event, process_event):
    """Parses Testlog file."""
    try:
      with open(path, 'r') as f:
        for line in f:
          # If the log file is not sync to disk correctly, it may have null
          # characters.
          if '\0' in line:
            SetProcessEventStatus(ERROR_CODE.TestlogNullCharactersExist,
                                  process_event)
          # If the log file is not sync to disk correctly, a line may have a
          # broken event and a new event. We can use the EVENT_START to find
          # the new event.
          EVENT_START = '{"payload":'
          new_event_index = line.rfind(EVENT_START)
          if new_event_index > 0:
            SetProcessEventStatus(ERROR_CODE.TestlogBrokenEvent, process_event,
                                  line)
            line = line[new_event_index:]

          try:
            event = datatypes.Event.Deserialize(line)

            if not isinstance(event, dict):
              SetProcessEventStatus(ERROR_CODE.TestlogBrokenEvent,
                                    process_event, line)
              continue

            if 'serialNumbers' in event:
              for sn_key, sn_value in event['serialNumbers'].items():
                if not isinstance(sn_value, str):
                  SetProcessEventStatus(ERROR_CODE.TestlogWrongType,
                                        process_event)
                  sn_value = str(sn_value)
                report_event['serialNumbers'][sn_key] = sn_value
            if 'time' in event:
              report_event['dutTime'] = event['time']

            for field in REPORT_EVENT_FIELD:
              if field in event:
                report_event[field] = event[field]

            if event.get('testType', None) == 'hwid':
              data = event.get('parameters', {}).get('phase', {}).get(
                  'data', {})
              if len(data) == 1 and 'textValue' in data[0]:
                report_event['phase'] = data[0]['textValue']
          except json.JSONDecodeError as e:
            SetProcessEventStatus(ERROR_CODE.TestlogBrokenEvent, process_event,
                                  e)
          except Exception as e:
            SetProcessEventStatus(ERROR_CODE.TestlogUnknownError, process_event,
                                  e)
      return report_event, process_event
    except Exception as e:
      SetProcessEventStatus(ERROR_CODE.TestlogUnknownError, process_event, e)
      self.exception('Failed to parse testlog events')
      return None, process_event


ERROR_CODE = type_utils.Obj(
    EventNoObjectId=100,
    ArchiveInvalidFormat=200,
    ArchiveUnknownError=299,
    ReportInvalidFormat=300,
    ReportUnknownError=399,
    EventlogFileNotFound=400,
    EventlogNullCharactersExist=401,
    EventlogWrongType=402,
    EventlogBrokenEvent=403,
    EventlogUnknownError=499,
    TestlogFileNotFound=500,
    TestlogNullCharactersExist=501,
    TestlogWrongType=502,
    TestlogBrokenEvent=503,
    TestlogUnknownError=599,
)


def SetProcessEventStatus(code, process_event, message=None):
  """Sets status and message to process_event.

  See ERROR_CODE and http://b/184819627 (Googlers only) for details.
  Error Code type:
    1xx Event Error:
    2xx Archive Error:
    3xx Report Error:
    4xx Eventlog Error:
    5xx Testlog Error:
    6xx Other Error:
  """
  if code not in process_event['status']:
    process_event['status'].append(code)
  if isinstance(message, str):
    process_event['message'].append(message)
  elif isinstance(message, bytes):
    process_event['message'].append(message.decode('utf-8'))
  elif message:
    process_event['message'].append(str(message))
    if isinstance(message, Exception):
      process_event['message'].append(traceback.format_exc())


if __name__ == '__main__':
  plugin_base.main()
