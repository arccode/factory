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
      "sensor_hwid": [
        1234,
        [5120, 65520]
      ],
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
import sys
import unittest

import numpy

from cros.factory.device import device_utils
from cros.factory.testlog import testlog
from cros.factory.test.utils import fpmcu_utils
from cros.factory.utils import type_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import schema

# use the fingerprint image processing library if available
sys.path.extend(['/usr/local/opt/fpc', '/opt/fpc'])
try:
  import fputils
  libfputils = fputils.FpUtils()
except ImportError:
  libfputils = None

_ARG_SENSOR_HWID_SCHEMA = schema.JSONSchemaDict(
    'sensor hwid schema object',
    {
        'anyOf': [
            {
                'type': ['integer', 'null']
            },
            {
                'type': 'array',
                'items': {
                    'anyOf': [
                        {
                            'type': 'integer'
                        },
                        {
                            'type': 'array',
                            'items': {
                                'type': 'integer'
                            },
                            'minItems': 2,
                            'maxItems': 2
                        }
                    ]
                }
            }
        ]
    })

class FingerprintTest(unittest.TestCase):
  """Tests the fingerprint sensor."""
  ARGS = [
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
      Arg('max_reset_pixel_dev', int,
          'The maximum deviation from the median per column for a pixel from '
          'test reset image.',
          default=55),
      Arg('max_error_reset_pixels', int,
          'The maximum number of error pixels in the test_reset image.',
          default=5),
      Arg('fpframe_retry_count', int,
          'The maximum number of retry for fpframe.',
          default=0),
  ]

  # MKBP index for Fingerprint sensor event
  EC_MKBP_EVENT_FINGERPRINT = '5'


  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._fpmcu = fpmcu_utils.FpmcuDevice(self._dut)

  def tearDown(self):
    self._fpmcu.FpmcuCommand('fpmode', 'reset')

  def FpmcuTryWaitEvent(self, *args, **kwargs):
    try:
      self._fpmcu.FpmcuCommand('waitevent', *args, **kwargs)
    except Exception as e:
      logging.error('Wait event fail: %s', e)

  def FpmcuGetFpframe(self, *args, **kwargs):
    # try fpframe command for at most (fpframe_retry_count + 1) times.
    for num_retries in range(self.args.fpframe_retry_count + 1):
      try:
        img = self._fpmcu.FpmcuCommand('fpframe', *args, **kwargs)
        break
      except Exception as e:
        if num_retries < self.args.fpframe_retry_count:
          logging.info('Retrying fpframe %d times', num_retries + 1)
        else:
          # raise an exception if last attempt failed
          raise e
    return img

  def IsDetectZone(self, x, y):
    for x1, y1, x2, y2 in self.args.detect_zones:
      if (x in range(x1, x2 + 1) and
          y in range(y1, y2 + 1)):
        return True
    return False

  def CheckPnmAndExtractPixels(self, pnm):
    if not pnm:
      raise type_utils.TestFailure('Failed to retrieve image')
    lines = pnm.split('\n')
    if lines[0].strip() != 'P2':
      raise type_utils.TestFailure('Unsupported/corrupted image')
    try:
      # strip header/footer
      pixel_lines = lines[3:-1]
    except (IndexError, ValueError):
      raise type_utils.TestFailure('Corrupted image')

    return pixel_lines

  def CalculateMedianAndDev(self, matrix):
    # Transform the 2D array of triples in a 1-D array of triples
    pixels = matrix.reshape((-1, 3))
    median = numpy.median([v for v, x, y in pixels])
    dev = [(abs(v - median), x, y) for v, x, y in pixels]
    return median, dev

  def ProcessCheckboardPixels(self, lines, parity):
    # Keep only type-1 or type-2 pixels depending on parity
    matrix = numpy.array([[(int(v), x, y) for x, v
                           in enumerate(l.strip().split())
                           if (x + y) % 2 == parity]
                          for y, l in enumerate(lines)])
    return self.CalculateMedianAndDev(matrix)

  def CheckerboardTest(self, inverted=False):
    full_name = 'Inv. checkerboard' if inverted else 'Checkerboard'
    short_name = 'icb' if inverted else 'cb'
    # trigger the checkerboard test pattern and capture it
    self._fpmcu.FpmcuCommand('fpmode', 'capture',
                             'pattern1' if inverted else 'pattern0')
    # wait for the end of capture (or timeout after 500 ms)
    self.FpmcuTryWaitEvent(self.EC_MKBP_EVENT_FINGERPRINT, '500')
    # retrieve the resulting image as a PNM
    pnm = self.FpmcuGetFpframe()

    pixel_lines = self.CheckPnmAndExtractPixels(pnm)
    # Build arrays of black and white pixels (aka Type-1 / Type-2)
    # Compute pixels parameters for each type
    median1, dev1 = self.ProcessCheckboardPixels(pixel_lines, 0)
    median2, dev2 = self.ProcessCheckboardPixels(pixel_lines, 1)

    all_dev = dev1 + dev2
    max_dev = numpy.max([d for d, _, _ in all_dev])
    # Count dead pixels (deviating too much from the median)
    dead_count = 0
    dead_detect_count = 0
    for d, x, y in all_dev:
      if d > self.args.max_pixel_dev:
        dead_count += 1
        if self.IsDetectZone(x, y):
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

  def CalculateMedianAndDevPerColumns(self, matrix):
    # The data flow of the input matrix would be
    #  1. original matrix:
    #     [1, 2, 150]
    #     [1, 2, 150]
    #     [1, 2, 3  ]
    #  2. rotate 90 to access column in an index of array:
    #     [150, 150, 3]
    #     [2,   2,   2]
    #     [1,   1,   1]
    #  3. flipud first level of array to put first column at index 0:
    #     [1,   1,   1]
    #     [2,   2,   2]
    #     [150, 150, 3]
    #  4. medians per column - [1, 2, 150]
    #  5. devs per column:
    #     [0, 0, 0  ]
    #     [0, 0, 0  ]
    #     [0, 0, 147]
    matrix = numpy.rot90(matrix)
    matrix = numpy.flipud(matrix)
    medians = [numpy.median([v for v, x, y in l]) for l in matrix]
    devs = [[(abs(v - medians[x]), x, y) for v, x, y in l] for l in matrix]
    return medians, devs

  def ProcessResetPixelImage(self, lines):
    matrix = numpy.array([[(int(v), x, y) for x, v
                           in enumerate(l.strip().split())]
                          for y, l in enumerate(lines)])
    return self.CalculateMedianAndDevPerColumns(matrix)

  def ResetPixelTest(self):
    # reset the sensor and leave it in reset state then capture the single
    # frame.
    self._fpmcu.FpmcuCommand('fpmode', 'capture', 'test_reset')
    # wait for the end of capture (or timeout after 500 ms)
    self.FpmcuTryWaitEvent(self.EC_MKBP_EVENT_FINGERPRINT, '500')
    # retrieve the resulting image as a PNM
    pnm = self.FpmcuGetFpframe()

    pixel_lines = self.CheckPnmAndExtractPixels(pnm)
    # Compute median value and the deviation of every pixels per column.
    medians, devs = self.ProcessResetPixelImage(pixel_lines)
    # Count error pixels (deviating too much from the median)
    error_count = 0
    max_dev_per_columns = [numpy.max([d for d, _, _ in col]) for col in devs]
    for col in devs:
      for d, _, _ in col:
        if d > self.args.max_reset_pixel_dev:
          error_count += 1

    # Log everything first for debugging
    logging.info('error_count:\t%d', error_count)
    logging.info('median per columns: %s', medians)
    logging.info('max dev per columns (col, max_dev, median):\t%s',
                 max_dev_per_columns)
    testlog.UpdateParam(
        name='error_reset_pixel',
        description='Number of error reset pixels',
        value_unit='pixels')
    if not testlog.CheckNumericParam(
        name='error_reset_pixel',
        value=error_count,
        max=self.args.max_error_reset_pixels):
      raise type_utils.TestFailure('Too many error reset pixels')

  def runTest(self):
    # Verify communication with the FPMCU
    ro_ver, rw_ver = self._fpmcu.GetFpmcuFirmwareVersion()
    self.assertTrue(ro_ver is not None and rw_ver is not None,
                    'Unable to retrieve FPMCU version')
    logging.info("FPMCU version RO %s RW %s", ro_ver, rw_ver)

    # checkerboard test patterns
    self.CheckerboardTest(inverted=False)
    self.CheckerboardTest(inverted=True)
    self.ResetPixelTest()

    if self.args.rubber_finger_present:
      # Test sensor image quality
      self._fpmcu.FpmcuCommand('fpmode', 'capture', 'qual')
      # wait for the end of capture (or timeout after 5s)
      self.FpmcuTryWaitEvent(self.EC_MKBP_EVENT_FINGERPRINT, '5000')
      img = self.FpmcuGetFpframe('raw', encoding=None)
      # record the raw image file for quality evaluation
      testlog.AttachContent(
          content=str(img),
          name='finger_mqt.raw',
          description='raw MQT finger image')
      # Check quality if the function if available
      if libfputils:
        rc, snr = libfputils.mqt(img)
        logging.info('MQT SNR %f (err:%d)', snr, rc)
        if rc:
          raise type_utils.TestFailure('MQT failed with error %d' % (rc))
        testlog.UpdateParam(
            name='mqt_snr', description='Image signal-to-noise ratio')
        if not testlog.CheckNumericParam(
            name='mqt_snr', value=snr, min=self.args.min_snr):
          raise type_utils.TestFailure('Bad quality image')
      elif self.args.min_snr > 0.0:
        raise type_utils.TestFailure('No image quality library available')
