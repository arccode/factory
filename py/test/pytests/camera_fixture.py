# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Camera fixture test.

Fixture types:
  - FullChamber: light chamber for full-assembly line in FATP and RMA.
  - ABChamber: light chamber for AB sub-assembly line (after A and B panels are
               assembled).
  - ModuleChamber: light chamber for module-level OQC, IQC, production QC.
  - LightPanel: light panel for standalone lens shading test.

Test types:
  When fixture_type == {Full|AB|Module}Chamber:
    - Calibration: calibrates light chamber and test chart to align with the
                   golden sample (only checking image shift and tilt).
    - IQ: checks IQ factors such as MTF (sharpness), lens shading, image shift,
          and image tilt in one test.
    - IQ_ALS: checks IQ factors + ALS calibration.

  When fixture_type == LightPanel
    - LensShading: checks lens shading ratio (usually fails when camera module
                   is not precisely aligned with the view hole on bezel).

Test chart versions:
    - A: 7x11 blocks. Used for 720p camera or similar aspect ratio.
    - B: 7x9 blocks. Used for VGA camera or similar aspect ratio.
    - White: All white. Used for standalone lens shading test.

Remarks: This pytests code only supports Camera and LensShading now, the
remaining functionality are implemented in autotest-based
factory_CameraPerformanceAls.py.

Usage Examples:

# Fixture calibration for FATP line.
OperatorTest(
  id='CameraFixtureCalibration',
  pytest_name='camera_fixture',
  dargs={
    'mock_mode': False,
    'test_type': 'Calibration',
    'fixture_type': 'FullChamber',
    'test_chart_version': 'B',
    'capture_resolution': (640, 480),
    'resize_ratio': 0.7,
    'calibration_shift': 0.003,
    'calibration_tilt': 0.25})

# Standalone lens shading check.
OperatorTest(
  id='LensShading',
  pytest_name='camera_fixture',
  dargs={
    'mock_mode': False,
    'test_type': 'LensShading',
    'fixture_type': 'LightPanel',
    'test_chart_version': 'White',
    'capture_resolution': (640, 480),
    'resize_ratio': 0.7,
    'lens_shading_ratio': 0.30})

