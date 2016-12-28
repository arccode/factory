# -*- coding: UTF-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is sample code of a board specific test.

Board specific test should be put in board overlay, e.g.
~/trunk/src/private-overlays/overlay-${BOARD}-private/chromeos-base/chromeos-factory-board/files/py/pytests/

To avoid file name conflict, please name the python script as "${BOARD}_xxx.py".
For example, if you are implementing your own touchscreen test for board ABC, a
reasonable file name would be: abc_touchscreen.py.
"""


import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.test import testlog
from cros.factory.utils import arg_utils


class SampleCustomizedTest(unittest.TestCase):
  """Example of how to write a pytest.

  The pytest must inherit `unittest.TestCase`, and implement `runTest` function.
  The `runTest` function is similar to the main function of the test.  When the
  test starts, this function will be called.  You can also implement `setUp` and
  `tearDown` functions to make sure something is done before / after the test,
  no matter what.
  """

  ARGS = [
      arg_utils.Arg(
          'foo', int, help='foo can only be int, not optional'),
      arg_utils.Arg(
          'bar', str, help='bar is optional, default to None',
          optional=True),
      arg_utils.Arg(
          'baz', str, help='baz is optional, default to "BAZ"',
          default="BAZ"),
      ]
  """Arguments of this pytest.

  Arguments of a pytest is defined by class variable "ARGS", which must be a
  list of `cros.factory.utils.arg_utils.Arg` object.  You can specify the value
  of each argument in the test list:

      FactoryTest(
          ...,
          dargs={
              'foo': 123,
              'bar': 'value of bar',
              # not setting value of 'baz', it will use default value.
          })
  """

  def setUp(self):
    """Setup function."""
    self.dut = device_utils.CreateDUTInterface()
    # from now on, you can use `self.dut` to control stuff on DUT
    # for example, create a temporary folder on DUT
    self.temp_dir = self.dut.temp.mktemp(is_dir=True)

  def tearDown(self):
    """Tear down function (for clean up)."""
    # remove the folder we created, and everything inside that folder.
    self.dut.CheckCall(['rm', '-rf', self.temp_dir])

  def runTest(self):
    """Main function of the test.  Implement test logic in this function."""

    # for example, measure some value on DUT.
    photo_path = self.TakePhoto()

    # when you use logging, the message will be logged by testlog automatically.
    logging.info('Image captured, attaching to testlog...')

    # attach the file to the testlog
    testlog.AttachFile(
        path=photo_path, mime_type='image/jpeg', name='front_camera.jpeg',
        description='image captured by the front camera for quality test.')

    quality = self.ComputePhotoQuality(photo_path)
    # check and log the value, note that testlog will NOT fail the test for you,
    # you have to raise an exception by yourself.
    if not testlog.CheckParam(
        name='photo_quality',
        value=quality,
        min=0.9, max=1.0,
        description='Quality of the photo'):
      raise factory.FactoryTestFailure('The camera is not qualified')

    # you can also measure and log a series of values
    series_logger = testlog.CreateSeries(
        name='audio_quality',
        description='quality of audio device on different frequency',
        key_unit='Hz', value_unit='quality')

    failed = False
    for freq in xrange(1000, 4000, 50):
      quality = self.MeasureAudioQuality(freq)
      if not series_logger.CheckValue(
          key=str(freq), value=quality, min=0.8, max=None):
        failed = True
    if failed:
      raise factory.FactoryTestFailure('The audio device is not qualified')

  def TakePhoto(self):
    raise NotImplementedError

  def ComputePhotoQuality(self, photo_path):
    raise NotImplementedError

  def MeasureAudioQuality(self, freq):
    raise NotImplementedError
