#!/usr/bin/env python2
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Profiling tool for N1914A

Because N1914A supports various of sensors, this performance measuring
tool is aimed to better understand the accuracy and speed of different
configuration/ sensor combination.
"""

import argparse
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.test.rf.n1914a import N1914A


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
      description=('This tool will use REAL format to measure the reading/sec '
                   'for different sampling modes.'))
  parser.add_argument('--port', action='store', type=int, default=1,
                      help='port where sensor located.')
  parser.add_argument('--iteration', action='store', type=int, default=10,
                      help='iteration of readings per mode.')
  parser.add_argument('--host', action='store', required=True,
                      help='IP of the N1914A.')
  args = parser.parse_args()
  n1914a = N1914A(args.host)

  modes = [('Normal', n1914a.ToNormalMode),
           ('Double', n1914a.ToDoubleMode),
           ('Fast', n1914a.ToFastMode)]

  # Preparation
  print 'Preparing device...'
  n1914a.SetRealFormat()
  # Disable average filter
  n1914a.SetAverageFilter(port=args.port, avg_length=None)
  n1914a.SetRange(port=args.port, range_setting=1)
  n1914a.SetTriggerToFreeRun(port=args.port)
  n1914a.SetContinuousTrigger(port=args.port)

  time_elapsed = {}
  last_measurment = {}
  for mode_name, mode_func in modes:
    mode_func(port=args.port)
    print 'Profiling mode %s ...' % mode_name
    start_time = time.time()
    for iteration in xrange(args.iteration):
      power = n1914a.MeasureOnceInBinary(port=args.port)
    time_elapsed[mode_name] = time.time() - start_time
    last_measurment[mode_name] = power

  # Printing the result.
  for mode_name, _ in modes:
    print 'Mode[%8s]:  %8.2f reading/sec, last measurment=%10.7f dBm.' % (
        mode_name, args.iteration / float(time_elapsed[mode_name]),
        last_measurment[mode_name])
