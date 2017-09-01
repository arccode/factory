# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Fixtureless camera test.

This test supports combinations of one or multiple choices from these five test
types:

  (A) do_QR_scan
  (B) do_facial_recognition
  (C) do_capture_timeout
  (D) do_capture_manual
  (E) do_led_manual

(A), (B) and (C) do not requires intervention of operator. It passes or fails
automatically.

(D) and (E) requires operator to judge test passing / failing manually. Note
that it may yield false positivity.

Usage examples::

  # Manual capture test + manual LED test (the typical use case).
  OperatorTest(
      id='CameraManual',
      pytest_name='camera',
      dargs={
          'do_capture_manual': True,
          'do_led_manual': True,
          'resize_ratio': 0.4,
          'camera_args':{'resolution': (1920, 1280)}})

  # Automatic QR scan test + manual capture test + manual LED test.
  OperatorTest(
      id='CameraQR',
      pytest_name='camera',
      dargs={
          'do_QR_scan': True,
          'do_capture_manual': True,
          'do_led_manual': True,
          'resize_ratio': 0.4,
          'camera_args':{'resolution': (1920, 1280)}})

  # Automatic facial recognition test + manual LED test.
  OperatorTest(
      id='CameraFacial',
      pytest_name='camera',
      dargs={
          'do_facial_recognition': True,
          'do_led_manual': True,
          'resize_ratio': 0.4,
          'camera_args':{'resolution': (1920, 1280)}})

  # Stress camera capturing until timeout without UI.
  FactoryTest(
      id='CameraTimeout',
      pytest_name='camera',
      dargs={
          'do_capture_timeout': True,
          'timeout_secs': 1000,
          'show_image': False,
          'camera_args':{'resolution': (1920, 1280)}})

  # Stress camera capturing until given number of frames captured.
  FactoryTest(
      id='CameraCount',
      pytest_name='camera',
      dargs={
          'do_capture_frame_count': True,
          'num_frames_to_pass': 100,
          'timeout_secs': 1000,
          'show_image': False,
          'camera_args':{'resolution': (1920, 1280)}})

"""


import random
import tempfile
import threading
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.fixture.camera import barcode
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_task
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils

from cros.factory.external import cv
from cros.factory.external import cv2


_MSG_CAMERA_MANUAL_CAPTURE = i18n_test_ui.MakeI18nLabelWithClass(
    'Capturing image...', 'camera-test-info')
_MSG_CAMERA_MANUAL_TEST = i18n_test_ui.MakeI18nLabelWithClass(
    'Press ENTER to pass or ESC to fail.', 'camera-test-info')
_MSG_CAMERA_TIMEOUT_TEST = i18n_test_ui.MakeI18nLabelWithClass(
    'Running the camera until timeout.', 'camera-test-info')
_MSG_CAMERA_FRAME_COUNT_TEST = i18n_test_ui.MakeI18nLabelWithClass(
    'Running the camera until expected number of frames captured.',
    'camera-test-info')
_MSG_CAMERA_QR_SCAN = i18n_test_ui.MakeI18nLabelWithClass(
    'Scanning QR code...', 'camera-test-info')
_MSG_CAMERA_QR_FOUND_STRING = lambda text: i18n_test_ui.MakeI18nLabelWithClass(
    'Scanned QR code: "{text}"', 'camera-test-info', text=text)
_MSG_CAMERA_FACIAL_RECOGNITION = i18n_test_ui.MakeI18nLabelWithClass(
    'Detecting faces...', 'camera-test-info')
_MSG_LED_TEST = i18n_test_ui.MakeI18nLabelWithClass(
    'Press 0 if LED is flickering, 1 if LED is constantly lit,'
    '<br>or ESC to fail.', 'camera-test-info')
_MSG_TIME_REMAINING = lambda time: i18n_test_ui.MakeI18nLabelWithClass(
    'Time remaining: {time}', 'camera-test-info', time=time)

_ID_IMAGE = 'camera-test-image'
_ID_PROMPT = 'camera-test-prompt'
_ID_COUNTDOWN_TIMER = 'camera-test-timer'
_HTML_CAMERA_TEST = """
    <img id="%(image)s"/>
    <div id="%(prompt)s"></div>
    <div id="%(timer)s"></div>
