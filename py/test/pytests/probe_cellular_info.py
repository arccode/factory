# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Probes information from modem status.

Description
-----------
This test can probe requested data, including
``NAME={'imei', 'meid', 'lte_imei', 'lte_iccid'}`` from modem status. When the
argument ``probe_{NAME}`` is set ``True``, the data ``NAME`` will be logged and
saved to device data.

The ``fields`` argument is a dictionary containing multiple
(``NAME``, ``FIELD``) pairs. It will override the following default fields:

============= ================== ===============
NAME          FIELD              probe_{NAME}
============= ================== ===============
``imei``      ``imei``           True
``meid``      ``meid``           True
``lte_imei``  ``Imei``           False
``lte_iccid`` ``SimIdentifier``  False
============= ================== ===============

Test Procedure
--------------
This is an automated test without user interaction.

The test will probe specific data from the command ``modem status``, then log to
``cros.factory.testlog`` and save to ``cros.factory.test.device_data``.

Dependency
----------
Some modems may have different identities for each fields. For example, Fibocom
LTE module will identify imei as ``EquipmentIdentifier``, so you will need
to specify the ``fields`` argument.

Examples
--------
The following argument will probe imei from field ``EquipmentIdentifier``::

  {
    "pytest_name": "probe_cellular_info",
    "args": {
      "probe_imei": True,
      "probe_meid": False,
      "fields": {
        "imei": "EquipmentIdentifier"
      }
    }
  }


Example output::

  # "modem status" output
  output = \"\"\"Modem /org/freedesktop/ModemManager1/Modem/7:
    GetStatus:
    Properties:
      EquipmentIdentifier: 862227050001326
      ...
    3GPP:
    CDMA:
  \"\"\"

  # device_data
  data = {'imei': '862227050001326'}

"""

import logging
import unittest

from cros.factory.test import device_data
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import string_utils


class ProbeCellularInfoTest(unittest.TestCase):
  ARGS = [
      Arg('probe_imei', bool, 'Whether to probe IMEI', True),
      Arg('probe_meid', bool, 'Whether to probe MEID', True),
      Arg('probe_lte_imei', bool, 'Whether to probe IMEI on LTE modem', False),
      Arg('probe_lte_iccid', bool, 'Whether to probe ICCID on LTE SIM card',
          False),
      Arg('fields', dict,
          ('Specify the fields to probe. A {NAME: FIELD} pair will record the'
           'value of FIELD to KEY_COMPONENT.cellular.NAME'), {})
  ]

  def runTest(self):

    def _FindField(output_dict, key):
      """Find field value in nested dictionary."""

      if not isinstance(output_dict, dict):
        return None
      if key in output_dict and len(output_dict[key]) > 0:
        return output_dict[key]

      for child in output_dict.values():
        value = _FindField(child, key)
        if value is not None:
          return value

      return None

    output = process_utils.CheckOutput(['modem', 'status'], log=True)
    logging.info('modem status output:\n%s', output)

    output_dict = string_utils.ParseDict(output.strip().splitlines(),
                                         recursive=True)
    data = {}

    for name, field, enabled in (
        ('imei', 'imei', self.args.probe_imei),
        ('meid', 'meid', self.args.probe_meid),
        ('lte_imei', 'Imei', self.args.probe_lte_imei),
        ('lte_iccid', 'SimIdentifier', self.args.probe_lte_iccid)):
      if not enabled:
        continue

      field = self.args.fields[name] if name in self.args.fields else field
      data[name] = _FindField(output_dict, field)

    event_log.Log('cellular_info', modem_status_stdout=output, **data)
    testlog.LogParam('modem_status_stdout', output)
    for k, v in data.items():
      testlog.LogParam(k, v)

    missing = set(k for k, v in data.items() if v is None)
    self.assertFalse(
        missing,
        "Missing elements in 'modem status' output: %s" % sorted(missing))

    logging.info('Probed data: %s', data)
    device_data.UpdateDeviceData({
        device_data.JoinKeys(device_data.KEY_COMPONENT, 'cellular', name): value
        for name, value in data.items()
    })
