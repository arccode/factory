# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is the sample code of a board specific test.

Description
-----------
This is a sample test code to demostrate how to write a board-specific test.

A board specific test should be put in the board overlay. For example, assuming
the overlay is located at
``~/trunk/src/private-overlays/overlay-${BOARD}-private``, then you have to
create the factory-board package and put files under relative path
``chromeos-base/factory-board/files/py/pytests/``.

To avoid file name conflict, please name the python script as "${BOARD}_xxx.py".
For example, if you are implementing your own touchscreen test for board ABC, a
reasonable file name would be: ``abc_touchscreen.py``.

Test Procedure
--------------
This is only a sample code to demonstrate how to write a board-specific test.

Dependency
----------
None.

Examples
--------
To run this sample code with default arguments, add this in test list::

  {
    "pytest_name": "sample_customized_test",
    "args": {
      "foo": 1
    }
  }
"""


import logging
import unittest

from cros.factory.device import device_utils
from cros.factory.testlog import testlog
from cros.factory.utils import arg_utils
from cros.factory.utils import type_utils


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
          default=None),
      arg_utils.Arg(
          'baz', str, help='baz is optional, default to "BAZ"',
          default="BAZ"),
  ]
  """Arguments of this pytest.

  Arguments of a pytest is defined by class variable "ARGS", which must be a
  list of `cros.factory.utils.arg_utils.Arg` object.  You can specify the value
  of each argument in the test list:

      {
        "pytest_name": "sample_customized_test",
        "args": {
          "foo": 123,
          "bar": "value of bar"
        }
      }

  The value for argument "baz" is not set in the above example, so it will use
  default value "BAZ".
  """

  def setUp(self):
    """Setup function."""
    self.dut = device_utils.CreateDUTInterface()
    # from now on, you can use `self.dut` to control stuff on DUT
    # for example, create a temporary folder on DUT
    self.temp_dir = self.dut.temp.mktemp(is_dir=True)

    # Group checker for Testlog.
    self.group_checker = testlog.GroupParam(
        'audio', ['audio_quality', 'audio_frequency'])
    testlog.UpdateParam('audio_frequency',
                        param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam(
        name='audio_quality',
        description='quality of audio device on different frequency',
        value_unit='quality')
    testlog.UpdateParam(
        name='audio_frequency',
        value_unit='Hz')

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
    testlog.UpdateParam(
        name='photo_quality',
        description='Quality of the photo')
    if not testlog.CheckNumericParam(
        name='photo_quality',
        value=quality,
        min=0.9, max=1.0):
      raise type_utils.TestFailure('The camera is not qualified')

    failed = False
    for freq in range(1000, 4000, 50):
      quality = self.MeasureAudioQuality(freq)
      # you can also measure and log a series of values
      with self.group_checker:
        if not testlog.CheckNumericParam('audio_quality', quality, min=0.8):
          failed = True
        testlog.LogParam('audio_frequency', freq)
    if failed:
      raise type_utils.TestFailure('The audio device is not qualified')

  def TakePhoto(self):
    raise NotImplementedError

  def ComputePhotoQuality(self, photo_path):
    raise NotImplementedError

  def MeasureAudioQuality(self, freq):
    raise NotImplementedError
