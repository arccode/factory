# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
Implementation for light chamber connection.
"""

try:
  import cv   # pylint: disable=F0401
  import cv2  # pylint: disable=F0401
except ImportError:
  pass
import os

from cros.factory.test.utils import Enum

# Reference test chart image file.
_TEST_CHART_FILE = 'test_chart_%s.png'

# Default mock image.
_MOCK_IMAGE_FILE = 'mock_%s.jpg'

TestType = Enum(['CALI', 'MODULE', 'AB', 'FULL'])


class LightChamberError(Exception):
  pass


class LightChamber(object):
  def __init__(self, test_type, test_chart_version, mock_mode, device_index,
               image_resolution):
    """
    Args:
      test_type: Current light chamber test type (TestType).
      test_chart_version: Version of the test chart.
      mock_mode: Run in mock mode.
      device_index: Video device index (-1 to auto pick device by OpenCV).
      image_resolution: A tuple (x-res, y-res) for image resolution.
    """
    assert test_chart_version in ('A', 'B')
    assert mock_mode in (True, False)

    self.test_type = test_type
    self.test_chart_version = test_chart_version
    self.mock_mode = mock_mode
    self.device_index = device_index
    self.image_resolution = image_resolution

    self._camera_device = None

  def __del__(self):
    """An evil destructor to always close camera device.

    Remarks: it happened before that broken USB driver cannot handle the case
    that camera device is not closed properly.
    """
    self.DisableCamera()

  def GetTestChartFile(self):
    return os.path.join(os.path.dirname(__file__), 'static',
                        _TEST_CHART_FILE % self.test_chart_version)

  def _ReadMockImage(self):
    fpath = os.path.join(os.path.dirname(__file__), 'static',
                         _MOCK_IMAGE_FILE % self.test_chart_version)
    return cv2.imread(fpath)

  def EnableCamera(self):
    """Open camera device."""
    if self.mock_mode:
      return

    device = cv2.VideoCapture(self.device_index)
    if not device.isOpened():
      raise LightChamberError('Cannot open video interface #%d' %
                              self.device_index)
    width, height = self.image_resolution
    device.set(cv.CV_CAP_PROP_FRAME_WIDTH, width)
    device.set(cv.CV_CAP_PROP_FRAME_HEIGHT, height)
    if (device.get(cv.CV_CAP_PROP_FRAME_WIDTH) != width or
        device.get(cv.CV_CAP_PROP_FRAME_HEIGHT) != height):
      device.release()
      raise LightChamberError('Cannot set video resolution')

    self._camera_device = device

  def DisableCamera(self):
    """Releases camera device."""
    if self.mock_mode:
      return

    if self._camera_device:
      self._camera_device.release()
      self._camera_device = None

  def ReadSingleFrame(self):
    """Read a single frame from camera device.

    Returns:
      Returns color image, grayscale image.
    """
    if self.mock_mode:
      ret, img = True, self._ReadMockImage()
    else:
      assert self._camera_device, 'Camera device is not opened'
      ret, img = self._camera_device.read()

    if not ret or img is None:
      raise LightChamberError('Error while capturing. Camera disconnected?')

    return (img, cv2.cvtColor(img, cv.CV_BGR2GRAY))
