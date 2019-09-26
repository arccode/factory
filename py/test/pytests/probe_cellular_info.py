# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Probes information from 'modem status'.

Requested data are probed, written to the event log, and saved to device data.
"""

import logging
import re
import unittest

from six import iteritems

import factory_common  # pylint: disable=unused-import
from cros.factory.test import device_data
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


class ProbeCellularInfoTest(unittest.TestCase):
  ARGS = [
      Arg('probe_imei', bool, 'Whether to probe IMEI', True),
      Arg('probe_meid', bool, 'Whether to probe MEID', True),
      Arg('probe_lte_imei', bool, 'Whether to probe IMEI on LTE modem', False),
      Arg('probe_lte_iccid', bool, 'Whether to probe ICCID on LTE SIM card',
          False),
  ]

  def runTest(self):
    output = process_utils.CheckOutput(['modem', 'status'], log=True)
    logging.info('modem status output:\n%s', output)

    data = {}

    for name, field, enabled in (
        ('imei', 'imei', self.args.probe_imei),
        ('meid', 'meid', self.args.probe_meid),
        ('lte_imei', 'Imei', self.args.probe_lte_imei),
        ('lte_iccid', 'SimIdentifier', self.args.probe_lte_iccid)):
      if not enabled:
        continue

      match = re.search(r'^\s*' + field + ': (.+)', output, re.M | re.I)
      data[name] = match.group(1) if match else None

    event_log.Log('cellular_info', modem_status_stdout=output, **data)
    testlog.LogParam('modem_status_stdout', output)
    for k, v in iteritems(data):
      testlog.LogParam(k, v)

    missing = set(k for k, v in iteritems(data) if v is None)
    self.assertFalse(
        missing,
        "Missing elements in 'modem status' output: %s" % sorted(missing))

    logging.info('Probed data: %s', data)
    device_data.UpdateDeviceData({
        device_data.JoinKeys(device_data.KEY_COMPONENT, 'cellular', name): value
        for name, value in iteritems(data)})