"""

import base64
try:
  import cv2  # pylint: disable=F0401
except ImportError:
  pass
import logging
import os
import Queue
import time
import unittest

from cros.factory.event_log import Log
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.fixture.camera.camera_utils import EncodeCVImage
from cros.factory.test.fixture.camera.light_chamber import LightChamber
import cros.factory.test.fixture.camera.perf_tester as camperf
import cros.factory.test.fixture.camera.renderer as renderer
from cros.factory.test.utils import Enum


# Delay between each frame during calibration.
CALIBRATION_FPS = 15

# Delay between each frame during lens shading test.
LENS_SHADING_FPS = 5

# TODO(jchuang): import from event.py
MAX_MESSAGE_SIZE = 60000

TestType = Enum(['CALI', 'LS'])

Fixture = Enum(['FULL', 'AB', 'MODULE', 'PANEL'])

class CameraFixture(unittest.TestCase):
  ARGS = [
    Arg('test_type', str, 'What to test. '
        'Supported types: Calibration, LensShading.'),
    Arg('fixture_type', str, 'Type of the light chamber/panel. '
        'Supported types: FullChamber, ABChamber, ModuleChamber, '
        'LightPanel.'),
    Arg('test_chart_version', str, 'Version of the test chart. '
        'Supported types: A, B, White'),
    Arg('mock_mode', bool, 'Mock mode allows testing without a fixture.',
        default=False),
    Arg('device_index', int, 'Index of camera video device. '
        '(-1 to auto pick video device by OpenCV).', default=-1),
    Arg('capture_resolution', tuple, 'A tuple (x-res, y-res) indicating the '
        'image capture resolution to use.'),
    Arg('resize_ratio', float, 'The resize ratio of the captured image '
        'displayed on preview.', default=1.0),
    Arg('calibration_shift', float, 'Max image shift allowed '
        'when test_type="Calibration".', default=0.002),
    Arg('calibration_tilt', float, 'Max image tilt allowed '
        'when test_type="Calibration".', default=0.05),
    Arg('lens_shading_ratio', float, 'Max len shading ratio allowed '
        'when test_type="LensShading".', default=0.20),
    Arg('lens_shading_timeout_secs', int, 'Timeout in seconds '
        'when test_type="LensShading".', default=20),
  ]

  # self.args.test_type => TestType
  TEST_TYPES = {
    'Calibration': TestType.CALI,
    'LensShading': TestType.LS
  }

  # self.args.fixture_type => Fixture
  FIXTURE_TYPES = {
    'FullChamber': Fixture.FULL,
    'ABChamber': Fixture.AB,
    'ModuleChamber': Fixture.MODULE,
    'LightPanel': Fixture.PANEL
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
    self.fixture_type = CameraFixture.FIXTURE_TYPES[self.args.fixture_type]

    self.chamber = LightChamber(test_chart_version=self.args.test_chart_version,
                                mock_mode=self.args.mock_mode,
                                device_index=self.args.device_index,
                                image_resolution=self.args.capture_resolution)
    self.ui = test_ui.UI()
    self.ui.AddEventHandler('exit_test_button_clicked',
        lambda _: self.PostInternalQueue(self.Event.EXIT_TEST))

  def runTest(self):
    self.ui.Run(blocking=False)

    if self.test_type == TestType.CALI:
      self.RunCalibration()
    elif self.test_type == TestType.LS:
      self.RunLensShading()

  def RunCalibration(self):
    """Main routine for camera fixture calibration.

    The test keeps reading images from camera and updating preview on
    screen. For each frame, it checks the image shift and image tilt.

    If the shift and tilt meet the criteria, it will prompt PASS. Then user can
    click 'Exit Test' button.  Otherwise, it prompts FAIL, and user needs to
    rotate and move the test chart to align it with the golden sample camera.

    """
    self.ui.CallJSFunction('InitForCalibration')

    ref_data = camperf.PrepareTest(self.chamber.GetTestChartFile())
    frame_delay = 1.0 / CALIBRATION_FPS

    self.chamber.EnableCamera()
    try:
      while True:
        img, gray_img = self.chamber.ReadSingleFrame()
        success, tar_data = camperf.CheckVisualCorrectness(
            sample=gray_img, ref_data=ref_data,
            max_image_shift=self.args.calibration_shift,
            max_image_tilt=self.args.calibration_tilt,
            corner_only=True)

        renderer.DrawVC(img, success, tar_data)
        self.UpdateDisplayedImage(img, 'preview_image')

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

  def RunLensShading(self):
    """Main routine for standalone lens shading test.

    The test keeps reading images from camera and updating preview on screen. If
    it checks lens shading correctly on a single frame, it will exit the test
    successfully. Otherwise, it will prompt FAIL.

    During the test, user should move a light panel or light mask with uniform
    lighting in front of the camera on DUT. If the test doesn't pass before
    timeout, it will also fail.

    Upon finished, it logs 'lens_shading_ratio' in event
    'camera_fixture_lens_shading'.

    """
    self.ui.CallJSFunction('InitForLensShading')

    frame_delay = 1.0 / LENS_SHADING_FPS
    end_time = time.time() + self.args.lens_shading_timeout_secs

    self.chamber.EnableCamera()
    try:
      while True:
        remaining_time = end_time - time.time()

        img, gray_img = self.chamber.ReadSingleFrame()

        self.UpdateDisplayedImage(img, 'preview_image')

        success, tar_ls = camperf.CheckLensShading(
            sample=gray_img, max_shading_ratio=self.args.lens_shading_ratio,
            check_low_freq=False)
        ls_ratio = float(1.0 - tar_ls.lowest_ratio)

        log_msg = 'PASS: ' if success else 'FAIL: '
        log_msg += "Remaining %d s. Shading ratio=%.3f " % (
            remaining_time, ls_ratio)
        label = test_ui.MakeLabel(en=log_msg, css_class=(
            self.STYLE_PASS if success else self.STYLE_FAIL))
        self.ui.CallJSFunction("UpdateTestStatus", label)

        if (remaining_time <= 0 or success or
            self.PopInternalQueue(False) == self.Event.EXIT_TEST):
          Log('camera_fixture_lens_shading', lens_shading_ratio=ls_ratio)
          if not success:
            self.ui.Fail(
                'Failed to meet the lens shading criteria with '
                'ratio=%f (> %f).' % (ls_ratio, self.args.lens_shading_ratio))
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
    resized_img = cv2.resize(
        img, None, fx=self.args.resize_ratio, fy=self.args.resize_ratio,
        interpolation=cv2.INTER_AREA)
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
