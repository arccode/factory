#!/usr/bin/python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Selects whether this device should be sampled for certain tests.

Uses a hash of the WLAN MAC address (wlan0 or mlan0), and writes a
"True" or "False" value to a particular element in the device data
dictionary.
"""

import hashlib
import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import event_log
from cros.factory.test import shopfloor
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import net_utils


class SelectForSamplingTest(unittest.TestCase):
  ARGS = [
      Arg('rate', float,
          'Sampling rate (0 to never select any devices, 1 to select all, '
          '0.2 to select 20% of devices, etc.)'),
      Arg('device_data_key', str,
          'Key in the device data dictionary',
          default='selected_for_sampling'),
  ]

  def runTest(self):
    self.assertGreaterEqual(self.args.rate, 0.0)
    self.assertLessEqual(self.args.rate, 1.0)

    mac_address = net_utils.GetWLANMACAddress()
    digest = hashlib.md5(mac_address).hexdigest()
    value = int(digest, 16)

    max_value = 16 ** len(digest)
    fraction = value * 1.0 / max_value

    selected = fraction < self.args.rate

    logging.info('MAC address hash (as a fraction of 1): %.5f', fraction)
    logging.info('Sampling rate: %.5f', self.args.rate)
    logging.info('Selected: %r', selected)

    event_log.Log('select_for_sampling',
                  device_data_key=self.args.device_data_key,
                  fraction=fraction, rate=self.args.rate, selected=selected)

    shopfloor.UpdateDeviceData({self.args.device_data_key: selected})
