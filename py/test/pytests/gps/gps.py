# -*- mode: python; coding: utf-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import logging
import os
import re
# TODO(kitching): Make sure that we can safely delete polling.
#import select
import subprocess
import sys
import threading
import time
import unittest

import numpy

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test.event_log import Log
from cros.factory.test.args import Arg
from cros.factory.test.dut.base import CalledProcessError
from cros.factory.utils import time_utils


DEFAULT_INIT_TIMEOUT = 10
DEFAULT_TIMEOUT = 15
GLGPS_BINARY = 'glgps'
DEVICE_GPS_CONFIG_PATH = '/data/gps/gpsconfig_jobs.xml'

STAT_FNS = {
    'count': len,
    'min': numpy.min,
    'max': numpy.max,
    'median': numpy.median,
    'mean': numpy.mean,
    'std': numpy.std}
CMP_FNS = {
    '<': lambda x, y: x < y,
    '<=': lambda x, y: x <= y,
    '>': lambda x, y: x > y,
    '>=': lambda x, y: x >= y,
    }


class Gps(unittest.TestCase):
  ARGS = [
      Arg('event_log_name', str, 'Name of the event_log.  We might want to '
          're-run the conductive test at different points in the factory, so '
          'this can be used to separate them.  e.g. "gps_smt"',
          optional=False),
      Arg('init_timeout', int,
          'How long to poll for good data before giving up.  '
          'Default %d seconds.' % DEFAULT_INIT_TIMEOUT,
          optional=True, default=DEFAULT_INIT_TIMEOUT),
      Arg('timeout', int,
          'How long to run the test.  Default %d seconds.' % DEFAULT_TIMEOUT,
          optional=True, default=DEFAULT_TIMEOUT),
      Arg('gps_config_file', str,
          'Relative or absolute path to GPS configuration file to upload '
          'to device.  If relative, searches both in directory of this test '
          'file, and in directory of currently executing Python script.',
          optional=False),
      Arg('gps_config_job', str,
          'Name of the job within gps_config_file to run.  This will be passed '
          'as an argument to glgps to start the job during test execution.',
          optional=False),
      Arg('nmea_out_path', str,
          'Path to the nmea_out file on the device.  This should be a named '
          'pipe which is specified in gps_config_file in the <hal> element, '
          'like so: <hal NmeaOutName="/data/gps/nmea_out">',
          optional=False),
      Arg('nmea_prefix', str,
          'Prefix of NMEA sentences for which to filter.  Only these sentences '
          'will be parsed based on nmea_fields.',
          optional=False),
      Arg('nmea_fields', dict,
          'Dictionary of fields to pull from the NMEA sentence.  '
          'Key is a string representing the name of the field, and '
          'value is its comma-separated index.',
          optional=False),
      Arg('limits', list,
          'List of limits, in the format ("nmea_field", "fn", "cmp", value), '
          'where fn can be any of %s, and cmp can be any of %s.'
          % (STAT_FNS.keys(), CMP_FNS.keys()),
          optional=True, default=[])
  ]

  def setUp(self):
    # Push the jobs config so we can start the job self.args.gps_config_job.
    factory.console.info('Pushing config file...')
    # May be in the directory of this file, or the executing Python script.
    possible_dirs = [os.path.dirname(self.args.gps_config_file),
                     os.path.dirname(os.path.abspath(__file__)),
                     os.path.dirname(os.path.abspath(sys.argv[0]))]
    config_path = None
    for possible_dir in possible_dirs:
      config_path = os.path.join(possible_dir, self.args.gps_config_file)
      if os.path.isfile(config_path):
        break
    if not config_path:
      self.fail('Config file %s could not be found')
    self.dut.Push(config_path, '/data/gps')

    # Stop glgps if it's already running.
    factory.console.info('Stopping gpsd...')
    self.dut.Shell('stop gpsd')

    # Run glgps for 60 seconds with job self.args.gps_config_job.
    factory.console.info('Starting %s job...', self.args.gps_config_job)
    def start_gps_job():
      self.dut.Shell([GLGPS_BINARY,
                      DEVICE_GPS_CONFIG_PATH,
                      self.args.gps_config_job])
    glgps_thread = threading.Thread(target=start_gps_job)
    glgps_thread.daemon = True
    glgps_thread.start()

    # TODO(kitching): Figure out a way to verify GLGPS is running instead of
    # waiting for a predetermined period of time.
    # Give the thread time to send ADB command.
    time.sleep(1)

  def runTest(self):
    # Check that glgps is running.
    try:
      self.dut.CheckCall('ps | grep %s' % GLGPS_BINARY)
    except CalledProcessError:
      self.fail('%s was not running' % GLGPS_BINARY)

    # Get the latest readings from the NMEA output file.
    factory.console.info('Reading from NMEA output file...')
    p = subprocess.Popen(['adb', 'shell', 'cat %s' % self.args.nmea_out_path],
                         stdout=subprocess.PIPE)
    # TODO(kitching): Make sure that we can safely delete polling.
    #poll_obj = select.poll()
    #poll_obj.register(p.stdout, select.POLLIN)

    nmea_values = self.args.nmea_fields
    all_values = {key: [] for key in nmea_values}

    start_time = time_utils.MonotonicTime()
    timeout = self.args.init_timeout  # Initial timeout to get good data.
    init = False
    while time_utils.MonotonicTime() - start_time < timeout:
      time_left = timeout - (time_utils.MonotonicTime() - start_time)

      # Make sure we have a useful NMEA line to work with.
      # TODO(kitching): Make sure that we can safely delete polling.
      #poll_result = poll_obj.poll(0)
      #if not poll_result:
      #  continue
      nmea = p.stdout.readline().rstrip()
      if self.args.nmea_prefix not in nmea:
        continue
      logging.debug('[%d] nmea: %s', time_left, nmea)

      # Split the comma-separated data and grab the necessary values.
      pglor = nmea.split(',')
      current_values = {}
      continue_outer = False
      for key, index in nmea_values.iteritems():
        if not init:
          if pglor[index] != '':
            # This is the first useful value we are getting.
            init = True
            start_time = time_utils.MonotonicTime()
            time_left = timeout = self.args.timeout
          else:
            factory.console.info('[%d] Waiting for initialization...',
                                 time_left)
            continue_outer = True
            break
        if pglor[index] == '':
          self.fail('Empty value encountered after initialization')

        parsed_value = float(pglor[index])
        all_values[key].append(parsed_value)
        current_values[key] = parsed_value

      # Continue to outer loop if necessary.
      if continue_outer:
        continue

      current_values_str = ' '.join(
          '%s=%.1f' % (key, value)
          for key, value in current_values.iteritems())
      factory.console.info('[%d] %s', time_left, current_values_str)

    if not init:
      self.fail('Never initialized')

    logging.debug('Timeout has been reached (%d secs)', self.args.timeout)

    field_stats = {key: {} for key in nmea_values.keys()}
    for key, values in all_values.iteritems():
      for fn_name, fn in STAT_FNS.iteritems():
        field_stats[key][fn_name] = fn(values)
      field_stats_str = ' '.join(
          '%s=%.1f' % (k, v)
          for k, v in field_stats[key].iteritems())
      factory.console.info('%s: %s', key, field_stats_str)

    # Do limit testing.
    limit_results = {}
    limit_failures_str = []
    for nmea_field, stat_fn, cmp_fn_key, limit_value in self.args.limits:
      cmp_fn = CMP_FNS[cmp_fn_key]
      test_value = field_stats[nmea_field][stat_fn]
      passed = cmp_fn(test_value, limit_value)
      passed_str = 'PASS' if passed else 'FAIL'
      limit_str = ('%s.%s %s %.1f'
                   % (nmea_field, stat_fn, cmp_fn_key, limit_value))
      result_str = '%s %s' % (passed_str, limit_str)
      limit_results[limit_str] = {'test_value': test_value, 'result': passed}
      factory.console.info(result_str)
      if not passed:
        limit_failures_str.append(result_str)
    logging.debug('Results to be logged: %s', limit_results)

    # TODO(kitching): Save logs from this run.

    # Check for failures.
    if limit_failures_str:
      self.fail('\n'.join(limit_failures_str))


  def tearDown(self):
    # Stop the glgps with Factory_Test_Track and restart normal gpsd operation.
    ps_line = self.dut.CheckOutput('ps | grep %s' % GLGPS_BINARY)
    glgps_pid = re.split(r' *', ps_line)[1]
    if not glgps_pid:
      factory.console.info('%s already stopped', GLGPS_BINARY)
    else:
      factory.console.info('Killing %s pid %d...', GLGPS_BINARY, int(glgps_pid))
      self.dut.CheckOutput(['kill', glgps_pid])
      # TODO(kitching): Join the GLGPS thread before sending a kill signal?

    factory.console.info('Restarting normal gpsd...')
    self.dut.Shell('start gpsd')
