# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Fixtureless camera test.

Description
-----------
This pytest test if camera is working by one of the following method (choose
by argument ``mode``):

* ``'camera_assemble'``: Detect whether the camera is well assembled.

* ``'qr'``: Scan QR code of given string.

* ``'camera_assemble_qr'``: Run camera_assemble and qr mode together.

* ``'face'``: Recognize a human face.

* ``'timeout'``: Run camera capture until timeout.

* ``'frame_count'``: Run camera capture for specified frames.

* ``'manual'``: Show captured image.

* ``'manual_led'``: Light or blink camera LED.

* ``'brightness'``: Check the maximum brightness of frames.

``e2e_mode`` can be set to use Chrome Media API instead of device API.

Test Procedure
--------------
If ``e2e_mode`` is ``True``, the operator may be prompt to click on the 'Allow'
button on Chrome notification to give Chrome camera permission.

The test procedure differs for each different modes:

* ``'camera_assemble'``: Operator prepares a white paper that is large enough
  to cover the FOV of the camera. Test would pass automatically after
  ``num_frames_to_pass`` frames with white paper are captured.

* ``'qr'``: Operator put a QR code with content specified by ``QR_string``.
  Test would pass automatically after ``num_frames_to_pass`` frames with QR code
  are captured.

* ``'camera_assemble_qr'``: Operator prepares a white paper that has QR code on
  it. The white paper should be large enough to cover the FOV of the camera,
  and the QR code should locate at the specified detection region. Test would
  pass automatically after ``num_frames_to_pass`` frames with white paper and
  QR code are captured.

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

``'brightness'``: No user interaction is required, the test pass after
  ``num_frames_to_pass`` frames are captured. Only the frames which the maximum
  brightness is between `brightness_range` are counted.

Except ``'timeout'`` mode, the test would fail after ``timeout_secs`` seconds.

Dependency
----------
End-to-end ``'camera_assemble'``, ``'qr'``, ``'camera_assemble_qr'`` and
``'face'`` modes depend on OpenCV and numpy.

If not end-to-end mode, depend on OpenCV and device API
``cros.factory.device.camera``.

``'qr'`` and ``'camera_assemble_qr'`` mode also depend on library ``zbar``.

Examples
--------
To run a manual capture test. (The default case), add this in test list::

  {
    "pytest_name": "camera"
  }

Resolution must be set when using Chrome API::

  {
    "pytest_name": "camera",
    "args": {
      "camera_args": {
        "resolution": [1920, 1280]
      },
      "e2e_mode": true
    }
  }

