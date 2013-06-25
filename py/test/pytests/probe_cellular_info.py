# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Probes information from 'modem status'.

Requested data are probed, written to the event log, and saved to device data.
"""

import logging
import re
import unittest

from cros.factory.event_log import Log
from cros.factory.test.args import Arg
from cros.factory.test.shopfloor import UpdateDeviceData
from cros.factory.utils.process_utils import CheckOutput


class ProbeCellularInfoTest(unittest.TestCase):
  ARGS = [
      Arg('probe_imei', bool, 'Whether to probe IMEI', True),
      Arg('probe_meid', bool, 'Whether to probe MEID', True),
      ]

  def runTest(self):
    output = CheckOutput(['modem', 'status'], log=True)
    logging.info('modem status output:\n%s', output)

    data = {}

    for name, enabled in (('imei', self.args.probe_imei),
                          ('meid', self.args.probe_meid)):
      if not enabled:
        continue

      match = re.search('^\s*' + name + ': (.+)', output, re.M | re.I)
      data[name] = match.group(1) if match else None

    Log('cellular_info', modem_status_stdout=output, **data)

    missing = set(k for k, v in data.iteritems() if v is None)
    self.assertFalse(
        missing,
        "Missing elements in 'modem status' output: %s" % sorted(missing))

    logging.info('Probed data: %s', data)
    UpdateDeviceData(data)
