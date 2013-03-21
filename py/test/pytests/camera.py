# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

try:
  import cv   # pylint: disable=F0401
  import cv2  # pylint: disable=F0401
except ImportError:
  pass

import glob
import random
import re
import time
import tempfile
import unittest

from cros.factory.test import factory_task
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection
from cros.factory.test.utils import StartDaemonThread

_MSG_CAMERA_MANUAL_TEST = test_ui.MakeLabel(
    'Press ENTER to pass or ESC to fail.',
    zh='摄像头运作正常请按 ENTER，不正常请按 ESC',
    css_class='camera-test-info')
_MSG_CAMERA_TIMEOUT_TEST = test_ui.MakeLabel(
    'Running the camera until timeout.',
    zh='运行相机直到超时',
    css_class='camera-test-info')
_MSG_CAMERA_FACIAL_RECOGNITION = test_ui.MakeLabel(
    'Detecting faces...',
    zh='侦测人脸中...',
    css_class='camera-test-info')
_MSG_LED_TEST = test_ui.MakeLabel(
    'Press 0 if LED is flickering, 1 if LED is constantly lit,'
    '<br/>or ESC to fail.',
    zh='LED 闪烁请按 0，一直亮着请按 1，没亮请按 ESC',
    css_class='camera-test-info')
_MSG_TIME_REMAINING = lambda t: test_ui.MakeLabel(
    'Time remaining: %d' % t, u'剩余时间：%d' % t, 'camera-test-info')

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
    function hideImage() {
      var element = $("%(image)s");
      if (element) {
        element.style.display = "none";
      }
    }
