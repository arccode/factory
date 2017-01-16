# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Uses i2cdetect utility to probe for I2C devices on a specific bus.

This pytest will be deprecated and replaced by "probe" pytest later.
"""

import json
import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.test.utils import deploy_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import sys_utils


class I2CProbeTest(unittest.TestCase):

  ARGS = [
      Arg('bus', int, 'I2C bus to probe.', optional=True),
      Arg('addr', (int, list), 'I2C address(es) to probe. Can be a list '
          'containing multiple I2C addresses, in which case the test passes '
          'when *any* of those exists.'),
      Arg('r_flag', bool, 'Use SMBus "read byte" commands for probing.',
          default=False),
      Arg('auto_detect_device', (str, list),
          'Given devices name from /proc/bus/input/devices to auto '
          'detect i2c bus',
          optional=True)
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self.factory_tools = deploy_utils.FactoryPythonArchive(self._dut)

  def runTest(self):
    self.assertTrue(self.args.bus is not None or self.args.auto_detect_device,
                    'You should assign bus or enable auto detect')
    bus, addr_list, r_flag = self.args.bus, self.args.addr, self.args.r_flag
    if self.args.auto_detect_device:
      if type(self.args.auto_detect_device) != list:
        self.args.auto_detect_device = [self.args.auto_detect_device]
      bus = sys_utils.GetI2CBus(self.args.auto_detect_device)
      self.assertTrue(type(bus) is int, 'Auto detect bus error')
      factory.console.info('Auto detect bus: %d', bus)

    if type(addr_list) != list:
      addr_list = [addr_list]

    probe_config = {'i2c_category':{}}
    for addr in addr_list:
      probe_config['i2c_category']['device_%s' % addr] = {
          'eval': {
              'i2c': {
                  'bus_number': str(bus),
                  'addr': '0x%x' % addr,
                  'use_r_flag': r_flag}},
          'expect': {}}
    logging.info('probe config: %s', probe_config)

    with file_utils.UnopenedTemporaryFile(suffix='.json') as config_file:
      with open(config_file, 'w') as f:
        json.dump(probe_config, f)

      # Execute Probe.
      cmd = ['probe', '-v', 'probe', config_file]
      factory.console.info('Call the command: %s', ' '.join(cmd))
      probed_results = json.loads(self.factory_tools.CheckOutput(cmd))
      count = sum(len(comps) for comps in probed_results['i2c_category'].values())
      self.assertGreaterEqual(count, 1,
                              'No I2C device on bus %d addr %s' %
                              (bus, ', '.join(['0x%x' % addr
                                               for addr in addr_list])))
