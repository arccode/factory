# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Plankton-HDMI: a video capture card to capture DP/HDMI.

It converts DP/HDMI to UVC camera (a USB3 device).
"""

try:
  import cv2 as cv
except ImportError:
  pass

import glob
import logging
import re
import threading
import time


class PlanktonHDMIException(Exception):
  pass


class PlanktonHDMI:
  _VIDEO_STREAM_THREAD_JOIN_TIMEOUT_SECS = 1.0

  def __init__(self, uvc_video_index=None, uvc_video_port=None,
               capture_resolution=(1920, 1080), capture_fps=30):
    """Initializes PlanktonHDMI.

    Args:
      uvc_video_index: index of PlanktonHDMI video device (default None
          for looking up video device from uvc_video_port).
      uvc_video_port: PlanktonHDMI's USB port index, e.g. 3-1 (default None,
          required if uvc_video_index is None.)
      capture_resolution: capture resolution (x, y).
      capture_fps: capture FPS.
    """
    self._camera_device = None
    self._camera_enabled = False
    self._uvc_video_index = uvc_video_index
    self._uvc_video_port = uvc_video_port if uvc_video_index is None else None
    self._capture_resolution = capture_resolution
    self._capture_fps = capture_fps
    self._capture_thread = None
    self._stream_finished = False

  def __del__(self):
    self.DisableCamera()

  def EnableCamera(self):
    """Enables and connects to camera device.

    Open a thread to read stream from camera in order to make Plankton-HDMI an
    active display device to DUT.
    """
    if self._camera_enabled:
      return

    # uvc_video_index may change after some plugging operations if there are
    # more than 1 Plankton-HDMI board. So it needs to find index everytime you
    # enable camera.
    if self._uvc_video_port:
      self._uvc_video_index = self.FindUVCVideoDeviceIndex(self._uvc_video_port)

    logging.debug('Create VideoCapture(index=%r)', self._uvc_video_index)
    self._camera_device = cv.VideoCapture(self._uvc_video_index)
    if not self._camera_device.isOpened():
      raise PlanktonHDMIException(
          'Unable to open video capture interface: %r' % self._uvc_video_index)

    # Set camera capture to HD resolution.
    logging.debug('Set capture resolution')
    x_res, y_res = self._capture_resolution
    self._camera_device.set(cv.CAP_PROP_FPS, self._capture_fps)
    self._camera_device.set(cv.CAP_PROP_FRAME_WIDTH, x_res)
    self._camera_device.set(cv.CAP_PROP_FRAME_HEIGHT, y_res)

    # Open read stream thread. Plankton-HDMI needs to be an active streaming
    # camera device if we need to regard it as an auto-detectable external
    # display as well.
    logging.debug('Start camera stream')
    self._capture_thread = threading.Thread(target=self._CameraStream)
    self._capture_thread.daemon = True
    self._capture_thread.start()
    self._camera_enabled = True

  def DisableCamera(self):
    """Disables the camrea capturing thread."""
    if not self._camera_enabled:
      logging.info('Camera already disabled')
      return

    self._stream_finished = True
    self._capture_thread.join(self._VIDEO_STREAM_THREAD_JOIN_TIMEOUT_SECS)

    if self._camera_device.isOpened():
      self._camera_device.release()
    self._camera_enabled = False
    logging.info('Camera disabled successfully')

  def Capture(self):
    """Captures an image from video.

    Returns:
      A captured image from camrea device.

    Raises:
      PlanktonHDMIException when capture error.
    """
    if not self._camera_enabled:
      raise PlanktonHDMIException('Camera disabled. Call EnableCamera() first')

    ret, captured_image = self._camera_device.read()
    if not ret:
      raise PlanktonHDMIException('Error capturing. DP Loopback distached?')

    height, width = captured_image.shape[:2]
    logging.debug('Image captured, size: %dx%d', width, height)
    return captured_image

  def CaptureToFile(self, file_path):
    """Captures an image and saves to a file.

    This is mainly for development/debugging use.

    Args:
      file_path: Path of captured image to be saved.

    Returns:
      False if it captures nothing.
    """
    captured_image = self.Capture()
    logging.info('Image captured. Writing to file %s', file_path)
    cv.imwrite(file_path, captured_image)
    return True

  def CaptureCompare(self, golden_image_path, threshold, return_corr=False):
    """Compares captured image with given image.

    It compares two images' bgr-channel histograms' correlation.

    Args:
      golden_image_path: Path to golden image.
      threshold: A tuple of (b, g, r) channel histogram pass threshold.
      return_corr: Set True for returning corr_values directly.

    Returns:
      If return_corr is False, return True if two images' histogram correlation
      is high enough. If return_corr is True, return correlation values directly
      without comparing to threshold.
    """
    logging.debug('Comparing captured image w/ golden image: %s',
                  golden_image_path)

    golden_image = cv.imread(golden_image_path)
    golden_image = cv.resize(golden_image, self._capture_resolution)

    # Compare two images.
    # Retries are added to avoid false alarms when getting flaky images
    # probably from USB-C DP stream in the bounce time of projecting to the
    # external monitor.
    for unused_i in range(8):
      captured_image = self.Capture()
      if self.CompareImage(captured_image, golden_image, threshold,
                           return_corr):
        logging.info('Comparing captured image w/ golden image passed')
        return True
      logging.info('Comparing captured image w/ golden image failed')
      time.sleep(0.25)

    return False

  def CaptureCheckPixels(self, points):
    """Captures an image and grabs the values of some pixels.

    Args:
      points: A list of checked point locations (x, y)

    Returns:
      A list of pixel values (b, g, r) of captured image.
    """
    captured_image = self.Capture()
    pixels = []
    for x, y in points:
      value = (int(captured_image[y, x, 0]),
               int(captured_image[y, x, 1]),
               int(captured_image[y, x, 2]))
      logging.info('Get pixel (%d, %d) = %s', x, y, str(value))
      pixels.append(value)
    return pixels

  def _CameraStream(self):
    """A daemon thread to read camera in target fps.

    Raises:
      BFTFixtureException if it fails to detect camera.
    """
    self._stream_finished = False
    tick = 1.0 / self._capture_fps
    # _stream_finish will be set to True by main thread's DisableCamrea.
    while not self._stream_finished:
      ret, _ = self._camera_device.read()
      if not ret:
        raise PlanktonHDMIException('Error capturing. DP Loopback distached?')
      time.sleep(tick)

  @staticmethod
  def FindUVCVideoDeviceIndex(device_port):
    """Searches uvcvideo device index in sysfs with given video port index.

    Args:
      device_port: Video device port index.

    Returns:
      UVC video device index.

    Raises:
      PlanktonHDMIException: if it failed to find camera device.
    """
    if not device_port:
      raise PlanktonHDMIException('Unspecified uvc_video_port')
    uvc_vid_dirs = glob.glob(
        '/sys/bus/usb/drivers/uvcvideo/%s*/video4linux/video*' % device_port)
    if not uvc_vid_dirs:
      raise PlanktonHDMIException('No DP loopback interface found')
    if len(uvc_vid_dirs) > 1:
      raise PlanktonHDMIException(
          'Multiple DP loopback interface found')
    return int(re.search(r'video([0-9]+)$', uvc_vid_dirs[0]).group(1))

  @staticmethod
  def CompareImage(image1, image2, threshold=(0.8, 0.8, 0.8),
                   return_corr=False):
    """Compares bgr-channel histograms for two images by correlation.

    Args:
      image1, image2: Two cv image objects to be compared.
      threshold: A tuple of (b, g, r) channel histogram pass threshold.
      return_corr: Set True for returning corr_values directly.

    Returns:
      If return_corr is False, return True if two images' histogram correlation
      is high enough. If return_corr is True, return correlation values directly
      without comparing to threshold.
    """
    corr_values = []
    result = True
    for color_channel in range(3):  # b, g, r channels
      hist1 = cv.calcHist([image1], [color_channel], None, [256], [0, 255])
      hist2 = cv.calcHist([image2], [color_channel], None, [256], [0, 255])
      corr = cv.compareHist(hist1, hist2, method=cv.HISTCMP_CORREL)
      corr_values.append(corr)
      if corr < threshold[color_channel]:
        result = False
        logging.info('Correlation of channel %d == %.2f < threshold %.2f',
                     color_channel, corr, threshold[color_channel])

    logging.info('CompareHist correlation result = b: %.4f, g: %.4f, r: %.4f',
                 corr_values[0], corr_values[1], corr_values[2])
    return corr_values if return_corr else result
