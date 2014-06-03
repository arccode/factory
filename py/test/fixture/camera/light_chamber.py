# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation for light chamber connection."""

try:
  import cv   # pylint: disable=F0401
  import cv2  # pylint: disable=F0401
except ImportError:
  pass

import numpy as np
import os


# Reference test chart image file.
_TEST_CHART_FILE = 'test_chart_%s.png'

# Default mock image.
_MOCK_IMAGE_FILE = 'mock_%s.jpg'


class LightChamberError(Exception):
  """Light chamber exception class."""
  pass


class LightChamber(object):
  """Light chamber interface."""
  def __init__(self, test_chart_version, mock_mode, device_index,
               image_resolution):
    """Initializes LightChamber.

    Args:
      test_chart_version: Version of the test chart.
      mock_mode: Run in mock mode.
      device_index: Video device index (-1 to auto pick device by OpenCV).
      image_resolution: A tuple (x-res, y-res) for image resolution.
    """
    assert test_chart_version in ('A', 'B', 'White', 'QR')
    assert mock_mode in (True, False)

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

  def ReadSingleFrame(self, return_gray_image=True):
    """Reads a single frame from camera device.

    Args:
      return_gray_image: Whether to return grayscale image.

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

    return (img,
            cv2.cvtColor(img, cv.CV_BGR2GRAY) if return_gray_image else None)

  def ReadLowNoisesFrame(self, sample_count, return_gray_image=True):
    """Reads multiple frames and average them into a single image to reduce
    noises.

    Args:
      sample_count: The number of frames to take.
      return_gray_image: Whether to return grayscale image.

    Returns:
      Returns averaged color image, grayscale image.
    """
    assert sample_count >= 1
    img, _ = self.ReadSingleFrame(return_gray_image=False)
    img = img.astype(np.float64)
    for unused_counter in xrange(sample_count - 1):
      t, _ = self.ReadSingleFrame(return_gray_image=False)
      img += t.astype(np.float64)
    img /= sample_count
    img = img.round().astype(np.uint8)
    return (img,
            cv2.cvtColor(img, cv.CV_BGR2GRAY) if return_gray_image else None)
