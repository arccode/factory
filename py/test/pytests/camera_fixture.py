# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Camera fixture test.

Fixture types:

- FullChamber: light chamber for full-assembly line in FATP and RMA.
- ABChamber: light chamber for AB sub-assembly line (after A and B panels are
  assembled).
- ModuleChamber: light chamber for module-level OQC, IQC, production QC.
- Panel: a simple test chart panel for standalone lens shading

Test types:

- When fixture_type == {Full|AB|Module}Chamber:

  - Calibration: calibrates light chamber and test chart to align with the
    golden sample (only checking image shift and tilt).
  - IQ (Image Quality): checks IQ factors such as MTF (sharpness), lens
    shading, image shift, and image tilt in one test.

- When fixture_type == Panel:

  - LensShading: checks lens shading ratio (usually fails when camera module
    is not precisely aligned with the view hole on bezel).

Test chart versions:

- A: 7x11 blocks. Used for 720p camera or similar aspect ratio.
- B: 7x9 blocks. Used for VGA camera or similar aspect ratio.
- White: All white. Used for standalone lens shading test.

Hot keys:

- Press Enter or Space keys to start the IQ test
- Press ESC to leave the test.

[IQ Test Only]

Data methods:

- Simple: reads parameters from 'param_dict' argument, but skips saving
  test results.
- USB: reads parameter file from USB drive, and saves test results in USB drive
  in subfolders ordered by date.
- Shopfloor: reads param file from shopfloor, and saves test results in
  shopfloor aux_logs. This is recommended over USB when there is
  Shopfloor environment because USB drive is not reliable.

Test parameters:

- Please check camera_fixture_static/camera.params.sample

Analysis of saved test data from IQ test:

- Use py/test/fixture/camera/analysis/analyze_camera_fixture_data.py

Control Chamber:

- If control_chamber is True, chamber_conn_params must also be set.
- If chamber_conn_params is set to the string 'default', the default parameter
  CHAMBER_CONN_PARAMS_DEFAULT is used. Otherwise chamber_conn_params should be
  specified as a dict.

Usage examples::

  # Without light chamber:

    # Standalone lens shading check.
    OperatorTest(
      id='LensShading',
      pytest_name='camera_fixture',
      dargs={
        'mock_mode': False,
        'test_type': 'LensShading',
        'fixture_type': 'Panel',
        'test_chart_version': 'White',
        'capture_resolution': (640, 480),
        'resize_ratio': 0.7,
        'lens_shading_ratio': 0.30})

  # With light chamber:

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

    # IQ (Image Quality) test with shopfloor.
    OperatorTest(
      id='ImageQuality',
      pytest_name='camera_fixture',
      dargs={'mock_mode': False,
             'test_type': 'IQ',
             'fixture_type': 'FullChamber',
             'test_chart_version': 'A',
             'capture_resolution': (1280, 720),
             'data_method': 'Shopfloor',
             'param_pathname': 'camera/camera.params.FATP',
             'local_ip': None})

    # IQ (Image Quality) test with USB drive.
    OperatorTest(
      id='ImageQualityUSB',
      pytest_name='camera_fixture',
      dargs={'mock_mode': False,
             'test_type': 'IQ',
             'fixture_type': 'ModuleChamber',
             'test_chart_version': 'A',
             'capture_resolution': (1280, 720),
             'data_method': 'USB',
             'param_pathname': 'camera.params'}),

  # With light chamber and controls the light chamber charts

    # IQ (Image Quality) test with shopfloor.
    OperatorTest(
      id='ImageQuality',
      pytest_name='camera_fixture',
      dargs={'mock_mode': False,
             'test_type': 'IQ',
             'fixture_type': 'FullChamber',
             'control_chamber': True,
             'chamber_conn_params': 'default',
             'chamber_cmd': {
               'WHITE': [('white\\n', 'White_Ready')],
               'CHARTA': [('chart1\\n', 'Chart1_Ready')]
             },
             'test_chart_version': 'A',
             'capture_resolution': (1280, 720),
             'data_method': 'Shopfloor',
             'param_pathname': 'camera/camera.params.FATP',
             'local_ip': None})

    # With mock_mode=True
    OperatorTest(
      id='ImageQuality',
      pytest_name='camera_fixture',
      dargs={'mock_mode': True,
             'test_type': 'IQ',
             'fixture_type': 'FullChamber',
             'control_chamber': True,
             'chamber_conn_params': 'default',
             'chamber_cmd': {
               'WHITE': [('white\\n', 'White_Ready')],
               'CHARTA': [('chart1\\n', 'Chart1_Ready')]
             },
             'test_chart_version': 'A',
             'capture_resolution': (1280, 720),
             'data_method': 'Shopfloor',
             'param_pathname': 'camera/camera.params.FATP',
             'local_ip': None})

