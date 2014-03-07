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
  - Panel: a simple test chart panel for standalone lens shading and QR test.

Test types:
  - When fixture_type == {Full|AB|Module}Chamber:
    - Calibration: calibrates light chamber and test chart to align with the
                   golden sample (only checking image shift and tilt).
    - IQ (Image Quality): checks IQ factors such as MTF (sharpness), lens
                          shading, image shift, and image tilt in one test.

  - When fixture_type == Panel
    - LensShading: checks lens shading ratio (usually fails when camera module
                   is not precisely aligned with the view hole on bezel).
    - QR: scans QR code. QR bar code test is intended for a fixtureless camera
          test. We only need a piece of paper to verify if camera is functional
          without human judgement. But the test coverage is not as complete
          as IQ test.

Test chart versions:
  - A: 7x11 blocks. Used for 720p camera or similar aspect ratio.
  - B: 7x9 blocks. Used for VGA camera or similar aspect ratio.
  - White: All white. Used for standalone lens shading test.
  - QR: QR code.

Hot keys:
  - Press Enter or Space keys to start the IQ test
  - Press ESC to leave the test.

[IQ Test Only]

Data methods for IQ test:
  - Simple: read parameters from 'IQ_param_dict' argument, but skips saving
            test results.
  - USB: read parameter file from USB drive, and saves test results in USB drive
         in subfolders ordered by date.
  - Shopfloor: read param file from shopfloor, and saves test results in
               shopfloor aux_logs. This is recommended over USB when there is
               Shopfloor environment because USB drive is not reliable.

Test parameters for IQ test:
  - Please check camera_fixture_static/camera.params.sample

Analysis of saved test data from IQ test:
  - Use py/test/fixture/camera/analysis/analyze_camera_fixture_data.py

[Usage Examples]

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

  # Standalone QR code scan.
  OperatorTest(
    id='QRScan',
    pytest_name='camera_fixture',
    dargs={
      'mock_mode': False,
      'test_type': 'QR',
      'fixture_type': 'Panel',
      'test_chart_version': 'QR',
      'capture_resolution': (640, 480),
      'resize_ratio': 0.5,
      'QR_string': 'Hello ChromeOS!'})

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
           'IQ_data_method': 'Shopfloor',
           'IQ_param_pathname': 'camera/camera.params.FATP',
           'IQ_local_ip': None})

  # IQ (Image Quality) test with USB drive.
  OperatorTest(
    id='ImageQualityUSB',
    pytest_name='camera_fixture',
    dargs={'mock_mode': False,
           'test_type': 'IQ',
           'fixture_type': 'ModuleChamber',
           'test_chart_version': 'A',
           'capture_resolution': (1280, 720),
           'IQ_data_method': 'USB',
           'IQ_param_pathname': 'camera.params'}),