""" % {'image': _ID_IMAGE}
_CSS_CAMERA_TEST = '.camera-test-info { font-size: 2em; }'

# Set JPEG image compression quality to 70 so that the image can be transferred
# through websocket.
_JPEG_QUALITY = 70
_HAAR_CASCADE_PATH = (
    '/usr/local/share/opencv/haarcascades/haarcascade_frontalface_default.xml')


class CaptureTask(factory_task.InteractiveFactoryTask):
  """Test task to test camera image capture functionality. It has 3 operating
  modes, which can be adjusted through CameraTest dargs:
  1. Automatically detect faces to pass the test, or
  2. Let operator manually select whether camera capture function is working or
     not.
  3. Run for a specified amount of time, pass if there are no errors.

  Args:
    camera_test: The main CameraTest object.
  """
  def __init__(self, camera_test):
    super(CaptureTask, self).__init__(camera_test.ui)
    self.camera_test = camera_test
    self.args = camera_test.args
    self.finished = False
    self.img_buffer = tempfile.NamedTemporaryFile(suffix='.jpg', delete=True)

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

  def TestCapture(self):
    detected_frame_count = 0
    tick = 1.0 / float(self.args.capture_fps)
    tock = time.time()
    process_interval = 1.0 / float(self.args.process_rate)
    resize_ratio = self.args.resize_ratio
    while not self.finished:
      ret, cv_img = self.camera_test.camera_device.read()
      if not ret:
        raise IOError('Error while capturing. Camera disconnected?')
      cv_img = cv2.resize(cv_img, None, fx=resize_ratio, fy=resize_ratio,
                          interpolation=cv2.INTER_AREA)
      cv_img = cv2.flip(cv_img, 1)
      if (self.args.face_recognition) and (
          time.time() - tock > process_interval):
        # Doing face recognition based on process_rate due to performance
        # consideration.
        tock = time.time()
        if self.DetectFaces(cv_img):
          detected_frame_count += 1
          if detected_frame_count > self.args.num_frames_to_pass:
            self.Pass()
            return
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

  def Init(self):
    if self.args.face_recognition:
      self.camera_test.ui.SetHTML(_MSG_CAMERA_FACIAL_RECOGNITION, id=_ID_PROMPT)
    elif self.args.timeout_run:
      self.camera_test.ui.SetHTML(_MSG_CAMERA_TIMEOUT_TEST, id=_ID_PROMPT)
    else:
      self.camera_test.ui.SetHTML(_MSG_CAMERA_MANUAL_TEST, id=_ID_PROMPT)
      self.BindPassFailKeys()
    self.camera_test.EnableCamera()

  def Cleanup(self):
    self.camera_test.ui.CallJSFunction('hideImage')
    self.finished = True

  def Run(self):
    self.Init()
    StartDaemonThread(target=self.TestCapture)


class LEDTask(factory_task.InteractiveFactoryTask):
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
        if self.camera_test.camera_device.isOpened():
          self.camera_test.DisableCamera()
        else:
          self.camera_test.EnableCamera()
          self.camera_test.camera_device.read()
      else:
        # Constantly lights the LED
        if not self.camera_test.camera_device.isOpened():
          self.camera_test.EnableCamera()
        self.camera_test.camera_device.read()
      time.sleep(0.5)

  def Init(self):
    self.camera_test.ui.SetHTML(_MSG_LED_TEST, id=_ID_PROMPT)
    self.BindPassFailKeys(pass_key=False)
    self.BindDigitKeys(self.pass_key)

  def Cleanup(self):
    self.finished = True
    self.UnbindDigitKeys()

  def Run(self):
    self.Init()
    StartDaemonThread(target=self.TestLED)


class CameraTest(unittest.TestCase):
  """Main class for camera test."""
  ARGS = [
    Arg('face_recognition', bool, 'Use face recognition to test camera.',
        default=True),
    Arg('num_frames_to_pass', int, 'The number of frames with faces '
        'presented to pass the test.', default=10),
    Arg('process_rate', (int, float), 'The process rate of face recognition '
        'calculation in times per second.', default=5),
    Arg('capture_fps', int, 'Camera capture rate in frames per second.',
        default=30),
    Arg('timeout_secs', int, 'Timeout value for the test.', default=20),
    Arg('capture_resolution', tuple, 'A tuple (x-res, y-res) indicating the '
        'image capture resolution to use.', default=(1280, 720)),
    Arg('resize_ratio', float, 'The resize ratio of the captured image.',
        default=0.4),
    Arg('timeout_run', bool, 'Just run the camera for timeout_secs.',
        default=False),
    Arg('show_image', bool, 'Whether to actually show the image.',
        default=True),
  ]

  def EnableCamera(self):
    # Search for the camera device in sysfs. On some boards OpenCV fails to
    # determine the device index automatically.
    uvc_vid_dirs = glob.glob(
        '/sys/bus/usb/drivers/uvcvideo/*/video4linux/video*')
    dev_index = None
    if len(uvc_vid_dirs) != 1:
      raise IOError('Multiple video capture interface found')
    for uvc_dir_entry in uvc_vid_dirs:
      dev_index = int(re.search(r'video([0-9]+)$', uvc_dir_entry).group(1))
    if dev_index is not None:
      self.camera_device = cv2.VideoCapture(dev_index)
    if not self.camera_device.isOpened():
      raise IOError('Unable to open video capture interface')
    # Set camera capture to HD resolution.
    x_res, y_res = self.args.capture_resolution
    self.camera_device.set(cv.CV_CAP_PROP_FRAME_WIDTH, x_res)
    self.camera_device.set(cv.CV_CAP_PROP_FRAME_HEIGHT, y_res)

  def DisableCamera(self):
    if not self.camera_device.isOpened():
      return
    self.camera_device.release()

  def CountdownTimer(self):
    """Starts countdown timer and fails the test if timer reaches zero,
    unless in timeout_run mode, than it just passes."""
    time_remaining = self.args.timeout_secs
    while time_remaining > 0:
      self.ui.SetHTML(_MSG_TIME_REMAINING(time_remaining),
                      id=_ID_COUNTDOWN_TIMER)
      time.sleep(1)
      time_remaining -= 1
    if self.args.timeout_run:
      self.ui.Pass()
    else:
      self.ui.Fail('Camera test failed due to timeout.')

  def setUp(self):
    self.camera_device = None
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_CSS_CAMERA_TEST)
    self.template.SetState(_HTML_CAMERA_TEST)
    self.ui.RunJS(_JS_CAMERA_TEST)
    if self.args.timeout_run:
      self.task_list = [CaptureTask(self)]
    else:
      self.task_list = [CaptureTask(self), LEDTask(self)]
    self.task_manager = factory_task.FactoryTaskManager(self.ui, self.task_list)
    StartDaemonThread(target=self.CountdownTimer)

  def runTest(self):
    self.task_manager.Run()
