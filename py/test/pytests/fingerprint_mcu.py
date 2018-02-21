# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for the Fingerprint sensor.

Description
-----------
Tests that the fingerprint sensor is connected properly and has no defect
by executing commands through the fingerprint micro-controller.

Test Procedure
--------------
This is an automated test without user interaction,
it might use a rubber finger pressed against the sensor by a proper fixture.

Dependency
----------
The pytest supposes that the system as a fingerprint MCU exposed through the
kernel cros_ec driver as ``/dev/cros_fp``.

When available, it uses the vendor 'libfputils' shared library and its Python
helper to compute the image quality signal-to-noise ratio.

Examples
--------
Minimum runnable example to check if the fingerprint sensor is connected
properly and fits the default quality settings::

  {
    "pytest_name": "fpmcu"
  }

To check if the sensor has at most 100 dead pixels and its HWID is 0x140b,
add this in test list::

  {
    "pytest_name": "fpmcu",
    "args": {
      "dead_pixel_max": 10,
      "sensor_hwid": 5132
    }
  }
"""

import logging
import re
import sys
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.testlog import testlog
from cros.factory.utils import type_utils
from cros.factory.utils.arg_utils import Arg

# use the fingerprint image processing library if available
sys.path.extend(['/usr/local/opt/fpc', '/opt/fpc'])
try:
  import fputils
  libfputils = fputils.FpUtils()
except ImportError:
  libfputils = None

class FingerprintTest(unittest.TestCase):
  """Tests the fingerprint sensor."""
  ARGS = [
      Arg('sensor_hwid', int,
          'The finger sensor Hardware ID exported in the model field.',
          default=None),
      Arg('max_dead_pixels', int,
          'The maximum number of dead pixels on the fingerprint sensor.',
          default=6),
      Arg('min_snr', float,
          'The minimum signal-to-noise ratio for the image quality.',
          default=0.0),
      Arg('rubber_finger_present', bool,
          'A Rubber finger is pressed against the sensor for quality testing.',
          default=False),
  ]

  # Select the Fingerprint MCU cros_ec device
  CROS_FP_ARG = "--name=cros_fp"

  # Regular expression for parsing ectool output.
  RO_VERSION_RE = re.compile(r'^RO version:\s*(\S+)\s*$', re.MULTILINE)
  RW_VERSION_RE = re.compile(r'^RW version:\s*(\S+)\s*$', re.MULTILINE)
  FPINFO_MODEL_RE = re.compile(
      r'^Fingerprint sensor:\s+vendor.+model\s+(\S+)\s+version', re.MULTILINE)
  FPINFO_ERRORS_RE = re.compile(r'^Error flags:\s*(\S*)$', re.MULTILINE)
  FPCHECKPIXELS_DEAD_RE = re.compile(
      r'^Defects:\s+dead\s+(\d+)\s+\(pattern0\s+\d+\s+pattern1\s+\d+\)$',
      re.MULTILINE)

  def MCUCommand(self, command, *args):
    """Execute a host command on the fingerprint MCU

    Args:
      command: the name of the ectool command.

    Returns:
      Command text output.
    """
    cmdline = ['ectool', self.CROS_FP_ARG, command] + list(args)
    result = self._dut.CallOutput(cmdline)
    return result.strip() if result is not None else ''

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()

  def runTest(self):
    # Verify communication with the FPMCU
    fw_version = self.MCUCommand("version")
    match_ro = self.RO_VERSION_RE.search(fw_version)
    match_rw = self.RW_VERSION_RE.search(fw_version)
    self.assertTrue(match_ro != None and match_rw != None,
                    'Unable to retrieve FPMCU version (%s)' % (fw_version))
    if match_ro and match_rw:
      logging.info("FPMCU version RO %s RW %s",
                   match_ro.group(1), match_rw.group(1))

    # Retrieve the sensor identifiers and defects detected by the MCU
    info = self.MCUCommand('fpinfo')
    match_model = self.FPINFO_MODEL_RE.search(info)
    self.assertIsNotNone(match_model,
                         'Unable to retrieve Sensor info (%s)' % (info))
    logging.info('ectool fpinfo:\n%s\n', info)
    model = int(match_model.group(1), 16) if match_model else 0xdead
    match_errors = self.FPINFO_ERRORS_RE.search(info)
    self.assertIsNotNone(match_errors,
                         'Unable to retrieve Sensor error flags (%s)' % (info))
    flags = match_errors.group(1) if match_errors else ''

    self.assertEqual(flags, '',
                     'Sensor failure: %s' % (flags))
    expected_hwid = self.args.sensor_hwid if self.args.sensor_hwid else None
    if not testlog.CheckParam(name='sensor_hwid', value=model,
                              min=expected_hwid, max=expected_hwid,
                              description='Sensor Hardware ID register'):
      raise type_utils.TestFailure('Invalid sensor HWID')

    # Acquire the checkerboard test patterns to find dead pixels
    pixels = self.MCUCommand('fpcheckpixels')
    match_dead = self.FPCHECKPIXELS_DEAD_RE.search(pixels)
    self.assertIsNotNone(match_dead,
                         'Unable to retrieve Sensor dead pixel count (%s)'
                         % (pixels))
    dead = int(match_dead.group(1)) if match_dead else 0
    logging.info('ectool fpcheckpixels:\n%s\n', pixels)
    if not testlog.CheckParam(name='dead_pixels', value=dead,
                              max=self.args.max_dead_pixels,
                              description='Number of dead pixels on the sensor',
                              value_unit='pixels'):
      raise type_utils.TestFailure('Too many dead pixels')

    if self.args.rubber_finger_present:
      # Test sensor image quality
      self.MCUCommand('fpmode', 'capture', 'qual')
      # should wait here for the cros_fp EC_MKBP_FP_IMAGE_READY event, so we
      # know whether we captured a proper image or the finger was not present
      # or the capture failed by using self.MCUCommand('waitevent 1 60000')
      # requires kernel support: crosreview.com/866857
      #      and ectool support: crosreview.com/806167
      time.sleep(0.5)
      img = self.MCUCommand('fpframe', 'raw')
      # record the raw image file for quality evaluation
      testlog.AttachContent(
          content=img,
          name='finger_mqt.raw',
          description='raw MQT finger image')
      # Check quality if the function if available
      if libfputils:
        rc, snr = libfputils.mqt(img)
        logging.info('MQT SNR %f (err:%d)', snr, rc)
        if rc:
          raise type_utils.TestFailure('MQT failed with error %d' % (rc))
        else:
          if not testlog.CheckParam(name='mqt_snr', value=snr,
                                    min=self.args.min_snr,
                                    description='Image signal-to-noise ratio'):
            raise type_utils.TestFailure('Bad quality image')
      elif self.args.min_snr > 0.0:
        raise type_utils.TestFailure('No image quality library available')
