# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Fixtureless camera test.

Description
-----------
This pytest test if camera is working by one of the following method (choose
by argument ``mode``):

* ``'qr'``: Scan QR code of given string.

* ``'face'``: Recognize a human face.

* ``'timeout'``: Run camera capture until timeout.

* ``'frame_count'``: Run camera capture for specified frames.

* ``'manual'``: Show captured image.

* ``'manual_led'``: Light or blink camera LED.

``e2e_mode`` can be set to use Chrome Media API instead of device API.

Test Procedure
--------------
If ``e2e_mode`` is ``True``, the operator may be prompt to click on the 'Allow'
button on Chrome notification to give Chrome camera permission.

The test procedure differs for each different modes:

* ``'qr'``: Operator put a QR code with content specified by ``QR_string``.
  Test would pass automatically after ``num_frames_to_pass`` frames with QR code
  are captured.

* ``'face'``: Operator show a face to the camera. Test would pass automatically
  after ``num_frames_to_pass`` frames with detected face are captured.

* ``'timeout'``: No user interaction is required, the test pass after
  ``timeout_secs`` seconds.

* ``'frame_count'``: No user interaction is required, the test pass after
  ``num_frames_to_pass`` frames are captured.

* ``'manual'``: Screen would show the image captured by camera, and operator
  judge whether the image looks good. Note that this methods require judgement
  by operator, so may yield false positivity.

* ``'manual_led'``: The LED light of camera would either be constant on or
  blinking, and operator need to press the correct key to pass the test.

Except ``'timeout'`` mode, the test would fail after ``timeout_secs`` seconds.

Dependency
----------
End-to-end ``'qr'`` or ``'face'`` modes depend on OpenCV and numpy.

If not end-to-end mode, depend on OpenCV and device API
``cros.factory.device.camera``.

``'qr'`` mode also depends on library ``zbar``.

Examples
--------
To run a manual capture test. (The default case), add this in test list::

  {
    "pytest_name": "camera"
  }

To run QR scan test, and specify camera resolution to 1920 x 1080::

  {
    "pytest_name": "camera",
    "args": {
      "camera_args": {
        "resolution": [1920, 1280]
      },
      "mode": "qr"
    }
  }

To run facial recognition test, and use Chrome API instead of device API::

  {
    "pytest_name": "camera",
    "args": {
      "e2e_mode": true,
      "mode": "face"
    }
  }

To stress camera for 1000 seconds, and don't show the image::

  {
    "pytest_name": "camera",
    "args": {
      "mode": "timeout",
      "timeout_secs": 1000,
      "show_image": false
    }
  }

To stress camera capturing for 100 frames, have a timeout of 1000 seconds, and
don't show the image::

  {
    "pytest_name": "camera",
    "args": {
      "num_frames_to_pass": 100,
      "mode": "frame_count",
      "timeout_secs": 1000,
      "show_image": false
    }
  }
