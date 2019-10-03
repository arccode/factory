# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to calibrate speaker.

Description
-----------
The test calibrates the speaker by following steps::

  1. Play silent music to load DSM module.
  2. Enter calibration mode.
  3. Wait for 3 seconds to get stable Rdc.
  4. Read Rdc values from two speakers.
  5. Store result to VPD.
  6. Quit calibration mode.

After this test, it is recommended to run ``RebootStep`` to load calibration
data into cras, and run ``audio_loop`` test to verify the calibration result.

Test Procedure
--------------
This is an automated test without user interaction.

Dependency
----------
- ``alsactl-tlv``
- Device API ``cros.factory.device.audio``.
- Device API ``cros.factory.device.vpd``.

Examples
--------
To calibrate the speaker device hw:1,0, add this into test list::

  {
    "pytest_name": "dsm_calibration",
    "args": {
      "output_dev": ["1", "0"],
    }
  }

See audio_loop.py for more details about how to set ``output_dev``.
"""

import logging
import re
import time
import unittest

from cros.factory.device import device_utils
from cros.factory.test.utils import audio_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


_VPD_KEY = 'dsm_calib'


class DSMCalibrationTest(unittest.TestCase):
  ARGS = [
      Arg('output_dev', list,
          'Output ALSA device. [card_name, sub_device].'
          'For example: ["audio_card", "0"].', ['0', '0']),
      Arg('num_output_channels', int,
          'Number of output channels.', default=2),
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._out_card = self.args.output_dev[0]
    self._out_device = self.args.output_dev[1]
    self._sox_process = None

  def runTest(self):
    device = 'hw:%s,%s' % tuple(self.args.output_dev)
    sox_args = audio_utils.GetPlaySineArgs(2, device,
                                           freq=100, duration_secs=1000)
    self._sox_process = process_utils.Spawn(sox_args)
    time.sleep(0.5)

    # Enter calibration mode and wait 3 secs.
    self._dut.CheckCall([
        'alsactl-tlv', '-D', self._out_card, '-C', 'numid=28', '-V',
        '0x0000000,0x00000010,0x03000001,0x00000004'])
    time.sleep(3)

    calib_data = self._dut.CheckOutput([
        'alsactl-tlv', '-D', self._out_card, '-C',
        "name='spk_pb_in dsm 0 lp18 params'"])
    logging.info(calib_data)

    # Output should be something like:
    #
    # numid=0,iface=MIXER,name='spk_pb_in dsm 0 lp18 params'
    # TLV READ - 24 bytes
    # 0000: 03000012 00000008 08fb41b2 08b6a74b 00000000 00000000
    #
    # calibration offset is the 3rd and 4th hex number.
    match = re.search('[a-f0-9]+:' + ' ([a-f0-9]+)' * 6, calib_data)
    if not match:
      raise RuntimeError(
          'Calibration offset not found in output: %s' % calib_data)

    vpd_value = "0000000 00000010 01000006 {} 02000006 {}".format(
        match.group(3), match.group(4))
    self._dut.vpd.ro.Update({_VPD_KEY: vpd_value})

    # Quit calibration mode.
    self._dut.CheckCall([
        'alsactl-tlv', '-D', self._out_card, '-C', 'numid=28', '-V',
        '0x0000000,0x00000010,0x03000001,0x00000001'])

  def tearDown(self):
    if self._sox_process:
      self._sox_process.terminate()
