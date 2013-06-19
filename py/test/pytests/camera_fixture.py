# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Camera fixture test.

The current code only supports camera fixture calibration, the remaining
functionality are implemented in factory_CameraPerformanceAls.py.
"""

import base64
try:
  import cv   # pylint: disable=F0401
  import cv2  # pylint: disable=F0401
except ImportError:
  pass
import logging
import os
import Queue
import time
import unittest

from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.fixture.camera.camera_utils import EncodeCVImage
from cros.factory.test.fixture.camera.light_chamber import TestType, \
                                                        LightChamber
import cros.factory.test.fixture.camera.perf_tester as camperf
import cros.factory.test.fixture.camera.renderer as renderer
from cros.factory.test.utils import Enum

# Delay between each frame during calibration.
CALIBRATION_FPS = 15

# Calibration configuration for CheckVisualCorrectness().
CALIBRATION_DEFAULT_CONFIG = {
    'register_grid': False,
    'min_corner_quality_ratio': 0.05,
    'min_square_size_ratio': 0.022,
    'min_corner_distance_ratio': 0.010
    }

# TODO(jchuang): import from event.py
MAX_MESSAGE_SIZE = 60000

class CameraFixture(unittest.TestCase):
  ARGS = [
    Arg('device_index', int, 'Index of video device. '
        '(-1 to auto pick video device by OpenCV).', default=-1, optional=True),
    Arg('mock_mode', bool, 'Mock mode allows testing without a fixture.',
        default=False, optional=True),
    Arg('test_type', str, 'Describes the test type. '
        'Currently, only "calibration" is supported.'),
    Arg('test_chart_version', str, 'Version of the test chart.'),
    Arg('capture_resolution', tuple, 'A tuple (x-res, y-res) indicating the '
        'image capture resolution to use.'),
    Arg('resize_ratio', float, 'The resize ratio of the captured image.',
        default=1.0, optional=True),
    Arg('calibration_shift', float, 'Max image shift allowed '
        'during calibration.', default=0.002, optional=True),
    Arg('calibration_tilt', float, 'Max image tilt allowed '
        'during calibration.', default=0.05, optional=True),
  ]

  # self.args.test_type => light_chamber.TestType
  TEST_TYPES = {
    'calibration': TestType.CALI
  }

  # CSS style classes defined in the corresponding HTML file.
  STYLE_INFO = "color_idle"
  STYLE_PASS = "color_good"
  STYLE_FAIL = "color_bad"

  # Internal events.
  Event = Enum(['EXIT_TEST'])

  def __init__(self, *args, **kwargs):
    super(CameraFixture, self).__init__(*args, **kwargs)
    self.ui = None
    self.template = None
    self.ui_thread = None
    self.chamber = None
    self.internal_queue = Queue.Queue()

  def setUp(self):
    os.chdir(os.path.join(os.path.dirname(__file__), '%s_static' %
                          self.test_info.pytest_name)) # pylint: disable=E1101

    self.test_type = CameraFixture.TEST_TYPES[self.args.test_type]
    self.chamber = LightChamber(self.test_type, self.args.test_chart_version,
                                self.args.mock_mode, self.args.device_index,
                                self.args.capture_resolution)
    self.ui = test_ui.UI()
    self.ui.AddEventHandler('exit_test_button_clicked',
        lambda _: self.PostInternalQueue(self.Event.EXIT_TEST))

  def runTest(self):
    self.ui.Run(blocking=False)

    if self.test_type == TestType.CALI:
      self.Calibration()

  def Calibration(self):
    """Main routine for camera fixture calibration."""
    self.ui.CallJSFunction('InitForCalibration')

    ref_data = camperf.PrepareTest(self.chamber.GetTestChartFile())
    CALIBRATION_DEFAULT_CONFIG['max_image_shift'] = self.args.calibration_shift
    CALIBRATION_DEFAULT_CONFIG['max_image_tilt'] = self.args.calibration_tilt
    frame_delay = 1.0 / CALIBRATION_FPS

    self.chamber.EnableCamera()
    try:
      while True:
        img = self.chamber.ReadSingleFrame()
        gray_img = cv2.cvtColor(img, cv.CV_BGR2GRAY)
        success, tar_data = camperf.CheckVisualCorrectness(
            gray_img, ref_data, corner_only=True, **CALIBRATION_DEFAULT_CONFIG)

        renderer.DrawVC(img, success, tar_data)
        self.UpdateDisplayedImage(img, 'calibration_image')

        # Logs Visual-Correctness results to factory.log in case when external
        # display is unavailable.
        log_msg = 'PASS: ' if success else 'FAIL: '
        if hasattr(tar_data, 'shift'):
          log_msg += ("Shift=%.3f (%.01f, %0.01f) " % (
              tar_data.shift, tar_data.v_shift[0], tar_data.v_shift[1]))
          log_msg += ("Tilt=%0.2f" % tar_data.tilt)
        else:
          log_msg += 'Incorrect Chart'
        # TODO(jchuang): add subroutine to update displayed text.
        label = test_ui.MakeLabel(en=log_msg, css_class=(
            self.STYLE_PASS if success else self.STYLE_FAIL))
        self.ui.CallJSFunction("UpdateTestStatus", label)
        logging.info(log_msg)

        if self.PopInternalQueue(False) == self.Event.EXIT_TEST:
          if not success:
            self.ui.Fail('Failed to meet the calibration criteria.')
          break

        time.sleep(frame_delay)
    finally:
      self.chamber.DisableCamera()

  def PostInternalQueue(self, event):
    """Posts an event to internal queue."""
    self.internal_queue.put(event)

  def PopInternalQueue(self, wait):
    """Pops an event from internal queue.

    Args:
      wait: A bool flag to wait forever until internal queue has something.

    Returns:
      The first event in internal queue. None if 'wait' is set and internal
      queue is empty.
    """
    if wait:
      return self.internal_queue.get(block=True, timeout=None)
    else:
      try:
        return self.internal_queue.get_nowait()
      except Queue.Empty:
        return None

  def UpdateDisplayedImage(self, img, html_id):
    """Update displayed image.

    Args:
      img: OpenCV image object.
      html_id: Image ID in HTML.
    """
    resized_img = cv2.resize(img, None, fx=self.args.resize_ratio,
                      fy=self.args.resize_ratio, interpolation=cv2.INTER_AREA)
    data = base64.b64encode(EncodeCVImage(resized_img, '.jpg'))
    data_len = len(data)

    # Send the data in smaller packets due to event message size limit.
    try:
      self.ui.CallJSFunction('ClearImageData', '')
      p = 0
      while p < data_len:
        if p + MAX_MESSAGE_SIZE >= data_len:
          self.ui.CallJSFunction("AddImageData", data[p:data_len])
          p = data_len
        else:
          self.ui.CallJSFunction("AddImageData", data[p:p+MAX_MESSAGE_SIZE])
          p += MAX_MESSAGE_SIZE
      self.ui.CallJSFunction('UpdateImage', html_id)
    except AttributeError:
      # The websocket is closed because test has passed/failed.
      pass
