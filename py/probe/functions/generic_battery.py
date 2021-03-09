# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re

from cros.factory.probe.lib import probe_function
from cros.factory.utils import process_utils


ECTOOL_BATTERY_INFO_RE = re.compile(
    r'Battery (\d+ )?info:\n'
    r'  OEM name:               (?P<manufacturer>.*)\n'
    r'  Model number:           (?P<model_name>.*)\n'
    r'  Chemistry   :           (?P<technology>.*)\n'
    r'  Serial number:          \w+\n'
    r'  Design capacity:        (?P<charge_full_design>\d+) mAh\n')


class GenericBatteryFunction(probe_function.ProbeFunction):
  """Use `ectool battery` to probe battery information."""

  def Probe(self):
    try:
      output = process_utils.CheckOutput(['ectool', 'battery'])
    except process_utils.CalledProcessError:
      return None

    match = re.match(ECTOOL_BATTERY_INFO_RE, output)
    if match:
      return {
          'manufacturer': match.group('manufacturer'),
          'model_name': match.group('model_name'),
          'technology': match.group('technology'),
          'charge_full_design': int(match.group('charge_full_design')) * 1000
      }

    return None