To run camera_assemble test, use Chrome API and specify the minimal luminance
ratio to 0.7::

  {
    "pytest_name": "camera",
    "args": {
      "camera_args": {
        "resolution": [1920, 1280]
      },
      "e2e_mode": true,
      "mode": "camera_assemble",
      "min_luminance_ratio": 0.7
    }
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

To run camera_assemble_qr test, and specify the QR string::

  {
    "pytest_name": "camera",
    "args": {
      "camera_args": {
        "resolution": [1920, 1280]
      },
      "mode": "camera_assemble_qr",
      "QR_string": "hello world"
    }
  }

To run facial recognition test, and use Chrome API instead of device API::

  {
    "pytest_name": "camera",
    "args": {
      "camera_args": {
        "resolution": [1920, 1280]
      },
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

To check the camera capturing black frames (the maximum brightness less than
10)::

  {
    "pytest_name": "camera",
    "args": {
      "num_frames_to_pass": 5,
      "mode": "brightness",
      "timeout_secs": 3,
      "brightness_range": [null, 10]
    }
  }
"""


import codecs
import logging
import numbers
import os
import queue
import random
import time
import uuid

from cros.factory.device import device_utils
from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test.rules import phase
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test.utils import barcode
from cros.factory.test.utils import camera_assemble
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import schema
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils

from cros.factory.external import cv2 as cv
from cros.factory.external import numpy as np


# Set JPEG image compression quality to 70 so that the image can be transferred
# through websocket.
_JPEG_QUALITY = 70
_HAAR_CASCADE_PATH = (
    '/usr/local/share/opencv4/haarcascades/haarcascade_frontalface_default.xml')

TestModes = type_utils.Enum([
    'camera_assemble', 'qr', 'camera_assemble_qr', 'face', 'timeout',
    'frame_count', 'manual', 'manual_led', 'brightness'
])

_TEST_MODE_INST = {
    TestModes.manual:
        _('Press ENTER to pass or ESC to fail.'),
    TestModes.timeout:
        _('Running the camera until timeout.'),
    TestModes.frame_count:
        _('Running the camera until expected number of frames captured.'),
    TestModes.camera_assemble:
        _('Cover the field of view of the camera with a white paper. '
          'The red grids represent which region is too dark.'),
    TestModes.qr:
        _('Scanning QR code...'),
    TestModes.camera_assemble_qr:
        _('Place QR code in the frame and cover the field of view of the'
          ' camera with a white paper. The red grids represent which region is'
          ' too dark.'),
    TestModes.face:
        _('Detecting faces...'),
    TestModes.brightness:
        _('Checking brightness...')
}

_RANGE_SCHEMA = schema.JSONSchemaDict(
    'threshold schema object',
    {
        'type': 'array',
        'items': {
            'type': ['number', 'null']
        },
        'minItems': 2,
        'maxItems': 2
    },
)


class CameraTest(test_case.TestCase):
  """Main class for camera test."""
  ARGS = [
      Arg('mode', TestModes, 'The test mode to test camera.', default='qr'),
      Arg(
          'num_frames_to_pass', int,
          'The number of frames with faces in mode "face", '
          'QR code presented in mode "qr", '
          'or any frames in mode "frame_count" to pass the test.', default=10),
      Arg(
          'process_rate', numbers.Real,
          'The process rate of face recognition or '
          'QR code scanning in times per second.', default=5),
      Arg('QR_string', str, 'Encoded string in QR code.',
          default='Hello ChromeOS!'),
      Arg(
          'brightness_range', list, '**[min, max]**, check if the maximum '
          'brightness is between [min, max] (inclusive). None means no limit.',
          default=[None, None], schema=_RANGE_SCHEMA),
      Arg('capture_fps', numbers.Real,
          'Camera capture rate in frames per second.', default=30),
      Arg('timeout_secs', int, 'Timeout value for the test.', default=20),
      Arg('show_image', bool, 'Whether to actually show the image on screen.',
          default=True),
      Arg(
          'e2e_mode', bool, 'Perform end-to-end test or not (for camera).'
          'Normally, camera data is grabbed from video device by OpenCV, '
          "which doesn't support MIPI camera. In e2e mode, camera data is "
          'directly streamed on frontend using JavaScript MediaStream API.',
          default=False),
      Arg(
          'resize_ratio', float,
          'The resize ratio of captured image on screen, '
          'has no effect on e2e mode.', default=0.4),
      Arg('camera_facing', type_utils.Enum(['front', 'rear']),
          ('String "front" or "rear" for the camera to test. '
           'If in normal mode, default is automatically searching one. '
           'If in e2e mode, default is "front".'), default=None),
      Arg(
          'flip_image', bool,
          'Whether to flip the image horizontally. This should be set to False'
          'for the rear facing camera so the displayed image looks correct.'
          'The default value is False if camera_facing is "rear", True '
          'otherwise.', default=None),
      Arg(
          'camera_args', dict, 'Dict of args used for enabling the camera '
          'device. Only "resolution" is supported in e2e mode.', default={}),
      Arg('flicker_interval_secs', (int, float),
          'The flicker interval in seconds in manual_led mode', default=0.5),
      Arg('fullscreen', bool, 'Run the test in fullscreen', default=False),
      Arg('video_start_play_timeout_ms', int,
          'The timeout between we open a stream and it starts to play.',
          default=5000),
      Arg('get_user_media_retries', int,
          ('The times that we try to getUserMedia in camera.js. The '
           'getUserMedia executes at most (1+get_user_media_retries) times.'),
          default=0),
      Arg('min_luminance_ratio', float,
          ('The minimal acceptable luminance of the boundary region of an'
           'image. This value is multiplied by the brightest region of an'
           'image. If the luminance of the boundary region is lower than or'
           'equal to the product, we consider the image containing black edges,'
           'and thus the camera is badly assembled. It is recommended to set'
           'this value to 0.5 for usb camera and 0.7 for mipi camera.'),
          default=0.5)
  ]

  def _Timeout(self):
    if self.mode == TestModes.timeout:
      # If it keeps capturing images until timeout, the test passes.
      self.PassTask()
    else:
      self.FailTask('Camera test failed due to timeout.')

  def ShowFeedback(self, msg):
    self.ui.CallJSFunction('showFeedback', msg)

  def AppendFeedback(self, msg):
    self.ui.CallJSFunction('appendFeedback', msg)

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
    self.ui.CallJSFunction('hideImage')

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

  def DrawRectangle(self, cv_image, rect_pos, rect_shape, color, fill):
    """Draw rectangles on UI.

    Args:
      cv_image: The image captured by camera.
      rect_pos: The x, y coordinates of the top-left corner of the rectangle.
      rect_shape: The width and height of the rectangle.
      color: The color string and its corresponding BGR value.
      fill: Fill the rectangle of not.

    Returns:
       The js functions used to draw the rectangles.
    """
    x_pos, y_pos = rect_pos
    rect_width, rect_height = rect_shape
    color_string, bgr_color = color
    image_height, image_width = cv_image.shape[:2]

    draw_rect_js = ''
    thickness = cv.FILLED if fill else 1
    fill_string = 'true' if fill else 'false'
    if self.e2e_mode:
      # Normalize the coordinates / size to [0, 1], since the canvas in the
      # frontend may not be the same size as the image.
      draw_rect_js += 'cameraTest.drawRect({}, {}, {}, {}, ' \
                      '"{}", {});'.format(
                          float(x_pos) / image_width,
                          float(y_pos) / image_height,
                          float(rect_width) / image_width,
                          float(rect_height) / image_height,
                          color_string,
                          fill_string)
    else:
      cv.rectangle(cv_image, (x_pos, y_pos),
                   (x_pos + rect_width, y_pos + rect_height), bgr_color,
                   thickness)

    return draw_rect_js

  def DetectFaces(self, cv_image):
    # TODO(pihsun): Use the shape detection API in Chrome in e2e mode when it
    # is ready.
    height, width = cv_image.shape[:2]
    cascade = cv.CascadeClassifier(_HAAR_CASCADE_PATH)
    detected_objs = cascade.detectMultiScale(
        cv_image, scaleFactor=1.2, minNeighbors=2,
        flags=cv.CASCADE_DO_CANNY_PRUNING, minSize=(width // 10, height // 10))
    # pylint: disable=len-as-condition
    # Detected_objs will be numpy array or an empty tuple. bool(numpy_array)
    # will not work (will raise an exception).
    detected = len(detected_objs) > 0

    draw_rect_js = 'cameraTest.clearOverlay();'
    for x, y, w, h in detected_objs:
      draw_rect_js += self.DrawRectangle(cv_image, (x, y), (w, h),
                                         ('white', 255), False)

    if self.e2e_mode:
      self.RunJSBlocking(draw_rect_js)
    return detected

  def DetectAssemblyIssue(self, cv_image):
    camera_assemble_issue = camera_assemble.DetectCameraAssemblyIssue(
        cv_image, self.min_luminance_ratio)

    is_too_dark, grid, grid_size = \
      camera_assemble_issue.IsBoundaryRegionTooDark()
    if is_too_dark:
      grid_width, grid_height = grid_size
      height, width = cv_image.shape[:2]

      draw_rect_js = 'cameraTest.clearOverlay();'
      for grid_r, y_pos in enumerate(range(0, height, grid_height)):
        for grid_c, x_pos in enumerate(range(0, width, grid_width)):
          if grid[grid_r][grid_c]:
            # It will be slow if we call the js function for each grid.
            # Instead, we run the js functions all at once at the end of the
            # loop.
            draw_rect_js += self.DrawRectangle(cv_image, (x_pos, y_pos),
                                               (grid_width, grid_height),
                                               ('red', (0, 0, 255)), True)
      if self.e2e_mode:
        self.RunJSBlocking(draw_rect_js)
    return not is_too_dark

  def ScanQRCode(self, cv_image):
    scanned_text = None

    # TODO(pihsun): Use the shape detection API in Chrome in e2e mode when it
    # is ready.
    scan_results = barcode.ScanQRCode(cv_image)
    if scan_results:
      scanned_text = scan_results[0]

    if scanned_text:
      self.ShowFeedback(
          i18n.StringFormat(_('Scanned QR code: "{text}"'), text=scanned_text))
      if scanned_text != self.args.QR_string:
        logging.warning(
            'Scanned QR code "%s" does not match target QR code "%s"',
            scanned_text, self.args.QR_string)

    return scanned_text == self.args.QR_string

  def GetResultString(self, result):
    return _('Success!') if result else _('Failure')

  def DetectAssemblyIssueAndScanQRCode(self, cv_image):
    camera_well_assembled = self.DetectAssemblyIssue(cv_image)

    img_height, img_width = cv_image.shape[:2]
    x_pos, y_pos, qr_width, qr_height = \
      camera_assemble.GetQRCodeDetectionRegion(img_height, img_width)

    # Since we'll use the center and boundary regions of the image when
    # conducting the camera_assemble test, we restrict the position of the QR
    # code so that it won't be at the center or boundary regions.
    qr_region = cv_image[y_pos:y_pos + qr_height, x_pos:x_pos + qr_width, :]
    qr_code_scan_success = self.ScanQRCode(qr_region)

    string_to_show = i18n.StringFormat(
        _(
            'Camera assemble: {camera_well_assembled}, '
            'QR code: {qr_code_scan_success}',
            camera_well_assembled=self.GetResultString(camera_well_assembled),
            qr_code_scan_success=self.GetResultString(qr_code_scan_success)))

    if qr_code_scan_success:
      self.AppendFeedback(string_to_show)
    else:
      self.ShowFeedback(string_to_show)

    return camera_well_assembled and qr_code_scan_success

  def BrightnessCheck(self, cv_image):
    value = cv.cvtColor(cv_image, cv.COLOR_BGR2GRAY).max()
    threshold = self.args.brightness_range
    session.console.info(f'Maximum brightness: {value}')
    return ((threshold[0] is None or threshold[0] <= value) and
            (threshold[1] is None or value <= threshold[1]))

  def ShowImage(self, cv_image):
    if self.e2e_mode:
      # In e2e mode, the image is directly shown by frontend in a video
      # element, independent to the calls to ShowImage here.
      return

    resize_ratio = self.args.resize_ratio
    cv_image = cv.resize(cv_image, None, fx=resize_ratio, fy=resize_ratio,
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
          'showImage', 'data:image/jpeg;base64,' + jpg_base64.decode('utf-8'))
    except AttributeError:
      # The websocket is closed because test has passed/failed.
      return

  def DrawQRDetectionRegion(self, cv_image):
    img_height, img_width = cv_image.shape[:2]
    x_pos, y_pos, qr_width, qr_height = \
      camera_assemble.GetQRCodeDetectionRegion(img_height, img_width)

    if self.e2e_mode:
      self.RunJSBlocking('cameraTest.clearOverlay()')
      self.RunJSBlocking('cameraTest.drawRect({}, {}, {}, {})'.format(
          float(x_pos) / img_width,
          float(y_pos) / img_height,
          float(qr_width) / img_width,
          float(qr_height) / img_height))
    else:
      cv.rectangle(cv_image, (x_pos, y_pos),
                   (x_pos + qr_width, y_pos + qr_height), 255)

  def CaptureTestFrame(self, mode, cv_image):
    if mode == TestModes.frame_count:
      return True
    if mode == TestModes.camera_assemble:
      return self.DetectAssemblyIssue(cv_image)
    if mode == TestModes.qr:
      return self.ScanQRCode(cv_image)
    if mode == TestModes.camera_assemble_qr:
      return self.DetectAssemblyIssueAndScanQRCode(cv_image)
    if mode == TestModes.face:
      return self.DetectFaces(cv_image)
    if mode == TestModes.brightness:
      return self.BrightnessCheck(cv_image)

    # For all other test, like TestModes.manually, return False.
    return False

  def CaptureTest(self, mode):
    self.ShowInstruction(_TEST_MODE_INST[mode])
    if mode == TestModes.manual:
      self.ui.BindStandardKeys()

    if not self.args.show_image:
      self.ui.CallJSFunction('hideImage')

    self.EnableDevice()
    try:
      frame_count = 0
      frame_interval = 1.0 / float(self.args.capture_fps)
      last_process_time = time.time()
      if mode == TestModes.frame_count:
        process_interval = 0
      else:
        process_interval = 1.0 / float(self.args.process_rate)

      while True:
        start_time = time.time()
        cv_image = self.ReadSingleFrame()

        if time.time() - last_process_time > process_interval:
          last_process_time = time.time()
          if self.CaptureTestFrame(mode, cv_image):
            frame_count += 1
          if frame_count >= self.args.num_frames_to_pass:
            return

        if self.args.show_image:
          if mode == TestModes.camera_assemble_qr:
            self.DrawQRDetectionRegion(cv_image)
          self.ShowImage(cv_image)

        self.Sleep(frame_interval - (time.time() - start_time))
    finally:
      self.DisableDevice()

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

    self.mode = self.args.mode
    self.e2e_mode = self.args.e2e_mode
    self.min_luminance_ratio = self.args.min_luminance_ratio

    # Whether we need to transmit image from UI back to Python in e2e mode.
    # TODO(pihsun): This can be removed after the desktop Chrome implements
    # shape detection API.
    self.need_transmit_from_ui = False

    self.flip_image = self.args.flip_image
    if self.flip_image is None:
      self.flip_image = self.args.camera_facing != 'rear'

    if self.args.fullscreen:
      self.ui.RunJS('test.setFullScreen(true)')

    if self.e2e_mode:
      if not self.dut.link.IsLocal():
        raise ValueError('e2e mode does not work on remote DUT.')
      if self.mode == TestModes.frame_count:
        logging.warning('frame count mode is NOT real frame count in e2e mode, '
                        'consider using timeout instead.')

      camera_facing = ('front' if self.args.camera_facing is None else
                       self.args.camera_facing)
      options = {
          'facingMode': {
              'front': 'user',
              'rear': 'environment'
          }[camera_facing],
          'videoStartPlayTimeoutMs': self.args.video_start_play_timeout_ms,
          'getUserMediaRetries': self.args.get_user_media_retries,
      }
      resolution = self.args.camera_args.get('resolution')
      if not resolution:
        raise ValueError(
            'Resolution must be specified when e2e_mode is set to true.')
      options['width'], options['height'] = resolution
      options['flipImage'] = self.flip_image
      self.ui.RunJS(
          'window.cameraTest = new CameraTest(args.options)', options=options)
      self.camera_device = None
      if self.mode in [
          TestModes.camera_assemble, TestModes.qr, TestModes.camera_assemble_qr,
          TestModes.face
      ]:
        self.need_transmit_from_ui = True
    else:
      self.camera_device = self.dut.camera.GetCameraDevice(
          self.args.camera_facing)

  def runTest(self):
    self.ui.StartCountdownTimer(self.args.timeout_secs, self._Timeout)

    if self.mode == TestModes.manual:
      self.assertFalse(phase.GetPhase() > phase.DVT,
                       msg='"manual" mode cannot be used after DVT')

    if self.mode in [
        TestModes.manual, TestModes.camera_assemble, TestModes.qr,
        TestModes.camera_assemble_qr, TestModes.face
    ]:
      self.assertTrue(self.args.show_image,
                      msg='show_image should be set to true!')

    if self.mode == TestModes.manual_led:
      self.LEDTest()
    else:
      self.CaptureTest(self.mode)