"""

import ast
import base64
from collections import namedtuple
from collections import OrderedDict
try:
  import cv2  # pylint: disable=import-error
except ImportError:
  pass
import datetime
import logging
import numpy as np
import os
import Queue
import re
import string
import threading
import time
import traceback
import unittest
import xmlrpclib

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test import event_log
from cros.factory.test import factory
from cros.factory.test.fixture.camera import light_chamber
from cros.factory.test.fixture.camera import perf_tester as camperf
from cros.factory.test.fixture.camera import renderer as renderer
from cros.factory.test.fixture import fixture_connection
from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import leds
from cros.factory.test import network
from cros.factory.test import shopfloor
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test.utils import camera_utils
from cros.factory.test.utils import media_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import type_utils


# Delay between each frame during calibration.
CALIBRATION_FPS = 15
# Delay between each frame during lens shading test.
LENS_SHADING_FPS = 5

# TODO(jchuang): import from event.py
# Upper limit of message size in JavaScript RPC.
MAX_MESSAGE_SIZE = 60000


# Test stages in IQ test.
STAGE00_START = 'cam_start'  # start test
STAGE10_SN = 'cam_sn'  # check serial number
STAGE15_FW = 'cam_fw'  # check firmware
STAGE20_INIT = 'cam_init'  # init camera and try to read one image
STAGE25_AWB = 'cam_awb'  # AWB and AE
STAGE30_IMG = 'cam_img'  # capture low-noises image

STAGE50_VC = 'cam_vc'  # visual correctness, image shift/tilt
STAGE60_LS = 'cam_ls'  # lens shading
STAGE70_MTF = 'cam_mtf'  # MTF / sharpness
STAGE90_END = 'cam_end'  # end test
STAGE100_SAVED = 'cam_data_saved'  # test data saved


# CSS style classes defined in the corresponding HTML file.
STYLE_INFO = 'color_idle'
STYLE_PASS = 'color_good'
STYLE_FAIL = 'color_bad'


# HTML id.
ID_PREVIEW_IMAGE = 'preview_image'
ID_ORIGINAL_IMAGE = 'camera_image'
ID_ANALYZED_IMAGE = 'analyzed_image'

ID_TEST_STATUS = 'test_status'
ID_MAIN_SCREEN_TITLE = 'main_screen_title'


# Text labels.
MSG_TITLE_CALIBRATION = i18n_test_ui.MakeI18nLabel('Camera Fixture Calibration')
MSG_TITLE_LENS_SHADING_TEST = i18n_test_ui.MakeI18nLabel(
    'Camera Lens Shading Test')
MSG_TITLE_IQ_TEST = i18n_test_ui.MakeI18nLabel('Camera Image Quality Test')

# Test stage => message
MSG_TEST_STATUS = {
    STAGE00_START: _('Starting the test'),
    STAGE10_SN: _('Reading serial number'),
    STAGE15_FW: _('Checking firmware version'),
    STAGE20_INIT: _('Initializing camera'),
    STAGE25_AWB: _('Adjusting white balance'),
    STAGE30_IMG: _('Reading test image'),
    STAGE50_VC: _('Locating test pattern'),
    STAGE60_LS: _('Checking vignetting level'),
    STAGE70_MTF: _('Checking image sharpness'),
    STAGE90_END: _('All tests are complete'),
    STAGE100_SAVED: _('Test data saved'),
}


# LED pattern.
LED_PATTERN = ((leds.LED_NUM | leds.LED_CAP, 0.05), (0, 0.05))


# Data structures.
TestType = type_utils.Enum(['CALI', 'LS', 'IQ'])
Fixture = type_utils.Enum(['FULL', 'AB', 'MODULE', 'PANEL'])
DataMethod = type_utils.Enum(['SIMPLE', 'USB', 'SF'])
EventType = type_utils.Enum(['START_TEST', 'EXIT_TEST', 'VALIDATE_SN'])
TestStatus = type_utils.Enum(['PASSED', 'FAILED', 'UNTESTED', 'NA'])

InternalEvent = namedtuple('InternalEvent', 'event_type aux_data')


# Root failure causes (used for quick troubleshooting at factory).
FAIL_SN = 'SerialNumber'  # Missing camera or bad serial number.
FAIL_FIRMWARE = 'Firmware'  # Wrong firmware version.
FAIL_BAD_CAMERA = 'BadCamera'  # Fail to read image from camera.
FAIL_CHAMBER_ERROR = 'ChamberError'  # Fail to set light chamber chart
FAIL_WRONG_IMAGE = 'WrongImage'  # Image doesn't contain a valid test chart.
FAIL_IMAGE_SHIFT = 'Shift'  # Image shift is too large.
FAIL_IMAGE_TILT = 'Tilt'  # Image tilt is too large.
FAIL_LENS_SHADING = 'LensShading'  # Lens shading is over-limits.
FAIL_MTF = 'MTF'  # Image sharpness is too low.
FAIL_USB = 'USB'  # Fail to save to USB.
FAIL_UNKNOWN = 'UnknownError'  # Unknown error.


# Event log keys.
EVENT_IQ_STATUS = 'camera_IQ_status'
EVENT_IQ_DATA = 'camera_IQ_data'
EVENT_LENS_SHADING = 'camera_lens_shading'


# Log output format.
LOG_FORMAT_SHIFT = 'Image shift percentage: %f'
LOG_FORMAT_SHIFT_X = 'Image shift X: %f'
LOG_FORMAT_SHIFT_Y = 'Image shift Y: %f'
LOG_FORMAT_TILT = 'Image tilt: %f'
LOG_FORMAT_CORNER = 'Found corners count: %d'
LOG_FORMAT_EDGE = 'Found edges count: %d'
LOG_FORMAT_VC_MSG = 'Visual correctness: %s'

LOG_FORMAT_LS_LOW_FREQ = 'Low-frequency response value: %f'
LOG_FORMAT_LS_RATIO = 'Lens shading ratio: %f'
LOG_FORMAT_LS_MSG = 'Lens shading: %s'

LOG_FORMAT_MTF_MEDIAN = 'Median MTF value: %f'
LOG_FORMAT_MTF_LOWEST = 'Lowest MTF value: %f'
LOG_FORMAT_MTF_MSG = 'MTF Sharpness: %s'


# Serial numbers.
SN_NA = 'NO_SN'
SN_INVALID = 'INVALID_SN'


# Chamber connection parameters
CHAMBER_CONN_PARAMS_DEFAULT = {
    'driver': 'pl2303',
    'serial_delay': 0,
    'serial_params': {
        'baudrate': 9600,
        'bytesize': 8,
        'parity': 'N',
        'stopbits': 1,
        'xonxoff': False,
        'rtscts': False,
        'timeout': None
    },
    'response_delay': 2
}


class _IQTestDelegate(object):
  """Delegate class for IQ (image quality) test.

  We use four types of logging:

    1. factory console (factory.console.info())
    2. factory.log (self._Log())
    3. Save raw data to USB drive or shopfloor aux_logs folder (self._Log() and
       self._SaveTestData())
    4. Event log (event_log.Log())

  It has three public methods:
    - __init__()
    - LoadParamsAndShowTestScreen()
    - RunTest()

  Usage Example:

    delegate = _IQTestDelegate(...)
    delegate.LoadParamsAndShowTestScreen()
    while ...:  # loop test iterations
      delegate.RunTest()

  """

  def __init__(self, delegator, mock_mode, chamber, fixture_type,
               control_chamber, chamber_n_retries, chamber_retry_delay,
               data_method, local_ip, param_pathname, param_dict,
               save_good_image, save_bad_image):
    """Initalizes _IQTestDelegate.

    Args:
      delegator: Instance of CameraFixture.
      mock_mode: Whether or not we are in mock mode.
      chamber: Instance of LightChamber.
      fixture_type: Fixture enum.
      control_chamber: Whether or not to control the chart in the light chamber.
      chamber_n_retries: Number of retries when connecting.
      chamber_retry_delay: Delay between connection retries.
      data_method: DataMethod enum.
      local_ip: Check CameraFixture.ARGS for detailed description.
      param_pathname: ditto.
      param_dict: ditto.
      save_good_image: ditto.
      save_bad_image: ditto.
    """

    self.delegator = delegator
    self.mock_mode = mock_mode
    self.chamber = chamber
    self.fixture_type = fixture_type
    self.control_chamber = control_chamber
    self.chamber_n_retries = chamber_n_retries
    self.chamber_retry_delay = chamber_retry_delay

    # Basic config set by test_list.
    self.data_method = data_method
    self.local_ip = local_ip
    self.param_pathname = param_pathname
    self.save_good_image = save_good_image
    self.save_bad_image = save_bad_image

    # Internal context across multiple test iterations.
    if data_method == DataMethod.SIMPLE:
      self.params = param_dict
    else:
      self.params = None  # to be dynamically loaded later
    self.timing = {}  # test stage => completion ratio (0~1)

    self.usb_ready_event = None  # Internal flag is true if USB drive is ready.
    self.usb_dev_path = None

    # Internal context to be reset for each test iteration.
    # (Remember to reset them in _ResetForNewTest())
    self.logs = []  # list of log lines to be saved later.
    self.module_sn = SN_NA
    self.original_img = None
    self.analyzed_img = None

  def LoadParamsAndShowTestScreen(self):
    """Loads parameters and then shows main test screen."""
    # TODO(yllin): Move parameter loading to a standalone pytest and transform
    #              the parameters to JSON form.
    if self.data_method == DataMethod.USB:
      self.params = self._LoadParamsFromUSB()
    elif self.data_method == DataMethod.SF:
      self.params = self._LoadParamsFromShopfloor()

    media_utils.MediaMonitor('usb-serial', None).Start(
        on_insert=self._OnU2SInsertion, on_remove=self._OnU2SRemoval)

    # Basic pre-processing of the parameters.
    self._Log('Parameter version: %s\n' % self.params['version'])
    self._CalculateTiming()

    bind_keys = [test_ui.SPACE_KEY]
    if not self.params['ui']['ignore_enter_key']:
      bind_keys.append(test_ui.ENTER_KEY)
    for key in bind_keys:
      self.delegator.ui.BindKeyJS(
          key, 'if(event)event.preventDefault();\nOnButtonStartTestClick();')
    self.delegator.ui.CallJSFunction('ShowMainTestScreen',
                                     not self.params['sn']['auto_read'])

  def _LoadParamsFromUSB(self):
    """Loads parameters from USB drive."""
    self.usb_ready_event = threading.Event()
    media_utils.RemovableDiskMonitor().Start(on_insert=self._OnUSBInsertion,
                                             on_remove=self._OnUSBRemoval)

    while self.usb_ready_event.wait():
      with media_utils.MountedMedia(self.usb_dev_path, 1) as mount_point:
        pathname = os.path.join(mount_point, self.param_pathname)
        try:
          with open(pathname, 'r') as f:
            return ast.literal_eval(f.read())
        except IOError as e:
          self._Log('Error: fail to read %r: %r' % (pathname, e))
      time.sleep(0.5)

  def _LoadParamsFromShopfloor(self):
    """Loads parameters from shopfloor."""
    network.PrepareNetwork(ip=self.local_ip, force_new_ip=False)

    factory.console.info('Reading %s from shopfloor', self.param_pathname)
    shopfloor_client = shopfloor.GetShopfloorConnection()
    return ast.literal_eval(
        shopfloor_client.GetParameter(self.param_pathname).data)

  def _CalculateTiming(self):
    """Calculates the timing of each test stage to self.timing."""
    chk_point = self.params['chk_point_IQ']
    cumsum = np.cumsum([d for _, d in chk_point])
    total_time = cumsum[-1]
    for i in xrange(len(chk_point)):
      if i > 0:
        self.timing[chk_point[i][0]] = cumsum[i - 1] / total_time
      else:
        self.timing[chk_point[i][0]] = 0

  def RunTest(self, input_sn):
    if self.delegator.args.assume_chamber_connected:
      self._SetupFixture()

    ret = self._IQTest(input_sn)

    if self.delegator.args.auto_mode:
      self.delegator.PostInternalQueue(EventType.EXIT_TEST)

    return ret

  def _IQTest(self, input_sn):
    """Runs IQ (Image Quality) test.

    Args:
      input_sn: Serial number input on screen.
    """
    ref_data = camperf.PrepareTest(self.chamber.GetTestChartFile())
    self._ResetForNewTest()

    # test stage => status
    test_status = OrderedDict([
        (STAGE00_START, TestStatus.NA),
        (STAGE10_SN, TestStatus.UNTESTED),
        (STAGE15_FW, TestStatus.UNTESTED),
        (STAGE20_INIT, TestStatus.UNTESTED),
        (STAGE25_AWB, TestStatus.UNTESTED),
        (STAGE30_IMG, TestStatus.UNTESTED),
        (STAGE50_VC, TestStatus.UNTESTED),
        (STAGE60_LS, TestStatus.UNTESTED),
        (STAGE70_MTF, TestStatus.UNTESTED),
        (STAGE90_END, TestStatus.UNTESTED),
        (STAGE100_SAVED, TestStatus.NA),
    ])
    tar_vc = None
    tar_ls = None
    tar_mtf = None
    non_locals = {}  # hack to immitate nonlocal keyword in Python 3.x

    def update_progress(test_stage):
      non_locals['current_stage'] = test_stage
      self._UpdateTestProgress(test_stage)

    def update_status(success):
      if success:
        test_status[non_locals['current_stage']] = TestStatus.PASSED
      else:
        test_status[non_locals['current_stage']] = TestStatus.FAILED

    try:
      update_progress(STAGE00_START)

      # (1) Check / read module serial number.
      update_progress(STAGE10_SN)
      success = self._CheckSN(input_sn)
      update_status(success)
      if not success:
        return False, FAIL_SN

      # (2) Check firmware version.
      update_progress(STAGE15_FW)
      success = self._CheckCameraFirmware()
      update_status(success)
      if not success:
        return False, FAIL_FIRMWARE

      # (3) Take low noises photo.
      try:
        update_progress(STAGE20_INIT)

        # Switch to SFR Chart.
        if self.control_chamber:
          self.chamber.SetChart(light_chamber.LightChamber.Charts.SFR)

        self.chamber.EnableCamera()
        self.chamber.ReadSingleFrame(return_gray_image=False)  # test one image
        update_status(True)

        update_progress(STAGE25_AWB)
        time.sleep(self.params['cam_img']['buf_time'])
        update_status(True)

        update_progress(STAGE30_IMG)
        self.original_img, gray_img = self.chamber.ReadLowNoisesFrame(
            self.params['cam_img']['n_samples'])

        # Switch to White chart.
        if self.control_chamber:
          self.chamber.SetChart(light_chamber.LightChamber.Charts.WHITE)

        # Wait for AE/AWB.
        time.sleep(self.params['cam_img']['buf_time'])

        _, ls_gray_img = self.chamber.ReadSingleFrame(return_gray_image=True)
        update_status(True)
        self._UpdateOriginalImage()

        # TODO(wnhuang): overlay the calculation of MTF with len shading image
        # taking to reduce cycle time.
      except light_chamber.LightChamberCameraError as e:
        update_status(False)
        self._Log('Error: cannot read image %r' % e)
        return False, FAIL_BAD_CAMERA
      except light_chamber.LightChamberError as e:
        update_status(False)
        self._Log('Error: %r' % e)
        return False, FAIL_CHAMBER_ERROR
      except Exception as e:
        update_status(False)
        self._Log('Unknown Error: ' + traceback.format_exc())
        return False, FAIL_UNKNOWN
      finally:
        # It's important to close camera device even with intermittent error.
        self.chamber.DisableCamera()

      # (4) Visual correctness, image shift and tilt.
      update_progress(STAGE50_VC)
      success, tar_vc = camperf.CheckVisualCorrectness(gray_img, ref_data,
                                                       **self.params['cam_vc'])
      update_status(success)

      self.analyzed_img = self.original_img.copy()
      renderer.DrawVC(self.analyzed_img, success, tar_vc)
      self._UpdateAnalyzedImage()
      if not success:
        if 'shift' in tar_vc.msg:
          return False, FAIL_IMAGE_SHIFT
        elif 'tilt' in tar_vc.msg:
          return False, FAIL_IMAGE_TILT
        else:
          return False, FAIL_WRONG_IMAGE

      # (5) Lens shading.
      update_progress(STAGE60_LS)
      success, tar_ls = camperf.CheckLensShading(ls_gray_img,
                                                 **self.params['cam_ls'])
      update_status(success)

      if not success:
        return False, FAIL_LENS_SHADING

      # (6) MTF.
      update_progress(STAGE70_MTF)
      success, tar_mtf = camperf.CheckSharpness(gray_img, tar_vc.edges,
                                                **self.params['cam_mtf'])
      update_status(success)

      renderer.DrawMTF(self.analyzed_img, tar_vc.edges, tar_mtf.perm,
                       tar_mtf.mtfs,
                       self.params['cam_mtf']['mtf_crop_ratio'],
                       self.params['ui']['mtf_color_map_range'])
      self._UpdateAnalyzedImage()
      if not success:
        return False, FAIL_MTF

      # (7) Final test result.
      update_progress(STAGE90_END)
      update_status(True)
    finally:
      # (8) Logs to event log, and save to USB and shopfloor.
      update_progress(STAGE100_SAVED)
      self._SaveTestData(test_status[STAGE90_END] == TestStatus.PASSED)
      update_status(True)
      self._CollectIQLogs(test_status, tar_vc, tar_ls, tar_mtf)
      self._FlushEventLogs()

      # JavaScript needs to cleanup after the test is completed.
      self.delegator.ui.CallJSFunction('OnTestCompleted')

    return True, None

  def _ResetForNewTest(self):
    """Reset per-test context for new test."""
    self.logs = []
    self.module_sn = SN_NA

    self.original_img = None
    self._UpdateOriginalImage()
    self.analyzed_img = None
    self._UpdateAnalyzedImage()

  def _UpdateOriginalImage(self):
    """Shows or hide original image on screen."""
    if self.original_img is None:
      self.delegator.HideImage(ID_ORIGINAL_IMAGE)
    else:
      self.delegator.ShowImage(self.original_img, ID_ORIGINAL_IMAGE)

  def _UpdateAnalyzedImage(self):
    """Shows or hides analyzed image on screen."""
    if self.analyzed_img is None:
      self.delegator.HideImage(ID_ANALYZED_IMAGE)
    else:
      self.delegator.ShowImage(self.analyzed_img, ID_ANALYZED_IMAGE)

  def _UpdateTestProgress(self, test_stage):
    """Updates UI to show the test progress.

    Args:
      test_stage: Current test stage.
    """
    msg = MSG_TEST_STATUS[test_stage]
    self.delegator.ShowTestStatus(msg)
    self.delegator.ShowProgressBar(self.timing[test_stage])

  def _Log(self, text):
    """Custom log function to log to factory console and USB/shopfloor later."""
    factory.console.info(text)
    self.logs.append(text)

  def _SaveTestData(self, test_passed):
    """Saves test data to USB drive or shopfloor.

    Args:
      test_passed: whether the IQ test has passed the criteria.
    """
    log_prefix = self._GetLogFilePrefix()

    self.logs.append('')  # add tailing newline
    data_files = [(log_prefix + '.txt', '\n'.join(self.logs))]

    if ((test_passed and self.save_good_image) or
        (not test_passed and self.save_bad_image)):
      if self.original_img is not None:
        data_files.append((
            log_prefix + '.bmp',
            camera_utils.EncodeCVImage(self.original_img, '.bmp')))
      if self.analyzed_img is not None:
        data_files.append((
            log_prefix + '.jpg',
            camera_utils.EncodeCVImage(self.analyzed_img, '.jpg')))

    # Skip saving test data for DataMethod.SIMPLE.
    if self.data_method == DataMethod.USB:
      self._SaveTestDataToUSB(data_files)
    elif self.data_method == DataMethod.SF:
      self._SaveTestDataToShopfloor(data_files)

  def _GetLogFilePrefix(self):
    if self.fixture_type == Fixture.FULL:
      device_sn = device_data.GetSerialNumber() or 'MISSING_SN'
      return '_'.join([re.sub(r'\W+', '_', x) for x in
                       [os.environ.get('CROS_FACTORY_TEST_PATH'),
                        device_sn,
                        self.module_sn]])
    else:
      return self.module_sn

  def _SaveTestDataToUSB(self, data_files):
    """Saves test data to USB drive.

    Args:
      data_files: list of (filename, file data) pairs.

    Returns:
      Success or not.
    """
    self.usb_ready_event.wait()
    with media_utils.MountedMedia(self.usb_dev_path, 1) as mount_point:
      folder_path = os.path.join(mount_point,
                                 datetime.date.today().strftime('%Y%m%d'))
      if os.path.exists(folder_path):
        if not os.path.isdir(folder_path):
          factory.console.info('Error: fail to create folder %r', folder_path)
          return False
      else:
        os.mkdir(folder_path)

      for filename, data in data_files:
        file_path = os.path.join(folder_path, filename)
        mode = 'ab' if '.txt' in filename else 'wb'
        try:
          with open(file_path, mode) as f:
            f.write(data)
        except IOError as e:
          self._Log('Error: fail to save %r: %r' % (file_path, e))
          return False
    return True

  def _SaveTestDataToShopfloor(self, data_files):
    """Saves test data to shopfloor.

    Args:
      data_files: list of (filename, file data) pairs.
    """
    network.PrepareNetwork(ip=self.local_ip, force_new_ip=False)
    shopfloor_client = shopfloor.GetShopfloorConnection()

    for filename, data in data_files:
      start_time = time.time()
      shopfloor_client.SaveAuxLog(filename, xmlrpclib.Binary(data))
      factory.console.info('Successfully uploaded %r in %.03f s',
                           filename, time.time() - start_time)

  def _CheckSN(self, input_sn):
    """Checks and/or read module serial number.

    Args:
      input_sn: Serial number input on UI.
    """
    try:
      if self.params['cam_sn']['auto_read']:
        input_sn = self.delegator.camera_dev.GetSerialNumber()
    except Exception:
      self._Log('Error: fails to read serial number.')
      return False

    self.module_sn = input_sn
    self._Log('Serial number: %s' % self.module_sn)
    if not self.delegator.camera_dev.IsValidSerialNumber(self.module_sn):
      self._Log('Error: invalid serial number.')
      return False

    return True

  def _CheckCameraFirmware(self):
    if self.params['cam_fw']['fw_check']:
      success, version = self._ReadSysfs(self.params['cam_fw']['fw_sysfs_path'])
      if success:
        self._Log('Firmware version: %s' % version)
        if version != self.params['cam_fw']['fw_version']:
          success = False
          self._Log('Error: invalid firmware version: %r.' % version)
    else:
      success = True

    return success

  def _ReadSysfs(self, pathname):
    """Read single-line data from sysfs.

    Args:
      pathname: Pathname in sysfs.

    Returns:
      Tuple of (success, read data).
    """
    def _FilterNonPrintable(s):
      return ''.join(c for c in s if c in string.printable)

    try:
      read_data = _FilterNonPrintable(
          self.delegator.dut.ReadSpecialFile(pathname)).rstrip()
    except IOError as e:
      self._Log('Fail to read %r: %r' % (pathname, e))
      return False, None
    if read_data.find('\n') >= 0:
      self._Log('%r contains multi-line data: %r' % (pathname, read_data))
      return False, None
    return True, read_data

  def _CollectIQLogs(self, test_status, tar_vc, tar_ls, tar_mtf):
    # 1. Log overall test states.
    self._Log('Test status:\n%s' % self._FormatOrderedDict(test_status))
    event_log.Log(EVENT_IQ_STATUS, **test_status)

    # 2. Log IQ data.
    IQ_data = {}

    def mylog(value, key, log_text_fmt):
      self._Log((log_text_fmt % value))
      IQ_data[key] = value

    IQ_data['module_sn'] = self.module_sn

    if tar_vc is not None:
      if hasattr(tar_vc, 'shift'):
        mylog(float(tar_vc.shift), 'image_shift', LOG_FORMAT_SHIFT)
        mylog(float(tar_vc.v_shift[0]), 'image_shift_x', LOG_FORMAT_SHIFT_X)
        mylog(float(tar_vc.v_shift[1]), 'image_shift_y', LOG_FORMAT_SHIFT_Y)
        mylog(float(tar_vc.tilt), 'image_tilt', LOG_FORMAT_TILT)
      if hasattr(tar_vc, 'sample_corners'):
        mylog(int(tar_vc.sample_corners.shape[0]), 'corners', LOG_FORMAT_CORNER)
      if hasattr(tar_vc, 'edges'):
        mylog(int(tar_vc.edges.shape[0]), 'edges', LOG_FORMAT_EDGE)
      if hasattr(tar_vc, 'msg') and tar_vc.msg is not None:
        mylog(tar_vc.msg, 'msg', LOG_FORMAT_VC_MSG)

    if tar_ls is not None:
      if hasattr(tar_ls, 'check_low_freq') and tar_ls.check_low_freq:
        mylog(float(tar_ls.response), 'ls_low_freq', LOG_FORMAT_LS_LOW_FREQ)
      if hasattr(tar_ls, 'lowest_ratio'):
        mylog(float(tar_ls.lowest_ratio), 'ls_lowest_ratio',
              LOG_FORMAT_LS_RATIO)
      if hasattr(tar_ls, 'msg') and tar_ls.msg is not None:
        mylog(tar_ls.msg, 'msg', LOG_FORMAT_LS_MSG)

    if tar_mtf is not None:
      if hasattr(tar_mtf, 'mtf'):
        mylog(float(tar_mtf.mtf), 'median_MTF', LOG_FORMAT_MTF_MEDIAN)
      if hasattr(tar_mtf, 'min_mtf'):
        mylog(float(tar_mtf.min_mtf), 'lowest_MTF', LOG_FORMAT_MTF_LOWEST)
      if hasattr(tar_mtf, 'msg') and tar_mtf.msg is not None:
        mylog(tar_mtf.msg, 'msg', LOG_FORMAT_MTF_MSG)

    event_log.Log(EVENT_IQ_DATA, **IQ_data)

  def _FlushEventLogs(self):
    if self.data_method == DataMethod.SF:
      goofy = state.get_instance()
      goofy.FlushEventLogs()

  def _FormatOrderedDict(self, ordered_dict):
    l = ['{']
    l += ["  '%s': %s," % (key, ordered_dict[key]) for key in ordered_dict]
    l.append('}')
    return '\n'.join(l)

  def _SetupFixture(self):
    """Initialize the communication with the fixture."""
    try:
      self.chamber.Connect()
    except Exception as e:
      self._Log(str(e))
      self._Log('Failed to initialize the test fixture.')
      return False
    self._Log('Test fixture successfully initialized.')
    return True

  def _OnUSBInsertion(self, dev_path):
    self.usb_dev_path = dev_path
    self.usb_ready_event.set()
    self.delegator.ui.CallJSFunction('UpdateUSBStatus', True)

  def _OnUSBRemoval(self, dev_path):
    del dev_path  # Unused.
    self.usb_ready_event.clear()
    self.usb_dev_path = None
    self.delegator.ui.CallJSFunction('UpdateUSBStatus', False)

  def _OnU2SInsertion(self, _):
    if self.params:
      cnt = 0
      while not self._SetupFixture():
        cnt += 1
        if cnt >= self.chamber_n_retries:
          self.delegator.ui.CallJSFunction('UpdateFixtureStatus', False)
          return
        time.sleep(self.chamber_retry_delay)
      self.delegator.ui.CallJSFunction('UpdateFixtureStatus', True)

  def _OnU2SRemoval(self, _):
    if self.params:
      self.delegator.ui.CallJSFunction('UpdateFixtureStatus', False)


class CameraFixture(unittest.TestCase):
  """Camera fixture main class."""
  ARGS = [
      # main test type
      Arg('test_type', str, 'What to test. '
          'Supported types: Calibration, LensShading, and IQ.'),

      # Some options
      Arg('auto_mode', bool, 'Automatically start and end the test.',
          default=False),

      # chamber connection
      Arg('control_chamber', bool, 'Whether or not to control the chart in the '
          'light chamber.', default=False),
      Arg('assume_chamber_connected', bool, 'Assume chamber is connected on '
          'test startup. This is useful when running fixture-based testing. '
          "The OP won't have to reconnect the fixture everytime.",
          default=False),
      Arg('chamber_conn_params', (dict, str), 'Chamber connection parameters, '
          "either a dict or 'default'", default=None, optional=True),
      Arg('chamber_cmd', dict, 'A mapping between charts listed in '
          'LightChamber.Charts and a list of tuple (cmd, response) required to '
          "activate the chart. 'response' can be None to disable checking.",
          default=None, optional=True),
      Arg('chamber_n_retries', int, 'Number of retries when connecting.',
          default=10),
      Arg('chamber_retry_delay', int, 'Delay between connection retries.',
          default=2),

      # test environment
      Arg('fixture_type', str, 'Type of the light chamber/panel. '
          'Supported types: FullChamber, ABChamber, ModuleChamber, '
          'Panel.'),
      Arg('test_chart_version', str, 'Version of the test chart. '
          'Supported types: A, B, White', optional=True),
      Arg('mock_mode', bool, 'Mock mode allows testing without a fixture.',
          default=False),
      Arg('device_index', int, 'Index of camera video device. '
          '(-1 to auto pick video device by OpenCV).', default=-1),
      Arg('capture_resolution', tuple, 'A tuple (x-res, y-res) indicating the '
          'image capture resolution to use.', optional=True),
      Arg('resize_ratio', float, 'The resize ratio of the captured image '
          'displayed on preview.', default=1.0),

      # when test_type = Calibration
      Arg('calibration_shift', float, 'Max image shift allowed ',
          default=0.002),
      Arg('calibration_tilt', float, 'Max image tilt allowed ', default=0.05),

      # when test_type = LensShading
      Arg('lens_shading_ratio', float, 'Max len shading ratio allowed.',
          default=0.20),
      Arg('lens_shading_timeout_secs', int, 'Timeout in seconds.', default=20),

      # when test_type = IQ
      Arg('data_method', str, 'How to read parameters and save test results. '
          'Supported types: Simple, Shopfloor, and USB.', default='USB'),
      Arg('param_pathname', str, 'Pathname of parameter file on '
          'USB drive or shopfloor.', default='camera.params'),
      Arg('local_ip', str, 'Local IP address for connecting shopfloor. '
          'when data_method = Shopfloor. Set as None to use DHCP.',
          default=None, optional=True),
      Arg('param_dict', dict, 'The parameters dictionary. '
          'when data_method = Simple.',
          default=None, optional=True),

      # when test_type = IQ
      Arg('IQ_save_good_image', bool, 'Stores the images that pass IQ test on '
          'USB drive or shopfloor.', default=False),
      Arg('IQ_save_bad_image', bool, 'Stores the images that fail IQ test on '
          'USB drive or shopfloor.', default=True),
  ]

  # self.args.test_type => TestType
  TEST_TYPES = {
      'Calibration': TestType.CALI,
      'LensShading': TestType.LS,
      'IQ': TestType.IQ
  }

  # self.args.fixture_type => Fixture
  FIXTURE_TYPES = {
      'FullChamber': Fixture.FULL,
      'ABChamber': Fixture.AB,
      'ModuleChamber': Fixture.MODULE,
      'Panel': Fixture.PANEL,
  }

  # self.args.data_method => DataMethod
  DATA_METHODS = {
      'Simple': DataMethod.SIMPLE,
      'USB': DataMethod.USB,
      'Shopfloor': DataMethod.SF
  }

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.internal_queue = Queue.Queue()
    self.camera_dev = self.dut.GetCameraDevice(self.args.device_index)

    # pylint: disable=no-member
    os.chdir(os.path.join(os.path.dirname(__file__), '%s_static' %
                          self.test_info.pytest_name))

    self.test_type = CameraFixture.TEST_TYPES[self.args.test_type]
    self.fixture_type = CameraFixture.FIXTURE_TYPES[self.args.fixture_type]

    # Check test type and fixture type.
    assert bool(self.fixture_type == Fixture.PANEL) == bool(
        self.test_type in [TestType.LS])
    assert bool(self.args.test_chart_version == 'White') == bool(
        self.test_type == TestType.LS)
    assert (self.args.data_method != 'Simple' or
            self.args.param_dict is not None)

    if self.args.chamber_conn_params == 'default':
      chamber_conn_params = CHAMBER_CONN_PARAMS_DEFAULT
    else:
      chamber_conn_params = self.args.chamber_conn_params

    fixture_conn = None
    if self.args.control_chamber:
      if self.args.mock_mode:
        script = dict([(k.strip(), v.strip()) for k, v in
                       reduce(lambda a, b: a + b,
                              self.args.chamber_cmd.values(), [])])
        fixture_conn = fixture_connection.MockFixtureConnection(script)
      else:
        fixture_conn = fixture_connection.SerialFixtureConnection(
            **chamber_conn_params)

    self.chamber = light_chamber.LightChamber(
        test_chart_version=self.args.test_chart_version,
        mock_mode=self.args.mock_mode,
        device_index=self.args.device_index,
        image_resolution=self.args.capture_resolution,
        fixture_conn=fixture_conn,
        fixture_cmd=self.args.chamber_cmd)

    self.ui = test_ui.UI()
    self.ui.AddEventHandler(
        'start_test_button_clicked',
        lambda js_args: self.PostInternalQueue(EventType.START_TEST, js_args))
    self.ui.AddEventHandler(
        'exit_test_button_clicked',
        lambda _: self.PostInternalQueue(EventType.EXIT_TEST))
    self.ui.AddEventHandler(
        'sn_input_box_on_input',
        lambda js_args: self.PostInternalQueue(EventType.VALIDATE_SN, js_args))
    self.ui.BindKey(
        test_ui.ESCAPE_KEY,
        lambda _: self.PostInternalQueue(EventType.EXIT_TEST))

  def runTest(self):
    self.ui.RunInBackground(self._runTest)
    self.ui.Run()

  def _runTest(self):
    if self.test_type == TestType.CALI:
      self._RunCalibration()
    elif self.test_type == TestType.LS:
      self._RunLensShadingTest()
    elif self.test_type == TestType.IQ:
      self._RunIQTest()
    else:
      raise ValueError('Unsupported test type.')

  def _RunCalibration(self):
    """Main routine for camera fixture calibration.

    The test keeps reading images from camera and updating preview on
    screen. For each frame, it checks the image shift and image tilt.

    If the shift and tilt meet the criteria, it will prompt PASS. Then user can
    click 'Exit Test' button.  Otherwise, it prompts FAIL, and user needs to
    rotate and move the test chart to align it with the golden sample camera.
    """
    self.ui.CallJSFunction('InitForCalibration')
    self.ui.CallJSFunction('UpdateTextLabel', MSG_TITLE_CALIBRATION,
                           ID_MAIN_SCREEN_TITLE)

    ref_data = camperf.PrepareTest(self.chamber.GetTestChartFile())
    frame_delay = 1.0 / CALIBRATION_FPS

    if self.args.control_chamber:
      self.chamber.SetChart(light_chamber.LightChamber.Charts.SFR)

    self.chamber.EnableCamera()
    try:
      while True:
        img, gray_img = self.chamber.ReadSingleFrame()
        success, tar_vc = camperf.CheckVisualCorrectness(
            sample=gray_img, ref_data=ref_data,
            max_image_shift=self.args.calibration_shift,
            max_image_tilt=self.args.calibration_tilt,
            corner_only=True)

        renderer.DrawVC(img, success, tar_vc)
        self.ShowImage(img, ID_PREVIEW_IMAGE)

        # Logs Visual-Correctness results to factory.log in case when external
        # display is unavailable.
        log_msg = 'PASS: ' if success else 'FAIL: '
        if hasattr(tar_vc, 'shift'):
          log_msg += ('Shift=%.3f (%.01f, %0.01f) ' % (
              tar_vc.shift, tar_vc.v_shift[0], tar_vc.v_shift[1]))
          log_msg += ('Tilt=%0.2f' % tar_vc.tilt)
        else:
          log_msg += 'Incorrect Chart'

        self.ShowTestStatus(i18n.NoTranslation(log_msg), style=(
            STYLE_PASS if success else STYLE_FAIL))
        logging.info(log_msg)

        event = self.PopInternalQueue(wait=False)
        if event and event.event_type == EventType.EXIT_TEST:
          if success:
            self.ui.Pass()
          else:
            self.fail('Failed to meet the calibration criteria.')
          break

        time.sleep(frame_delay)
    finally:
      self.chamber.DisableCamera()

  def _RunLensShadingTest(self):
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
    self.ui.CallJSFunction('InitForLensShadingTest')
    self.ui.CallJSFunction('UpdateTextLabel', MSG_TITLE_LENS_SHADING_TEST,
                           ID_MAIN_SCREEN_TITLE)

    frame_delay = 1.0 / LENS_SHADING_FPS
    end_time = time.time() + self.args.lens_shading_timeout_secs

    if self.args.control_chamber:
      self.chamber.SetChart(light_chamber.LightChamber.Charts.WHITE)

    self.chamber.EnableCamera()
    try:
      while True:
        remaining_time = end_time - time.time()

        img, gray_img = self.chamber.ReadSingleFrame()

        self.ShowImage(img, ID_PREVIEW_IMAGE)

        success, tar_ls = camperf.CheckLensShading(
            sample=gray_img, max_shading_ratio=self.args.lens_shading_ratio,
            check_low_freq=False)
        ls_ratio = float(1.0 - tar_ls.lowest_ratio)

        log_msg = 'PASS: ' if success else 'FAIL: '
        log_msg += 'Remaining %d s. Shading ratio=%.3f ' % (
            remaining_time, ls_ratio)
        self.ShowTestStatus(i18n.NoTranslation(log_msg), style=(
            STYLE_PASS if success else STYLE_FAIL))

        event = self.PopInternalQueue(wait=False)
        if (remaining_time <= 0 or success or
            (event and event.event_type == EventType.EXIT_TEST)):
          event_log.Log(EVENT_LENS_SHADING, lens_shading_ratio=ls_ratio)
          if success:
            self.ui.Pass()
          else:
            self.fail(
                'Failed to meet the lens shading criteria with '
                'ratio=%f (> %f).' % (ls_ratio, self.args.lens_shading_ratio))
          break

        time.sleep(frame_delay)
    finally:
      self.chamber.DisableCamera()

  def _RunIQTest(self):
    """Main routine for IQ (Image Quality) test."""
    delegate = _IQTestDelegate(
        delegator=self,
        mock_mode=self.args.mock_mode,
        chamber=self.chamber,
        fixture_type=self.fixture_type,
        control_chamber=self.args.control_chamber,
        chamber_n_retries=self.args.chamber_n_retries,
        chamber_retry_delay=self.args.chamber_retry_delay,
        data_method=self.DATA_METHODS[self.args.data_method],
        local_ip=self.args.local_ip,
        param_pathname=self.args.param_pathname,
        param_dict=self.args.param_dict,
        save_good_image=self.args.IQ_save_good_image,
        save_bad_image=self.args.IQ_save_bad_image)

    self.ui.CallJSFunction('InitForTest', self.args.data_method,
                           self.args.control_chamber)

    self.ui.CallJSFunction('UpdateTextLabel', MSG_TITLE_IQ_TEST,
                           ID_MAIN_SCREEN_TITLE)

    delegate.LoadParamsAndShowTestScreen()

    if self.args.assume_chamber_connected:
      self.ui.CallJSFunction('UpdateFixtureStatus', True)

    if self.args.auto_mode and delegate.params['cam_sn']['auto_read']:
      self.PostInternalQueue(EventType.START_TEST)

    # Loop to repeat the test until user chooses 'Exit Test'.  For module-level
    # testing, it may test thousands of DUTs without leaving the test. The test
    # passes or fails depending on the last test result.
    success, fail_cause = False, None
    while True:
      event = self.PopInternalQueue(wait=True)
      if event.event_type == EventType.START_TEST:
        with leds.Blinker(LED_PATTERN):
          input_sn = ''
          if event.aux_data is not None:
            input_sn = event.aux_data.data.get('input_sn', '')

          # pylint: disable=unpacking-non-sequence
          success, fail_cause = delegate.RunTest(input_sn)

        if success:
          self.ShowTestStatus(i18n.NoTranslation('Camera: PASS'),
                              style=STYLE_PASS)
        else:
          self.ShowTestStatus(
              i18n.NoTranslation('Camera: FAIL %r' % fail_cause),
              style=STYLE_FAIL)
      elif event.event_type == EventType.EXIT_TEST:
        if success:
          self.ui.Pass()
        else:
          self.fail('Test Camera failed - fail cause = %r.' % fail_cause)
        break
      elif event.event_type == EventType.VALIDATE_SN:
        if event.aux_data is not None:
          input_sn = event.aux_data.data.get('input_sn', '')
          self.ui.CallJSFunction('UpdateStartTestButtonStatus',
                                 self.camera_dev.IsValidSerialNumber(input_sn))
      else:
        raise ValueError('Invalid event type.')

  def PostInternalQueue(self, event_type, aux_data=None):
    """Posts an event to internal queue.

    Args:
      event_type: EventType.
      aux_data: Extra data.
    """
    self.internal_queue.put(InternalEvent(event_type, aux_data))

  def PopInternalQueue(self, wait):
    """Pops an event from internal queue.

    Args:
      wait: A bool flag to wait forever until internal queue has something.

    Returns:
      The first InternalEvent in internal queue. None if 'wait' is False and
      internal queue is empty.
    """
    if wait:
      return self.internal_queue.get(block=True, timeout=None)
    else:
      try:
        return self.internal_queue.get_nowait()
      except Queue.Empty:
        return None

  def ShowTestStatus(self, msg, style=STYLE_INFO):
    """Shows test status.

    Args:
      msg: i18n text.
      style: CSS style.
    """
    label = i18n_test_ui.MakeI18nLabelWithClass(msg, style)
    self.ui.CallJSFunction('UpdateTextLabel', label, ID_TEST_STATUS)

  def ShowImage(self, img, html_id):
    """Shows displayed image.

    Args:
      img: OpenCV image object.
      html_id: Image ID in HTML.
    """
    assert img is not None, 'empty image data'
    resized_img = cv2.resize(
        img, None, fx=self.args.resize_ratio, fy=self.args.resize_ratio,
        interpolation=cv2.INTER_AREA)
    data = base64.b64encode(camera_utils.EncodeCVImage(resized_img, '.jpg'))
    data_len = len(data)

    # Send the data in smaller packets due to event message size limit.
    try:
      self.ui.CallJSFunction('ClearImageData', '')
      p = 0
      while p < data_len:
        if p + MAX_MESSAGE_SIZE >= data_len:
          self.ui.CallJSFunction('AddImageData', data[p:data_len])
          p = data_len
        else:
          self.ui.CallJSFunction('AddImageData', data[p:p + MAX_MESSAGE_SIZE])
          p += MAX_MESSAGE_SIZE
      self.ui.CallJSFunction('UpdateAndShowImage', html_id)
    except AttributeError:
      # The websocket is closed because test has passed/failed.
      pass

  def HideImage(self, html_id):
    """Hides image.

    Args:
      html_id: Image ID in HTML.
    """
    self.ui.CallJSFunction('HideImage', html_id)

  def ShowProgressBar(self, completion_ratio):
    """Update the progress bar.

    Args:
      completion_ratio: Completion ratio.
    """
    percent = int(round(completion_ratio * 100))
    self.ui.CallJSFunction('UpdateProgressBar', '%d%%' % percent)