"""

import base64
from collections import namedtuple, OrderedDict
try:
  import cv2  # pylint: disable=F0401
except ImportError:
  pass
import datetime
import logging
import numpy as np
import os
import Queue
import re
import threading
import time
import unittest
import xmlrpclib

from cros.factory import event_log
from cros.factory.test import factory
from cros.factory.test import leds
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
import cros.factory.test.fixture.camera.barcode as barcode
from cros.factory.test.fixture.camera.camera_utils import EncodeCVImage
from cros.factory.test.fixture.camera.light_chamber import (
    LightChamber, LightChamberError)
import cros.factory.test.fixture.camera.perf_tester as camperf
import cros.factory.test.fixture.camera.renderer as renderer
from cros.factory.test.media_util import MediaMonitor, MountedMedia
from cros.factory.test.utils import Enum
from cros.factory.utils import net_utils


# Delay between each frame during calibration.
CALIBRATION_FPS = 15
# Delay between each frame during lens shading test.
LENS_SHADING_FPS = 5
# Delay between each frame during QR Code scanning.
QR_CODE_FPS = 10

# TODO(jchuang): import from event.py
# Upper limit of message size in JavaScript RPC.
MAX_MESSAGE_SIZE = 60000


# Test stages in IQ test. Prefix them with 'cam_' to help query in Minijack.
STAGE00_START = 'cam_start'  # start test
STAGE10_SN = 'cam_sn'  # check serial number
STAGE15_FW = 'cam_fw'  # check firmware
STAGE20_INIT = 'cam_init'  # init camera and try to read one image
STAGE25_AWB = 'cam_awb'  # AWB and AE
STAGE30_IMG = 'cam_img'  # capture low-noises image

STAGE50_VC = 'cam_vc'  # visual correctness, image shift/tilt
STAGE60_LS = 'cam_ls'  # lens shading
STAGE70_MTF = 'cam_mtf'  # MTF / sharpness
# TODO: STAGE80_ALS
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
MSG_TITLE_CALIBRATION = test_ui.MakeLabel(
    'Camera Fixture Calibration', u'相机制具校正')
MSG_TITLE_LENS_SHADING_TEST = test_ui.MakeLabel(
    'Camera Lens Shading Test', u'相机镜头黑点测试')
MSG_TITLE_QR_CODE_TEST = test_ui.MakeLabel(
    'Scan QR Code', u'扫描QR码')
MSG_TITLE_IQ_TEST = test_ui.MakeLabel(
    'Camera Image Quality Test', u'相机影像品质测试')


# Test stage => (English message, Chinese message).
MSG_TEST_STATUS = {
  STAGE00_START: ('Starting the test', u'开始测试'),
  STAGE10_SN: ('Reading serial number', u'读取序号'),
  STAGE15_FW: ('Checking firmware version', u'检查韧体版本'),
  STAGE20_INIT: ('Initializing camera', u'初始化摄像头'),
  STAGE25_AWB: ('Adjusting white balance', u'白平衡调试'),
  STAGE30_IMG: ('Reading test image', u'读取测试影像'),
  STAGE50_VC: ('Locating test pattern', u'定位测试图样'),
  STAGE60_LS: ('Checking vignetting level', u'检测影像暗角'),
  STAGE70_MTF: ('Checking image sharpness', u'检测影像清晰度'),
  STAGE90_END: ('All tests are complete', u'测试已全部完成'),
  STAGE100_SAVED: ('Test data saved', u'记录档已写入'),
}


# LED pattern.
LED_PATTERN = ((leds.LED_NUM|leds.LED_CAP, 0.05), (0, 0.05))


# Data structures.
TestType = Enum(['CALI', 'LS', 'QR', 'IQ'])
Fixture = Enum(['FULL', 'AB', 'MODULE', 'PANEL'])
DataMethod = Enum(['SIMPLE', 'USB', 'SF'])
EventType = Enum(['START_TEST', 'EXIT_TEST'])
TestStatus = Enum(['PASSED', 'FAILED', 'UNTESTED', 'NA'])

InternalEvent = namedtuple('InternalEvent', 'event_type aux_data')


# Root failure causes (used for quick troubleshooting at factory).
FAIL_SN = 'SerialNumber'  # Missing camera or bad serial number.
FAIL_FIRMWARE = 'Firmware'  # Wrong firmware version.
FAIL_BAD_CAMERA = 'BadCamera'  # Fail to read image from camera.
FAIL_WRONG_IMAGE = 'WrongImage'  # Image doesn't contain a valid test chart.
FAIL_IMAGE_SHIFT = 'Shift'  # Image shift is too large.
FAIL_IMAGE_TILT = 'Tilt'  # Image tilt is too large.
FAIL_LENS_SHADING = 'LensShading'  # Lens shading is over-limits.
FAIL_MTF = 'MTF'  # Image sharpness is too low.
FAIL_USB = 'USB'  # Fail to save to USB.


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


class _IQTestDelegate(object):
  """Delegate class for IQ (image quality) test.

  We use four types of logging in IQ test:

    1. factory console (factory.console.info())
    2. factory.log (self._Log())
    3. Save raw data to USB drive or shopfloor aux_logs folder (self._Log() and
       self._SaveTestData())
    4. Event log (event_log.Log())

  It has three public methods:
    - __init__()
    - LoadParamsAndShowTestScreen()
    - IQTest()

  Usage Example:

    delegate = _IQTestDelegate(...)
    delegate.LoadParamsAndShowTestScreen()
    while ...: # loop test iterations
      delegate.IQTest()

  """

  def __init__(self, delegator, chamber, fixture_type, data_method, local_ip,
               param_pathname, param_dict, save_good_image, save_bad_image):
    """Initalizes _IQTestDelegate.

    Args:
      delegator: Instance of CameraFixture.
      chamber: Instance of LightChamber.
      fixture_type: Fixture enum.
      data_method: DataMethod enum.
      local_ip: Check CameraFixture.ARGS for detailed description.
      param_pathname: ditto.
      param_dict: ditto.
      save_good_image: ditto.
      save_bad_image: ditto.
    """
    self.delegator = delegator
    self.chamber = chamber
    self.fixture_type = fixture_type

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
    self.ref_data = camperf.PrepareTest(chamber.GetTestChartFile())
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
    if self.data_method == DataMethod.USB:
      self.params = self._LoadParamsFromUSB()
    elif self.data_method == DataMethod.SF:
      self.params = self._LoadParamsFromShopfloor()

    # Basic pre-processing of the parameters.
    self._Log('Parameter version: %s\n' % self.params['version'])
    self._CalculateTiming()

    self.delegator.ui.CallJSFunction('ShowMainTestScreen',
                                     not self.params['cam_sn']['sn_auto_read'],
                                     self.params['cam_sn']['sn_format'],
                                     self.params['ui']['ignore_enter_key'])

  def _LoadParamsFromUSB(self):
    """Loads parameters from USB drive."""
    self.usb_ready_event = threading.Event()
    MediaMonitor().Start(on_insert=self._OnUSBInsertion,
                         on_remove=self._OnUSBRemoval)

    while self.usb_ready_event.wait():
      with MountedMedia(self.usb_dev_path, 1) as mount_point:
        pathname = os.path.join(mount_point, self.param_pathname)
        try:
          with open(pathname , 'r') as f:
            return eval(f.read())
        except IOError as e:
          self._Log('Error: fail to read %r: %r' % (pathname, e))
      time.sleep(0.5)

  def _LoadParamsFromShopfloor(self):
    """Loads parameters from shopfloor."""
    net_utils.PrepareNetwork(ip=self.local_ip, force_new_ip=True)

    factory.console.info('Reading %s from shopfloor', self.param_pathname)
    shopfloor_client = shopfloor.GetShopfloorConnection()
    return eval(shopfloor_client.GetParameter(self.param_pathname).data)

  def _CalculateTiming(self):
    """Calculates the timing of each test stage to self.timing."""
    chk_point = self.params['chk_point']
    cumsum = np.cumsum([d for _, d in chk_point])
    total_time = cumsum[-1]
    for i in xrange(len(chk_point)):
      if i > 0:
        self.timing[chk_point[i][0]] = cumsum[i - 1] / total_time
      else:
        self.timing[chk_point[i][0]] = 0

  def IQTest(self, input_sn):
    """Runs IQ (Image Quality) test.

    Args:
      input_sn: Serial number input on screen.
    """
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
        self.chamber.EnableCamera()
        self.chamber.ReadSingleFrame(return_gray_image=False)  # test one image
        update_status(True)

        update_progress(STAGE25_AWB)
        time.sleep(self.params['cam_img']['buf_time'])
        update_status(True)

        update_progress(STAGE30_IMG)
        self.original_img, gray_img = self.chamber.ReadLowNoisesFrame(
            self.params['cam_img']['n_samples'])
        update_status(True)
        self._UpdateOriginalImage()
      except LightChamberError as e:
        update_status(False)
        self._Log('Error: cannot read image %r' % e)
        return False, FAIL_BAD_CAMERA
      finally:
        # It's important to close camera device even with intermittent error.
        self.chamber.DisableCamera()

      # (4) Visual correctness, image shift and tilt.
      update_progress(STAGE50_VC)
      success, tar_vc = camperf.CheckVisualCorrectness(gray_img, self.ref_data,
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
      success, tar_ls = camperf.CheckLensShading(gray_img,
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
      self._CollectIQLogs(test_status, tar_vc, tar_ls, tar_mtf)
      self._SaveTestData(test_status[STAGE90_END] == TestStatus.PASSED)
      update_progress(STAGE100_SAVED)

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
    msg, msg_zh = MSG_TEST_STATUS[test_stage]
    self.delegator.ShowTestStatus(msg, msg_zh)
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
        data_files.append((log_prefix + '.bmp',
                           EncodeCVImage(self.original_img, '.bmp')))
      if self.analyzed_img is not None:
        data_files.append((log_prefix + '.jpg',
                           EncodeCVImage(self.analyzed_img, '.jpg')))

    # Skip saving test data for DataMethod.SIMPLE.
    if self.data_method == DataMethod.USB:
      self._SaveTestDataToUSB(data_files)
    elif self.data_method == DataMethod.SF:
      self._SaveTestDataToShopfloor(data_files)

  def _GetLogFilePrefix(self):
    if self.fixture_type == Fixture.FULL:
      device_sn = shopfloor.get_serial_number() or 'MISSING_SN'
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
    with MountedMedia(self.usb_dev_path, 1) as mount_point:
      folder_path = os.path.join(mount_point,
                                 datetime.date.today().strftime('%Y%m%d'))
      if os.path.exists(folder_path):
        if not os.path.isdir(folder_path):
          factory.console.info('Error: fail to create folder %r' % folder_path)
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
    net_utils.PrepareNetwork(ip=self.local_ip, force_new_ip=False)
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
    if self.params['cam_sn']['sn_auto_read']:
      success, input_sn = self._ReadSysfs(
          self.params['cam_sn']['sn_sysfs_path'])
    else:
      success = True

    if success:
      self.module_sn = input_sn
      self._Log('Serial number: %s' % self.module_sn)
      if not re.match(self.params['cam_sn']['sn_format'], self.module_sn):
        success = False
        self._Log('Error: invalid serial number.')

    return success

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
    try:
      with open(pathname, 'r') as f:
        read_data = f.read().rstrip()
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

  def _FormatOrderedDict(self, ordered_dict):
    l = ['{']
    l += ["  '%s': %s," % (key, ordered_dict[key]) for key in ordered_dict]
    l.append('}')
    return '\n'.join(l)

  def _OnUSBInsertion(self, dev_path):
    self.usb_dev_path = dev_path
    self.usb_ready_event.set()
    self.delegator.ui.CallJSFunction('UpdateUSBStatus', True)

  def _OnUSBRemoval(self, dummy_dev_path):
    self.usb_ready_event.clear()
    self.usb_dev_path = None
    self.delegator.ui.CallJSFunction('UpdateUSBStatus', False)

class CameraFixture(unittest.TestCase):
  """Camera fixture main class."""
  ARGS = [
    # main test type
    Arg('test_type', str, 'What to test. '
        'Supported types: Calibration, LensShading, QR, and IQ.'),

    # test environment
    Arg('fixture_type', str, 'Type of the light chamber/panel. '
        'Supported types: FullChamber, ABChamber, ModuleChamber, '
        'Panel.'),
    Arg('test_chart_version', str, 'Version of the test chart. '
        'Supported types: A, B, White, QR'),
    Arg('mock_mode', bool, 'Mock mode allows testing without a fixture.',
        default=False),
    Arg('device_index', int, 'Index of camera video device. '
        '(-1 to auto pick video device by OpenCV).', default=-1),
    Arg('capture_resolution', tuple, 'A tuple (x-res, y-res) indicating the '
        'image capture resolution to use.'),
    Arg('resize_ratio', float, 'The resize ratio of the captured image '
        'displayed on preview.', default=1.0),

    # when test_type = Calibration
    Arg('calibration_shift', float, 'Max image shift allowed ', default=0.002),
    Arg('calibration_tilt', float, 'Max image tilt allowed ', default=0.05),

    # when test_type = LensShading
    Arg('lens_shading_ratio', float, 'Max len shading ratio allowed.',
        default=0.20),
    Arg('lens_shading_timeout_secs', int, 'Timeout in seconds.', default=20),

    # when test_type = QR
    Arg('QR_string', str, 'Encoded string in QR code.', default=None,
        optional=True),
    Arg('QR_timeout_secs', int, 'Timeout in seconds.', default=20),

    # when test_type = IQ
    Arg('IQ_data_method', str, 'How to read parameters and save test results. '
        'Supported types: Simple, Shopfloor, and USB.', default='USB'),
    Arg('IQ_param_pathname', str, 'Pathname of parameter file on '
        'USB drive or shopfloor.', default='camera.params'),
    Arg('IQ_save_good_image', bool, 'Stores the images that pass IQ test on '
        'USB drive or shopfloor.', default=False),
    Arg('IQ_save_bad_image', bool, 'Stores the images that fail IQ test on '
        'USB drive or shopfloor.', default=True),
    Arg('IQ_local_ip', str, 'Local IP address for connecting shopfloor. '
        'when IQ_data_method = Shopfloor. Set as None to use DHCP.',
        default=None, optional=True),
    Arg('IQ_param_dict', dict, 'The parameters dictionary. '
        'when IQ_data_method = Simple.',
        default=None, optional=True),
  ]

  # self.args.test_type => TestType
  TEST_TYPES = {
    'Calibration': TestType.CALI,
    'LensShading': TestType.LS,
    'QR': TestType.QR,
    'IQ': TestType.IQ,
  }

  # self.args.fixture_type => Fixture
  FIXTURE_TYPES = {
    'FullChamber': Fixture.FULL,
    'ABChamber': Fixture.AB,
    'ModuleChamber': Fixture.MODULE,
    'Panel': Fixture.PANEL
  }

  # self.args.IQ_data_method => DataMethod
  DATA_METHODS = {
    'Simple': DataMethod.SIMPLE,
    'USB': DataMethod.USB,
    'Shopfloor': DataMethod.SF
  }

  def setUp(self):
    self.internal_queue = Queue.Queue()

    os.chdir(os.path.join(os.path.dirname(__file__), '%s_static' %
                          self.test_info.pytest_name)) # pylint: disable=E1101

    self.test_type = CameraFixture.TEST_TYPES[self.args.test_type]
    self.fixture_type = CameraFixture.FIXTURE_TYPES[self.args.fixture_type]

    # Check test type and fixture type.
    assert bool(self.fixture_type == Fixture.PANEL) == bool(
        self.test_type in [TestType.LS, TestType.QR])
    assert bool(self.args.test_chart_version == 'QR') == bool(
            self.test_type == TestType.QR)
    assert bool(self.args.test_chart_version == 'White') == bool(
            self.test_type == TestType.LS)
    assert (self.args.IQ_data_method != 'Simple' or
            self.args.IQ_param_dict is not None)

    self.chamber = LightChamber(test_chart_version=self.args.test_chart_version,
                                mock_mode=self.args.mock_mode,
                                device_index=self.args.device_index,
                                image_resolution=self.args.capture_resolution)
    self.ui = test_ui.UI()
    self.ui.AddEventHandler(
        'start_test_button_clicked',
        lambda js_args: self._PostInternalQueue(EventType.START_TEST, js_args))
    self.ui.AddEventHandler(
        'exit_test_button_clicked',
        lambda _: self._PostInternalQueue(EventType.EXIT_TEST))
    self.ui.BindKey(
        test_ui.ESCAPE_KEY,
        lambda _: self._PostInternalQueue(EventType.EXIT_TEST))

  def runTest(self):
    ui_thread = self.ui.Run(blocking=False)

    if self.test_type == TestType.CALI:
      self._RunCalibration()
    elif self.test_type == TestType.LS:
      self._RunLensShadingTest()
    elif self.test_type == TestType.QR:
      self._RunQRCodeTest()
    elif self.test_type == TestType.IQ:
      self._RunIQTest()
    else:
      raise ValueError('Unsupported test type.')

    ui_thread.join()

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
          log_msg += ("Shift=%.3f (%.01f, %0.01f) " % (
              tar_vc.shift, tar_vc.v_shift[0], tar_vc.v_shift[1]))
          log_msg += ("Tilt=%0.2f" % tar_vc.tilt)
        else:
          log_msg += 'Incorrect Chart'

        self.ShowTestStatus(msg=log_msg, style=(
            STYLE_PASS if success else STYLE_FAIL))
        logging.info(log_msg)

        event = self._PopInternalQueue(wait=False)
        if event and event.event_type == EventType.EXIT_TEST:
          if success:
            self.ui.Pass()
          else:
            self.ui.Fail('Failed to meet the calibration criteria.')
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
        log_msg += "Remaining %d s. Shading ratio=%.3f " % (
            remaining_time, ls_ratio)
        self.ShowTestStatus(msg=log_msg, style=(
            STYLE_PASS if success else STYLE_FAIL))

        event = self._PopInternalQueue(wait=False)
        if (remaining_time <= 0 or success or
            (event and event.event_type == EventType.EXIT_TEST)):
          event_log.Log(EVENT_LENS_SHADING, lens_shading_ratio=ls_ratio)
          if success:
            self.ui.Pass()
          else:
            self.ui.Fail(
                'Failed to meet the lens shading criteria with '
                'ratio=%f (> %f).' % (ls_ratio, self.args.lens_shading_ratio))
          break

        time.sleep(frame_delay)
    finally:
      self.chamber.DisableCamera()

  def _RunQRCodeTest(self):
    """Main routine for standalone QR Code test.

    The test keeps reading images from camera and updating preview on screen. If
    it scans QR code correctly on a single frame, it will exit the test
    successfully. Otherwise, it will prompt FAIL. If the test doesn't pass
    before timeout, it will also fail.

    """
    self.ui.CallJSFunction('InitForQRCodeTest')
    self.ui.CallJSFunction('UpdateTextLabel', MSG_TITLE_QR_CODE_TEST,
                           ID_MAIN_SCREEN_TITLE)

    frame_delay = 1.0 / QR_CODE_FPS
    end_time = time.time() + self.args.QR_timeout_secs
    success = False

    self.chamber.EnableCamera()
    try:
      while True:
        remaining_time = end_time - time.time()
        img, _ = self.chamber.ReadSingleFrame(return_gray_image=False)
        self.ShowImage(img, ID_PREVIEW_IMAGE)

        scan_results = barcode.ScanQRCode(img)
        if len(scan_results) > 0:
          scanned_text = scan_results[0]
        else:
          scanned_text = None
        if scanned_text == self.args.QR_string:
          success = True

        log_msg = 'PASS: ' if success else 'FAIL: '
        log_msg += "Remaining %d s. Scanned %r, expecting %r" % (
            remaining_time, scanned_text, self.args.QR_string)
        self.ShowTestStatus(msg=log_msg, style=(
            STYLE_PASS if success else STYLE_FAIL))

        event = self._PopInternalQueue(wait=False)
        if (remaining_time <= 0 or success or
            (event and event.event_type == EventType.EXIT_TEST)):
          if success:
            self.ui.Pass()
          else:
            self.ui.Fail('Failed to scan QR code')
          break

        time.sleep(frame_delay)
    finally:
      self.chamber.DisableCamera()

  def _RunIQTest(self):
    """Main routine for IQ (Image Quality) test."""
    delegate = _IQTestDelegate(
        delegator=self, chamber=self.chamber,
        fixture_type=self.fixture_type,
        data_method=self.DATA_METHODS[self.args.IQ_data_method],
        local_ip=self.args.IQ_local_ip,
        param_pathname=self.args.IQ_param_pathname,
        param_dict=self.args.IQ_param_dict,
        save_good_image=self.args.IQ_save_good_image,
        save_bad_image=self.args.IQ_save_bad_image)

    self.ui.CallJSFunction('InitForIQTest', self.args.IQ_data_method)
    self.ui.CallJSFunction('UpdateTextLabel', MSG_TITLE_IQ_TEST,
                           ID_MAIN_SCREEN_TITLE)

    delegate.LoadParamsAndShowTestScreen()

    # Loop to repeat the test until user chooses 'Exit Test'.  For module-level
    # testing, it may test thousands of DUTs without leaving the test. The test
    # passes or fails depending on the last test result.
    success, fail_cause = False, None
    while True:
      event = self._PopInternalQueue(wait=True)
      if event.event_type == EventType.START_TEST:
        with leds.Blinker(LED_PATTERN):
          success, fail_cause = delegate.IQTest(
              input_sn=event.aux_data.data.get('input_sn', ''))

        if success:
          self.ShowTestStatus(msg='Camera: PASS', style=STYLE_PASS)
        else:
          self.ShowTestStatus(msg='Camera: FAIL %r' % fail_cause,
                              style=STYLE_FAIL)
      elif event.event_type == EventType.EXIT_TEST:
        if success:
          self.ui.Pass()
        else:
          self.ui.Fail('Camera IQ test failed - fail cause = %r.' % fail_cause)
        break
      else:
        raise ValueError('Invalid event type.')

  def _PostInternalQueue(self, event_type, aux_data=None):
    """Posts an event to internal queue.

    Args:
      event_type: EventType.
      aux_data: Extra data.
    """
    self.internal_queue.put(InternalEvent(event_type, aux_data))

  def _PopInternalQueue(self, wait):
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

  def ShowTestStatus(self, msg, msg_zh=None, style=STYLE_INFO):
    """Shows test status.

    Args:
      msg: English text.
      msg_zh: Chinese text.
      style: CSS style.
    """
    label = test_ui.MakeLabel(en=msg, zh=msg_zh, css_class=style)
    self.ui.CallJSFunction("UpdateTextLabel", label, ID_TEST_STATUS)

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
