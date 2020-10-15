# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Allows testing and verification of GPS chips on Android DUTs.

GPS devices have a standard text-based output format called NMEA sentences.
This test reads those NMEA sentences for certain values, and checks that they
are within configurable ranges.

Here's an example of input arguments::

  ARGS={
      'station_name': 'gps_fatp',
      'fixture_id': session.GetDeviceID(),
      'timeout': 30,
      'init_timeout': 30,
      'warmup_count': 1,
      'gps_config_file': 'gpsconfig_jobs.xml',
      'gps_config_job': 'Factory_Track_Test',
      'nmea_out_path': '/data/gps/nmea_out',
      'nmea_prefix': '$PREFIX,1,',
      'nmea_fields': {'signal_strength': 4,
                      'carrier_to_noise': 7,
                      'ref_clock_offset': 12},
      'limits': [('signal_strength', 'count', '>', 25),
                 ('signal_strength', 'mean', '>', -120),
                 ('ref_clock_offset', 'mean', '>', -3000),
                 ('ref_clock_offset', 'mean', '<', 3000)]})}
"""

import logging
import os
import re
import subprocess
import sys
import threading
import unittest

import numpy

from cros.factory import device
from cros.factory.device import device_utils
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test import session
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils
from cros.factory.utils import time_utils


START_GLGPS_TIMEOUT = 5
DEFAULT_INIT_TIMEOUT = 10
DEFAULT_TIMEOUT = 15
DEVICE_GPS_CONFIG_PATH = '/data/gps/gpsconfig_jobs.xml'
EVENT_LOG_NAME = 'gps'
GLGPS_BINARY = 'glgps'
SERIAL_NOT_AVAILABLE = 'NOT_AVAILABLE'

_LOGPARSER_PASS = 'PASSED'
_LOGPARSER_FAIL = 'FAILED'

STAT_FNS = {
    'count': len,
    'min': lambda l: float(numpy.min(l)),
    'max': lambda l: float(numpy.max(l)),
    'median': lambda l: float(numpy.median(l)),
    'mean': lambda l: float(numpy.mean(l)),
    'std': lambda l: float(numpy.std(l))}
CMP_FNS = {
    '<': lambda x, y: x < y,
    '<=': lambda x, y: x <= y,
    '>': lambda x, y: x > y,
    '>=': lambda x, y: x >= y}


class GPS(unittest.TestCase):
  ARGS = [
      Arg('station_name', str,
          'Name of the station.  We might want to run the GPS test at '
          'different points in the factory.  This can be used to identify '
          'them, and will be saved in event_logs.  e.g. "gps_smt"'),
      Arg('fixture_id', str,
          'Name of the fixture.  This will be saved in event_logs.'),
      Arg('init_timeout', (int, float),
          'How long to poll for good data before giving up.  '
          'Default %d seconds.' % DEFAULT_INIT_TIMEOUT,
          default=DEFAULT_INIT_TIMEOUT),
      Arg('timeout', (int, float),
          'How long to run the test.  Default %d seconds.' % DEFAULT_TIMEOUT,
          default=DEFAULT_TIMEOUT),
      Arg('warmup_count', int,
          'How many initial matching NMEA sentences to ignore before starting '
          'to record data.',
          default=0),
      Arg('gps_config_file', str,
          'Relative or absolute path to GPS configuration file to upload '
          'to device.  If relative, searches both in directory of this test '
          'file, and in directory of currently executing Python script.'),
      Arg('gps_config_job', str,
          'Name of the job within gps_config_file to run.  This will be passed '
          'as an argument to glgps to start the job during test execution.'),
      Arg('nmea_out_path', str,
          'Path to the nmea_out file on the device.  This should be a named '
          'pipe which is specified in gps_config_file in the <hal> element, '
          'like so: <hal NmeaOutName="/data/gps/nmea_out">'),
      Arg('nmea_prefix', str,
          'Prefix of NMEA sentences for which to filter.  Only these sentences '
          'will be parsed based on nmea_fields.'),
      Arg('nmea_fields', dict,
          'Dictionary of fields to pull from the NMEA sentence.  '
          'Key is a string representing the name of the field, and '
          'value is its comma-separated index.'),
      Arg('limits', list,
          'List of limits, in the format ("nmea_field", "fn", "cmp", value), '
          'where fn can be any of %s, and cmp can be any of %s.'
          % (list(STAT_FNS), list(CMP_FNS)),
          default=[])
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

    # Store the serial numbers for later use.
    self._mlb_serial_number = (self.dut.info.mlb_serial_number or
                               SERIAL_NOT_AVAILABLE)
    self._serial_number = (self.dut.info.serial_number or SERIAL_NOT_AVAILABLE)
    session.console.info('Got MLB serial number: %s', self._mlb_serial_number)
    session.console.info('Got serial number: %s', self._serial_number)

    # Create a list for test-level failures.
    self._failures = []


  def _PushConfigFile(self):
    # Push the jobs config so we can start the job <self.args.gps_config_job>.
    session.console.info('Pushing config file...')
    config_path = None

    if self.args.gps_config_file.startswith('/'):
      if os.path.isfile(self.args.gps_config_file):
        config_path = self.args.gps_config_file
    else:
      # May be in the directory of this file, or the executing Python script.
      possible_dirs = [os.path.dirname(os.path.abspath(__file__)),
                       os.path.dirname(os.path.abspath(sys.argv[0]))]
      for possible_dir in possible_dirs:
        try_config_path = os.path.join(possible_dir, self.args.gps_config_file)
        if os.path.isfile(try_config_path):
          config_path = try_config_path
          break
    if not config_path:
      self.fail('Config file %s could not be found' % self.args.gps_config_file)
    with open(config_path) as f:
      self.dut.WriteFile('/data/gps', f.read())

  def _ParseNMEAStream(self, file_stream):
    """Parse NMEA stream and return values.

    Returns:
      Dictionary, where keys are from self.args.nmea_fields, and values
      are lists of parsed values in NMEA sentences.
    """
    all_values = {key: [] for key in self.args.nmea_fields}

    start_time = time_utils.MonotonicTime()
    timeout = self.args.init_timeout  # Initial timeout to get valid data.
    warmup_count = self.args.warmup_count  # Initial sentences to ignore.
    init = False
    warmup_init = False
    nmea_line = None

    while True:
      time_left = timeout - (time_utils.MonotonicTime() - start_time)
      if time_left <= 0:
        break

      # Make sure we have a useful NMEA line to work with.
      nmea_line = file_stream.readline().rstrip()
      if not nmea_line.startswith(self.args.nmea_prefix):
        continue
      logging.debug('[%d] nmea_line: %s', time_left, nmea_line)

      # Split the comma-separated data.  Use the indices sorted in ascending
      # order to look at values deterministically from left-to-right.
      nmea_values = nmea_line.split(',')
      sorted_indices = sorted(self.args.nmea_fields.values())
      index_to_key = {v: k for k, v in self.args.nmea_fields.items()}
      values = [nmea_values[index] for index in sorted_indices]

      # Initialization.
      if not init:
        if all([value != '' for value in values]):
          # This is the first set of valid values we are getting.
          init = True
        else:
          session.console.info('[%d] Waiting for initialization...', time_left)
          continue

      # Warmup.
      if not warmup_init:
        if warmup_count == 0:
          # This is the first warmed up value we are getting.
          warmup_init = True
          start_time = time_utils.MonotonicTime()
          time_left = timeout = self.args.timeout
        else:
          session.console.info('[%d] Warming up...', time_left)
          warmup_count -= 1
          continue

      # Check and record each value.
      current_values = {}
      for index in sorted_indices:
        key = index_to_key[index]
        if nmea_values[index] == '':
          self._failures.append(
              'Empty value for %s encountered after initialization' % key)
          return all_values
        try:
          parsed_value = float(nmea_values[index])
        except ValueError:
          self._failures.append('Non-numeric value encountered for %s: %s'
                                % (key, nmea_values[index]))
          return all_values
        all_values[key].append(parsed_value)
        current_values[key] = parsed_value

      # Print parsed values.
      current_values_str = ' '.join(
          '%s=%.1f' % (key, value)
          for key, value in current_values.items())
      session.console.info('[%d] %s', time_left, current_values_str)

    logging.debug('Timeout has been reached (%d secs)', self.args.timeout)
    return all_values


  def _CheckLimits(self, all_values):
    """Check limits specified by self.args.limits.

    Returns:
      The tuple (field_stats, limit_results, limit_failures_str), where:
          field_stats: A dictionary mapping each NMEA field.  Values are
              dictionaries of STAT_FNS.keys() to its corresponding calculated
              value.
          limit_results: A dictionary mapping each limit (from self.args.limits)
              to a boolean representing its success/failure.
          limit_failures_str: A list of strings, where each string represents a
              human-readable representation of a limit failure.
    """
    # Are there values to calculate stats?
    if not all(all_values.values()):
      self._failures.append('Never initialized')
      field_stats = None
    else:
      field_stats = {key: {} for key in self.args.nmea_fields}
      for key, values in all_values.items():
        for fn_name, fn in STAT_FNS.items():
          field_stats[key][fn_name] = fn(values)
        field_stats_str = ' '.join(
            '%s=%.1f' % (k, v)
            for k, v in field_stats[key].items())
        session.console.info('%s: %s', key, field_stats_str)

    # Do limit testing.
    limit_results = {}
    limit_failures_str = []
    for nmea_field, stat_fn, cmp_fn_key, limit_value in self.args.limits:
      cmp_fn = CMP_FNS[cmp_fn_key]
      if not field_stats:
        test_value = None
        passed = False
      else:
        test_value = field_stats[nmea_field][stat_fn]
        passed = cmp_fn(test_value, limit_value)
      passed_str = 'PASS' if passed else 'FAIL'
      limit_str = ('%s.%s %s %.1f'
                   % (nmea_field, stat_fn, cmp_fn_key, limit_value))
      result_str = '%s %s' % (passed_str, limit_str)
      limit_results[limit_str] = {'test_value': test_value, 'passed': passed}
      session.console.info(result_str)
      if not passed:
        limit_failures_str.append(result_str)
    logging.debug('Results to be logged: %s', limit_results)
    return (field_stats, limit_results, limit_failures_str)


  def runTest(self):
    self._PushConfigFile()

    # Stop glgps if it's already running.
    self._KillGLGPS()

    # Stop gpsd if it's already running.
    session.console.info('Stopping gpsd...')
    self.dut.Call('stop gpsd')

    # Run glgps for <args.timeout> seconds with <self.args.gps_config_job>.
    session.console.info('Starting %s job...', self.args.gps_config_job)
    def StartGLGPS():
      self.dut.Call([GLGPS_BINARY,
                     DEVICE_GPS_CONFIG_PATH,
                     self.args.gps_config_job])
    glgps_thread = threading.Thread(target=StartGLGPS)
    glgps_thread.daemon = True
    glgps_thread.start()

    # Check that glgps is running and is writing to <self.args.nmea_out_path>.
    def CheckGLGPSRunning():
      try:
        self.dut.CheckCall('ps | grep %s' % GLGPS_BINARY)
        self.dut.CheckCall('[[ -n `timeout 1 cat %s` ]]'
                           % self.args.nmea_out_path)
        return True
      except device.CalledProcessError:
        return False
    if not sync_utils.PollForCondition(poll_method=CheckGLGPSRunning,
                                       timeout_secs=START_GLGPS_TIMEOUT,
                                       poll_interval_secs=0):
      self.fail('%s was not running' % GLGPS_BINARY)

    # Get the latest readings from the NMEA output file.
    session.console.info('Reading from NMEA output file...')
    # TODO(kitching): Move this into AdbTarget so we can use something like
    # self.dut.Popen() instead of calling adb directly.
    cat_process = subprocess.Popen(
        ['adb', 'shell', 'cat %s' % self.args.nmea_out_path],
        stdout=subprocess.PIPE)
    all_values = self._ParseNMEAStream(cat_process.stdout)
    field_stats, limit_results, limit_failures_str = (
        self._CheckLimits(all_values))

    # Log directly to event_log.
    # The 'results' value format is:
    #    {'signal_strength.min > -130.0': {'test_value': -120.0,
    #                                      'passed': True},
    #     ... }
    log_dict = {
        'station_name': self.args.station_name,
        'fixture_id': self.args.fixture_id,
        'mlb_serial_number': self._mlb_serial_number,
        'serial_number': self._serial_number,
        'passed': not self._failures and not limit_failures_str,
        'failures': self._failures,
        'stats': field_stats,
        'results': limit_results}
    event_log.Log(EVENT_LOG_NAME, **log_dict)
    testlog.LogParam('stats', field_stats)
    testlog.LogParam('results', limit_results)

    # Check for failures.
    if limit_failures_str:
      self.fail('\n'.join(limit_failures_str))


  def tearDown(self):
    # Kill glgps.
    self._KillGLGPS()

    # Restart normal gpsd operation.
    session.console.info('Restarting normal gpsd...')
    self.dut.Call('start gpsd')


  def _KillGLGPS(self):
    # Stop the glgps with Factory_Test_Track.
    try:
      ps_line = self.dut.CheckOutput('ps | grep %s' % GLGPS_BINARY)
    except device.CalledProcessError:
      # Process is not running.  Don't kill it!
      session.console.info('%s already stopped', GLGPS_BINARY)
      return
    glgps_pid = re.split(r' *', ps_line)[1]
    if not glgps_pid:
      # Process is not running.  Don't kill it!
      session.console.info('%s already stopped', GLGPS_BINARY)
    else:
      session.console.info('Killing %s pid %d...', GLGPS_BINARY, int(glgps_pid))
      self.dut.CheckOutput(['kill', glgps_pid])
      # TODO(kitching): Join the GLGPS thread before sending a kill signal?