"""


import codecs
import numbers
import os
import queue
import random
import time
import uuid

from cros.factory.device import device_utils
from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test.utils import barcode
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils

from cros.factory.external import cv2 as cv
from cros.factory.external import numpy as np


# Set JPEG image compression quality to 70 so that the image can be transferred
# through websocket.
_JPEG_QUALITY = 70
_HAAR_CASCADE_PATH = (
    '/usr/local/share/opencv4/haarcascades/haarcascade_frontalface_default.xml')


TestModes = type_utils.Enum(['qr', 'face', 'timeout', 'frame_count', 'manual',
                             'manual_led'])


class CameraTest(test_case.TestCase):
  """Main class for camera test."""
  ARGS = [
      Arg('mode', TestModes,
          'The test mode to test camera.', default='manual'),
      Arg('num_frames_to_pass', int,
          'The number of frames with faces in mode "face", '
          'QR code presented in mode "qr", '
          'or any frames in mode "frame_count" to pass the test.', default=10),
      Arg('process_rate', numbers.Real,
          'The process rate of face recognition or '
          'QR code scanning in times per second.', default=5),
      Arg('QR_string', str, 'Encoded string in QR code.',
          default='Hello ChromeOS!'),
      Arg('capture_fps', numbers.Real,
          'Camera capture rate in frames per second.', default=30),
      Arg('timeout_secs', int, 'Timeout value for the test.', default=20),
      Arg('resize_ratio', float,
          'The resize ratio of captured image on screen.', default=0.4),
      Arg('show_image', bool,
          'Whether to actually show the image on screen.', default=True),
      Arg('e2e_mode', bool, 'Perform end-to-end test or not (for camera).',
          default=False),
      Arg('camera_facing', type_utils.Enum(['front', 'rear', None]),
          'String "front" or "rear" for the camera to test. '
          'If in normal mode, default is automatically searching one. '
          'If in e2e mode, default is "front".',
          default=None),
      Arg('flip_image', bool,
          'Whether to flip the image horizontally. This should be set to False'
          'for the rear facing camera so the displayed image looks correct.'
          'The default value is False if camera_facing is "rear", True '
          'otherwise.',
          default=None),
      Arg('camera_args', dict, 'Dict of args used for enabling the camera '
          'device. Only "resolution" is supported in e2e mode.', default={}),
      Arg('flicker_interval_secs', (int, float),
          'The flicker interval in seconds in manual_led mode', default=0.5)]

  def _Timeout(self):
    if self.mode == TestModes.timeout:
      # If it keeps capturing images until timeout, the test passes.
      self.PassTask()
    else:
      self.FailTask('Camera test failed due to timeout.')

  def ShowInstruction(self, msg):
    self.ui.CallJSFunction('showInstruction', msg)

  def _RunJSBlockingImpl(self, js, func):
    return_queue = queue.Queue()
    event_name = 'wait_js_%s_%s' % (func, uuid.uuid4())
    self.event_loop.AddEventHandler(
        event_name, lambda event: return_queue.put(event.data))
    self.ui.CallJSFunction(func, js, event_name)
    ret = sync_utils.QueueGet(return_queue)
    self.event_loop.RemoveEventHandler(event_name)
    if 'error' in ret:
      self.FailTask(ret['error'])
    return ret['data']

  # TODO(pihsun): Put this in test_ui.
  def RunJSBlocking(self, js):
    self._RunJSBlockingImpl(js, 'runJS')

  # TODO(pihsun): Put this in test_ui.
  def RunJSPromiseBlocking(self, js):
    return self._RunJSBlockingImpl(js, 'runJSPromise')

  def EnableDevice(self):
    if self.e2e_mode:
      self.RunJSPromiseBlocking('cameraTest.enable()')
    else:
      self.camera_device.EnableCamera(**self.args.camera_args)

  def DisableDevice(self):
    if self.e2e_mode:
      self.RunJSBlocking('cameraTest.disable()')
    else:
      self.camera_device.DisableCamera()

  def ReadSingleFrame(self):
    if self.e2e_mode:
      if self.need_transmit_from_ui:
        # TODO(pihsun): The shape detection API (face / barcode detection) are
        # not implemented on desktop Chrome yet. We don't need to transmit the
        # image back after these APIs are implemented, and can do all
        # postprocessing on JavaScript.
        blob_path = self.RunJSPromiseBlocking(
            'cameraTest.grabFrameAndTransmitBack()')
        blob = codecs.decode(
            file_utils.ReadFile(blob_path, encoding=None), 'base64')
        os.unlink(blob_path)
        return cv.imdecode(np.fromstring(blob, dtype=np.uint8), cv.IMREAD_COLOR)

      self.RunJSPromiseBlocking('cameraTest.grabFrame()')
      return None

    return self.camera_device.ReadSingleFrame()

  def LEDTest(self):
    flicker = bool(random.randint(0, 1))

    self.ui.BindStandardFailKeys()
    for i in range(2):
      if i == flicker:
        self.ui.BindKey(str(i), lambda unused_event: self.PassTask())
      else:
        self.ui.BindKey(
            str(i), lambda unused_event: self.FailTask('Wrong key pressed.'))
    self.ShowInstruction(
        _('Press 0 if LED is constantly lit, 1 if LED is flickering,\n'
          'or ESC to fail.'))
    self.ui.CallJSFunction('hideImage', True)

    if flicker:
      while True:
        # Flickers the LED
        self.EnableDevice()
        self.ReadSingleFrame()
        self.Sleep(self.args.flicker_interval_secs)
        self.DisableDevice()
        self.Sleep(self.args.flicker_interval_secs)
    else:
      # Constantly lights the LED
      self.EnableDevice()
      while True:
        self.ReadSingleFrame()
        self.Sleep(0.5)

  def DetectFaces(self, cv_image):
    # TODO(pihsun): Use the shape detection API in Chrome in e2e mode when it
    # is ready.
    cascade = cv.CascadeClassifier(_HAAR_CASCADE_PATH)
    detected_objs = cascade.detectMultiScale(
        cv_image,
        scaleFactor=1.2,
        minNeighbors=2,
        flags=cv.CASCADE_DO_CANNY_PRUNING,
        minSize=(20, 20))
    # pylint: disable=len-as-condition
    # Detected_objs will be numpy array or an empty tuple. bool(numpy_array)
    # will not work (will raise an exception).
    detected = len(detected_objs) > 0
    if detected:
      for x, y, w, h in detected_objs:
        cv.rectangle(cv_image, (x, y), (x + w, y + h), 255)
    return detected

  def ScanQRCode(self, cv_image):
    scanned_text = None

    # TODO(pihsun): Use the shape detection API in Chrome in e2e mode when it
    # is ready.
    scan_results = barcode.ScanQRCode(cv_image)
    if scan_results:
      scanned_text = scan_results[0]

    if scanned_text:
      self.ShowInstruction(
          i18n.StringFormat(_('Scanned QR code: "{text}"'), text=scanned_text))

    return scanned_text == self.args.QR_string

  def ShowImage(self, cv_image):
    resize_ratio = self.args.resize_ratio
    if self.e2e_mode and not self.need_transmit_to_ui:
      self.RunJSPromiseBlocking('cameraTest.showImage(%s)' % resize_ratio)
    else:
      cv_image = cv.resize(
          cv_image,
          None,
          fx=resize_ratio,
          fy=resize_ratio,
          interpolation=cv.INTER_AREA)

      if self.flip_image:
        cv_image = cv.flip(cv_image, 1)

      unused_retval, jpg_data = cv.imencode(
          '.jpg', cv_image, (cv.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY))
      jpg_base64 = codecs.encode(jpg_data.tobytes(), 'base64')

      try:
        # TODO(pihsun): Don't use CallJSFunction for transmitting image back
        # to UI. Use URLForData instead, since event server actually
        # broadcast to all client, and is not suitable for large amount of
        # data.
        self.ui.CallJSFunction(
            'showImage',
            'data:image/jpeg;base64,' + jpg_base64.decode('utf-8'))
      except AttributeError:
        # The websocket is closed because test has passed/failed.
        return

  def CaptureTest(self, mode):
    frame_count = 0
    detected_frame_count = 0
    tick = 1.0 / float(self.args.capture_fps)
    tock = time.time()
    process_interval = 1.0 / float(self.args.process_rate)

    instructions = {
        TestModes.manual:
            _('Press ENTER to pass or ESC to fail.'),
        TestModes.timeout:
            _('Running the camera until timeout.'),
        TestModes.frame_count:
            _('Running the camera until expected number of frames captured.'),
        TestModes.qr:
            _('Scanning QR code...'),
        TestModes.face:
            _('Detecting faces...')
    }
    self.ShowInstruction(instructions[mode])
    if mode == TestModes.manual:
      self.ui.BindStandardKeys()

    self.EnableDevice()
    try:
      while True:
        start_time = time.time()
        cv_image = self.ReadSingleFrame()
        if mode == TestModes.frame_count:
          frame_count += 1
          if frame_count >= self.args.num_frames_to_pass:
            return
        elif (mode in [TestModes.qr, TestModes.face] and
              time.time() - tock > process_interval):
          # Doing face recognition based on process_rate due to performance
          # consideration.
          tock = time.time()
          if ((mode == TestModes.qr and self.ScanQRCode(cv_image)) or
              (mode == TestModes.face and self.DetectFaces(cv_image))):
            detected_frame_count += 1
          if detected_frame_count >= self.args.num_frames_to_pass:
            return

        if self.args.show_image:
          self.ShowImage(cv_image)

        self.Sleep(tick - (time.time() - start_time))
    finally:
      self.DisableDevice()

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

    self.mode = self.args.mode
    self.e2e_mode = self.args.e2e_mode

    # Whether we need to transmit image from UI back to Python in e2e mode.
    # TODO(pihsun): This can be removed after the desktop Chrome implements
    # shape detection API.
    self.need_transmit_from_ui = False

    # Whether we need to transmit processed image from Python to UI in e2e mode.
    # TODO(pihsun): This can be removed after the desktop Chrome implements
    # shape detection API.
    self.need_transmit_to_ui = False

    self.flip_image = self.args.flip_image
    if self.flip_image is None:
      self.flip_image = self.args.camera_facing != 'rear'

    if self.e2e_mode:
      if not self.dut.link.IsLocal():
        raise ValueError('e2e mode does not work on remote DUT.')
      camera_facing = ('front' if self.args.camera_facing is None else
                       self.args.camera_facing)
      options = {
          'facingMode': {
              'front': 'user',
              'rear': 'environment'
          }[camera_facing]
      }
      resolution = self.args.camera_args.get('resolution')
      if resolution:
        options['width'], options['height'] = resolution
      options['flipImage'] = self.flip_image
      self.ui.RunJS(
          'window.cameraTest = new CameraTest(args.options)', options=options)
      self.camera_device = None
      if self.mode in [TestModes.qr, TestModes.face]:
        self.need_transmit_from_ui = True
      if self.mode == TestModes.face:
        # TODO(pihsun): Only transmit the location of face instead of the whole
        # image in this case to speed up the process.
        self.need_transmit_to_ui = True
    else:
      self.camera_device = self.dut.camera.GetCameraDevice(
          self.args.camera_facing)

  def runTest(self):
    self.ui.StartCountdownTimer(self.args.timeout_secs, self._Timeout)

    if self.mode == TestModes.manual_led:
      self.LEDTest()
    else:
      self.CaptureTest(self.mode)
