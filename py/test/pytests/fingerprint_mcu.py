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
    "pytest_name": "fingerprint_mcu"
  }

To check if the sensor has at most 10 dead pixels and its HWID is 0x140c,
with bounds for the pixel grayscale median values and finger detection zones,
add this in test list::

  {
    "pytest_name": "fingerprint_mcu",
    "args": {
      "dead_pixel_max": 10,
      "sensor_hwid": 5132,
      "pixel_median": {
        "cb_type1" : [180, 220],
        "cb_type2" : [80, 120],
        "icb_type1" : [15, 70],
        "icb_type2" : [155, 210]
      },
      "detect_zones" : [
        [8, 16, 15, 23], [24, 16, 31, 23], [40, 16, 47, 23],
        [8, 66, 15, 73], [24, 66, 31, 73], [40, 66, 47, 73],
        [8, 118, 15, 125], [24, 118, 31, 125], [40, 118, 47, 125],
        [8, 168, 15, 175], [24, 168, 31, 175], [40, 168, 47, 175]
      ]
    }
  }
"""

import logging
import re
import sys
import unittest

import numpy

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
      Arg('sensor_hwid', (int, list),
          'The finger sensor Hardware ID exported in the model field.',
          default=None),
      Arg('max_dead_pixels', int,
          'The maximum number of dead pixels on the fingerprint sensor.',
          default=10),
      Arg('max_dead_detect_pixels', int,
          'The maximum number of dead pixels in the detection zone.',
          default=0),
      Arg('max_pixel_dev', int,
          'The maximum deviation from the median for a pixel of a given type.',
          default=35),
      Arg('pixel_median', dict,
          'Keys: "(cb|icb)_(type1|type2)", '
          'Values: a list of [minimum, maximum] '
          'Range constraints of the pixel median value of the checkerboards.',
          default={}),
      Arg('detect_zones', list,
          'a list of rectangles [x1, y1, x2, y2] defining '
          'the finger detection zones on the sensor.',
          default=[]),
      Arg('min_snr', float,
          'The minimum signal-to-noise ratio for the image quality.',
          default=0.0),
      Arg('rubber_finger_present', bool,
          'A Rubber finger is pressed against the sensor for quality testing.',
          default=False),
  ]

  # Select the Fingerprint MCU cros_ec device
  CROS_FP_ARG = "--name=cros_fp"
  # MKBP index for Fingerprint sensor event
  EC_MKBP_EVENT_FINGERPRINT = '5'

  # Regular expression for parsing ectool output.
  RO_VERSION_RE = re.compile(r'^RO version:\s*(\S+)\s*$', re.MULTILINE)
  RW_VERSION_RE = re.compile(r'^RW version:\s*(\S+)\s*$', re.MULTILINE)
  FPINFO_MODEL_RE = re.compile(
      r'^Fingerprint sensor:\s+vendor.+model\s+(\S+)\s+version', re.MULTILINE)
  FPINFO_ERRORS_RE = re.compile(r'^Error flags:\s*(\S*)$', re.MULTILINE)

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

  def tearDown(self):
    self.MCUCommand('fpmode', 'reset')

  def isDetectZone(self, x, y):
    for x1, y1, x2, y2 in self.args.detect_zones:
      if (x in range(x1, x2 + 1) and
          y in range(y1, y2 + 1)):
        return True
    return False

  def processCheckboardPixels(self, lines, parity):
    # Keep only type-1 or type-2 pixels depending on parity
    matrix = numpy.array([[(int(v), x, y) for x, v
                           in enumerate(l.strip().split())
                           if (x + y) % 2 == parity]
                          for y, l in enumerate(lines)])
    # Transform the 2D array of triples in a 1-D array of triples
    pixels = matrix.reshape((-1, 3))
    median = numpy.median([v for v, x, y in pixels])
    dev = [(abs(v - median), x, y) for v, x, y in pixels]
    return median, dev

  def checkerboardTest(self, inverted=False):
    full_name = 'Inv. checkerboard' if inverted else 'Checkerboard'
    short_name = 'icb' if inverted else 'cb'
    # trigger the checkerboard test pattern and capture it
    self.MCUCommand('fpmode', 'capture', 'pattern1' if inverted else 'pattern0')
    # wait for the end of capture (or timeout after 500 ms)
    self.MCUCommand('waitevent', self.EC_MKBP_EVENT_FINGERPRINT, '500')
    # retrieve the resulting image as a PNM
    pnm = self.MCUCommand('fpframe')
    if not pnm:
      raise type_utils.TestFailure('Failed to retrieve checkerboard image')
    lines = pnm.split('\n')
    if lines[0].strip() != 'P2':
      raise type_utils.TestFailure('Unsupported/corrupted image')
    # Build arrays of black and white pixels (aka Type-1 / Type-2)
    try:
      # PNM image size: w, h = [int(i) for i in lines[1].split()]
      # strip header/footer
      pixel_lines = lines[3:-1]
      # Compute pixels parameters for each type
      median1, dev1 = self.processCheckboardPixels(pixel_lines, 0)
      median2, dev2 = self.processCheckboardPixels(pixel_lines, 1)
    except (IndexError, ValueError):
      raise type_utils.TestFailure('Corrupted image')
    all_dev = dev1 + dev2
    max_dev = numpy.max([d for d, _, _ in all_dev])
    # Count dead pixels (deviating too much from the median)
    dead_count = 0
    dead_detect_count = 0
    for d, x, y in all_dev:
      if d > self.args.max_pixel_dev:
        dead_count += 1
        if self.isDetectZone(x, y):
          dead_detect_count += 1
    # Log everything first for debugging
    logging.info('%s type 1 median:\t%d', full_name, median1)
    logging.info('%s type 2 median:\t%d', full_name, median2)
    logging.info('%s max deviation:\t%d', full_name, max_dev)
    logging.info('%s dead pixels:\t%d', full_name, dead_count)
    logging.info('%s dead pixels in detect zones:\t%d',
                 full_name, dead_detect_count)

    testlog.UpdateParam(
        name='dead_pixels_%s' % short_name,
        description='Number of dead pixels',
        value_unit='pixels')
    if not testlog.CheckNumericParam(
        name='dead_pixels_%s' % short_name,
        value=dead_count,
        max=self.args.max_dead_pixels):
      raise type_utils.TestFailure('Too many dead pixels')
    testlog.UpdateParam(
        name='dead_detect_pixels_%s' % short_name,
        description='Dead pixels in detect zone',
        value_unit='pixels')
    if not testlog.CheckNumericParam(
        name='dead_detect_pixels_%s' % short_name,
        value=dead_detect_count,
        max=self.args.max_dead_detect_pixels):
      raise type_utils.TestFailure('Too many dead pixels in detect zone')
    # Check specified pixel range constraints
    t1 = "%s_type1" % short_name
    testlog.UpdateParam(
        name=t1,
        description='Median Type-1 pixel value',
        value_unit='8-bit grayscale')
    if t1 in self.args.pixel_median and not testlog.CheckNumericParam(
        name=t1,
        value=median1,
        min=self.args.pixel_median[t1][0],
        max=self.args.pixel_median[t1][1]):
      raise type_utils.TestFailure('Out of range Type-1 pixels')
    t2 = "%s_type2" % short_name
    testlog.UpdateParam(
        name=t2,
        description='Median Type-2 pixel value',
        value_unit='8-bit grayscale')
    if t2 in self.args.pixel_median and not testlog.CheckNumericParam(
        name=t2,
        value=median2,
        min=self.args.pixel_median[t2][0],
        max=self.args.pixel_median[t2][1]):
      raise type_utils.TestFailure('Out of range Type-2 pixels')

  def runTest(self):
    # Verify communication with the FPMCU
    fw_version = self.MCUCommand("version")
    match_ro = self.RO_VERSION_RE.search(fw_version)
    match_rw = self.RW_VERSION_RE.search(fw_version)
    self.assertTrue(match_ro is not None and match_rw is not None,
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
    model = int(match_model.group(1), 16)
    match_errors = self.FPINFO_ERRORS_RE.search(info)
    self.assertIsNotNone(match_errors,
                         'Unable to retrieve Sensor error flags (%s)' % (info))
    flags = match_errors.group(1) if match_errors else ''

    self.assertEqual(flags, '',
                     'Sensor failure: %s' % (flags))
    expected_hwid = type_utils.MakeList(self.args.sensor_hwid or [])
    testlog.UpdateParam(
        name='sensor_hwid', description='Sensor Hardware ID register')
    testlog.LogParam('sensor_hwid', model)
    if expected_hwid and model not in expected_hwid:
      raise type_utils.TestFailure('Invalid sensor HWID: %r' % model)

    # checkerboard test patterns
    self.checkerboardTest(inverted=False)
    self.checkerboardTest(inverted=True)

    if self.args.rubber_finger_present:
      # Test sensor image quality
      self.MCUCommand('fpmode', 'capture', 'qual')
      # wait for the end of capture (or timeout after 5s)
      self.MCUCommand('waitevent', self.EC_MKBP_EVENT_FINGERPRINT, '5000')
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
          testlog.UpdateParam(
              name='mqt_snr', description='Image signal-to-noise ratio')
          if not testlog.CheckNumericParam(
              name='mqt_snr', value=snr, min=self.args.min_snr):
            raise type_utils.TestFailure('Bad quality image')
      elif self.args.min_snr > 0.0:
        raise type_utils.TestFailure('No image quality library available')