""" % {'image': _ID_IMAGE, 'prompt': _ID_PROMPT, 'timer': _ID_COUNTDOWN_TIMER}
_JS_CAMERA_TEST = """
    function showJpegImage(jpeg_binary) {
      var element = $("%(image)s");
      if (element) {
        element.src = "data:image/jpeg;base64," + jpeg_binary;
      }
    }
    function hideImage(hide) {
      var element = $("%(image)s");
      if (element) {
        element.style.display = hide ? 'none' : '';
      }
    }
""" % {'image': _ID_IMAGE}
_CSS_CAMERA_TEST = '.camera-test-info { font-size: 2em; }'

# Set JPEG image compression quality to 70 so that the image can be transferred
# through websocket.
_JPEG_QUALITY = 70
_HAAR_CASCADE_PATH = (
    '/usr/local/share/opencv/haarcascades/haarcascade_frontalface_default.xml')

# Test types of capture task.
CaptureTaskType = type_utils.Enum(
    ['QR', 'FACE', 'TIMEOUT', 'MANUAL', 'FRAME_COUNT'])


class CaptureTask(test_task.InteractiveTestTask):
  """Test task to test camera image capture functionality. It has 3 operating
  modes, which can be adjusted through CameraTest dargs:
  1. Automatically detect faces to pass the test, or
  2. Let operator manually select whether camera capture function is working or
     not.
  3. Run for a specified amount of time, pass if there are no errors.

  Args:
    camera_test: The main CameraTest object.
    task_type: (CaptureTaskType enum) The test type of this capture task.
  """
  _CAPTURE_THREAD_NAME = 'TestCaptureThread'

  def __init__(self, camera_test, task_type):
    super(CaptureTask, self).__init__(camera_test.ui)
    self.camera_test = camera_test
    self.task_type = task_type
    self.args = camera_test.args
    self.finished = False
    self.img_buffer = tempfile.NamedTemporaryFile(suffix='.jpg', delete=True)
    self.capture_thread = None

  def DetectFaces(self, cv_image):
    storage = cv.CreateMemStorage()
    cascade = cv.Load(_HAAR_CASCADE_PATH)
    detected = cv.HaarDetectObjects(cv_image, cascade, storage, 1.2, 2,
                                    cv.CV_HAAR_DO_CANNY_PRUNING, (20, 20))
    if detected:
      for loc, _ in detected:
        x, y, w, h = loc
        cv.Rectangle(cv_image, (x, y), (x + w, y + h), 255)
    return detected != []

  def ScanQRCode(self, cv_image):
    scan_results = barcode.ScanQRCode(cv_image)
    if len(scan_results) > 0:
      scanned_text = scan_results[0]
    else:
      scanned_text = None
    if scanned_text:
      self.camera_test.ui.SetHTML(_MSG_CAMERA_QR_FOUND_STRING(scanned_text),
                                  id=_ID_PROMPT)
    return scanned_text == self.args.QR_string

  def TestCapture(self):
    frame_count = 0
    detected_frame_count = 0
    tick = 1.0 / float(self.args.capture_fps)
    tock = time.time()
    process_interval = 1.0 / float(self.args.process_rate)
    resize_ratio = self.args.resize_ratio
    if self.task_type == CaptureTaskType.MANUAL:
      self.camera_test.ui.SetHTML(_MSG_CAMERA_MANUAL_TEST, id=_ID_PROMPT)
      self.BindPassFailKeys()
    while not self.finished:
      cv_img = self.camera_test.camera_device.ReadSingleFrame()
      if self.task_type == CaptureTaskType.FRAME_COUNT:
        frame_count += 1
        if frame_count >= self.args.num_frames_to_pass:
          self.Pass()
          return
      if (self.task_type in [CaptureTaskType.QR, CaptureTaskType.FACE] and
          time.time() - tock > process_interval):
        # Doing face recognition based on process_rate due to performance
        # consideration.
        tock = time.time()
        if ((self.task_type == CaptureTaskType.QR and
             self.ScanQRCode(cv_img)) or
            (self.task_type == CaptureTaskType.FACE and
             self.DetectFaces(cv_img))):
          detected_frame_count += 1
        if detected_frame_count >= self.args.num_frames_to_pass:
          self.Pass()
          return
      cv_img = cv2.resize(cv_img, None, fx=resize_ratio, fy=resize_ratio,
                          interpolation=cv2.INTER_AREA)
      cv_img = cv2.flip(cv_img, 1)

      self.img_buffer.seek(0)
      cv2.imwrite(self.img_buffer.name, cv_img,
                  (cv.CV_IMWRITE_JPEG_QUALITY, _JPEG_QUALITY))
      if self.args.show_image:
        try:
          self.camera_test.ui.CallJSFunction(
              'showJpegImage',
              self.img_buffer.read().encode('base64'))
        except AttributeError:
          # The websocket is closed because test has passed/failed.
          return
      time.sleep(tick)

  def Run(self):
    if self.task_type == CaptureTaskType.QR:
      self.camera_test.ui.SetHTML(_MSG_CAMERA_QR_SCAN, id=_ID_PROMPT)
    elif self.task_type == CaptureTaskType.FACE:
      self.camera_test.ui.SetHTML(_MSG_CAMERA_FACIAL_RECOGNITION, id=_ID_PROMPT)
    elif self.task_type == CaptureTaskType.TIMEOUT:
      self.camera_test.ui.SetHTML(_MSG_CAMERA_TIMEOUT_TEST, id=_ID_PROMPT)
    elif self.task_type == CaptureTaskType.FRAME_COUNT:
      self.camera_test.ui.SetHTML(_MSG_CAMERA_FRAME_COUNT_TEST, id=_ID_PROMPT)
    else:
      self.camera_test.ui.SetHTML(_MSG_CAMERA_MANUAL_CAPTURE, id=_ID_PROMPT)

    self.camera_test.ui.CallJSFunction('hideImage', False)
    self.camera_test.EnableDevice()
    self.capture_thread = process_utils.StartDaemonThread(
        target=self.TestCapture, name=self._CAPTURE_THREAD_NAME,
        interrupt_on_crash=True)

  def Cleanup(self):
    self.finished = True
    # If Cleanup() is called from capture thread, no need to join() it.
    if (self.capture_thread and
        threading.current_thread().name != self._CAPTURE_THREAD_NAME):
      self.capture_thread.join(1.0)
    self.camera_test.camera_device.DisableCamera()


class LEDTask(test_task.InteractiveTestTask):
  """Test task to test camera LED.

  Args:
    camera_test: The main CameraTest object.
  """
  LED_FLICKERING = 0
  LED_CONSTANTLY_LIT = 1

  def __init__(self, camera_test):
    super(LEDTask, self).__init__(camera_test.ui)
    self.camera_test = camera_test
    self.pass_key = random.randint(self.LED_FLICKERING, self.LED_CONSTANTLY_LIT)
    self.finished = False

  def TestLED(self):
    while not self.finished:
      if self.pass_key == self.LED_FLICKERING:
        # Flickers the LED
        if self.camera_test.camera_device.IsEnabled():
          self.camera_test.camera_device.DisableCamera()
        else:
          self.camera_test.EnableDevice()
          self.camera_test.camera_device.ReadSingleFrame()
      else:
        # Constantly lights the LED
        if not self.camera_test.camera_device.IsEnabled():
          self.camera_test.EnableDevice()
        self.camera_test.camera_device.ReadSingleFrame()
      time.sleep(0.5)

  def Run(self):
    self.camera_test.ui.SetHTML(_MSG_LED_TEST, id=_ID_PROMPT)
    self.camera_test.ui.CallJSFunction('hideImage', True)
    self.BindPassFailKeys(pass_key=False)
    self.BindDigitKeys(self.pass_key, max_digit=1)
    process_utils.StartDaemonThread(target=self.TestLED,
                                    interrupt_on_crash=True)

  def Cleanup(self):
    self.finished = True
    self.UnbindDigitKeys()


class CameraTest(unittest.TestCase):
  """Main class for camera test."""
  ARGS = [
      Arg('do_QR_scan', bool, 'Automates camera check by scanning QR Code.',
          default=False),
      Arg('do_facial_recognition', bool,
          'Automates camera check by using '
          'face recognition.', default=False),
      Arg('do_capture_timeout', bool,
          'Just run camera capturing for '
          "'timeout_secs' without manual intervention of operator. "
          'This is usually used in run-in stress test. ', default=False),
      Arg('do_capture_manual', bool,
          'Manually checks if camera capturing is '
          'working.', default=False),
      Arg('do_capture_frame_count', bool,
          'Just run camera capturing for a given number of frames.',
          default=False),
      Arg('do_led_manual', bool, 'Manully tests LED on camera.',
          default=False),
      Arg('num_frames_to_pass', int,
          'The number of frames with faces, QR code presented or any frames '
          'when do_capture_frame_count to pass the test.', default=10),
      Arg('process_rate', (int, float),
          'The process rate of face recognition or '
          'QR code scanning in times per second.', default=5),
      Arg('QR_string', str, 'Encoded string in QR code.',
          default='Hello ChromeOS!'),
      Arg('capture_fps', (int, float),
          'Camera capture rate in frames per second.', default=30),
      Arg('timeout_secs', int, 'Timeout value for the test.', default=20),
      Arg('resize_ratio', float,
          'The resize ratio of captured image '
          'on screen.', default=0.4),
      Arg('show_image', bool,
          'Whether to actually show the image on screen.', default=True),
      Arg('device_index', int, 'Index of video device (0 for default).',
          default=0),
      Arg('camera_args', dict, 'Dict of args used for enabling the camera '
          'device.', optional=True)]

  def _CountdownTimer(self):
    """Starts countdown timer and fails the test if timer reaches zero,
    unless in timeout_run mode, than it just passes."""
    end_time = time.time() + self.args.timeout_secs
    while True:
      remaining_time = end_time - time.time()
      if remaining_time <= 0:
        break
      self.ui.SetHTML(_MSG_TIME_REMAINING(remaining_time),
                      id=_ID_COUNTDOWN_TIMER)
      time.sleep(1)

    if self.args.do_capture_timeout:
      # If it keeps capturing images until timeout, the test passes.
      self.ui.Pass()
    else:
      self.ui.Fail('Camera test failed due to timeout.')

  def EnableDevice(self):
    if self.args.camera_args:
      self.camera_device.EnableCamera(**self.args.camera_args)
    else:
      self.camera_device.EnableCamera()

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.camera_device = self.dut.camera.GetCameraDevice(
        self.args.device_index)

    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_CSS_CAMERA_TEST)
    self.template.SetState(_HTML_CAMERA_TEST)
    self.ui.RunJS(_JS_CAMERA_TEST)

    exclusive_check = False
    self.task_list = []
    if self.args.do_QR_scan:
      self.task_list.append(CaptureTask(self, CaptureTaskType.QR))
    if self.args.do_facial_recognition:
      self.task_list.append(CaptureTask(self, CaptureTaskType.FACE))
    if self.args.do_capture_timeout:
      self.task_list.append(CaptureTask(self, CaptureTaskType.TIMEOUT))
      exclusive_check = True
    if self.args.do_capture_frame_count:
      self.task_list.append(CaptureTask(self, CaptureTaskType.FRAME_COUNT))
      exclusive_check = True
    if self.args.do_capture_manual:
      self.task_list.append(CaptureTask(self, CaptureTaskType.MANUAL))
    if self.args.do_led_manual:
      self.task_list.append(LEDTask(self))
    if exclusive_check and len(self.task_list) > 1:
      raise ValueError('do_capture_timeout or do_capture_frame_count '
                       'can not coexist with other test types')
    if not self.task_list:
      raise ValueError('must choose at least one test type')

    self.task_manager = test_task.TestTaskManager(self.ui, self.task_list)
    process_utils.StartDaemonThread(target=self._CountdownTimer,
                                    interrupt_on_crash=True)

  def runTest(self):
    self.task_manager.Run()
