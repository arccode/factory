# -*- coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests and calibrates ambient light sensor with fixture.

This test tests the ambient light sensor by setting different light
intensity in the light chamber. Calibration is done by comparing the light
intensity detected from the ALS sensor and the preset value.

Usage examples::

  # Saving parameter file in USB.
  OperatorTest(
    id='ALSCalibration',
    pytest_name='light_sensor_fixture',
    dargs=dict(
      data_method='USB',
      param_pathname='als.params'))

  # Saving parameter file in shopfloor.
  OperatorTest(
    id='ALSCalibration',
    pytest_name='light_sensor_fixture',
    dargs=dict(
      data_method='SF',
      param_pathname='als.params'
      shopfloor_ip='10.0.0.1'))
"""

from __future__ import print_function

from collections import namedtuple
import datetime
import logging
import os
import Queue
import re
import serial
import threading
import time
import traceback
import unittest
import xmlrpclib

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Arg
from cros.factory.test import factory
from cros.factory.test import leds
from cros.factory.test.media_util import MediaMonitor, MountedMedia
from cros.factory.test import network
from cros.factory.test import shopfloor
from cros.factory.test.serial_utils import OpenSerial, FindTtyByDriver
from cros.factory.test import test_ui
from cros.factory.test.utils import Enum
from cros.factory.utils.process_utils import Spawn


DataMethod = Enum(['USB', 'SF'])

EventType = Enum(['START_TEST', 'EXIT_TEST'])

FailCause = Enum(['ReadSerial', 'ModuleSN', 'CalibData', 'WriteVPD',
                  'ALSInit', 'ALSValue', 'ALSOrder', 'Unknown'])

InternalEvent = namedtuple('InternalEvent', 'event_type aux_data')

# Fake value for ALS to return.
_ALS_MOCK_VALUE = 10
_ALS_MOCK_SCALE_FACTOR = 0.5

_LED_PATTERN = ((leds.LED_NUM|leds.LED_CAP, 0.05), (0, 0.05))

class FixtureException(Exception):
  pass


class Fixture(object):
  """Communications with the test fixture."""

  def __init__(self, params, mock_mode=False):
    self._tty = None
    self._mock_mode = mock_mode

    # Load parameters.
    self._driver = params['driver']
    self._serial_params = params['serial_params']
    self._serial_delay = params['serial_delay']
    self._light_delay = params['light_delay']
    self._light_seq = params['light_seq']
    self._fixture_echo = params['echo']
    self._light_off = params['off']

  def Connect(self):
    """Setups the serial port communication."""
    if self._mock_mode:
      return

    port = FindTtyByDriver(self._driver)
    if not port:
      raise FixtureException('Cannot find TTY with driver %s' % self._driver)
    self._tty = OpenSerial(port=port, **self._serial_params)
    self._tty.flush()

  def Send(self, msg):
    """Sends control messages to the fixture."""
    if self._mock_mode:
      return

    for c in msg:
      self._tty.write(str(c))
      self._tty.flush()
      # The fixture needs some time to process each incoming character.
      time.sleep(self._serial_delay)

  def _Read(self):
    return self._tty.read(self._tty.inWaiting())

  def AssertSuccess(self):
    """Checks if the returned value from the fixture is OK."""
    if self._mock_mode:
      return

    ret = self._Read()
    if not re.search(self._fixture_echo, ret):
      raise FixtureException('The communication with fixture was broken')

  def SetLight(self, idx):
    self.Send(self._light_seq[idx])

  def TurnOffLight(self):
    self.Send(self._light_off)

  def WaitForLightSwitch(self):
    time.sleep(self._light_delay)


class ALS(object):
  """Interfaces the ambient light sensor over iio."""
  # Default min delay seconds.
  _DEFAULT_MIN_DELAY = 0.178

  def __init__(self, val_path, scale_path, _mock_mode=False):
    self._mock_mode = _mock_mode
    self.detected = True
    if _mock_mode:
      return

    if (not os.path.isfile(val_path) or
      not os.path.isfile(scale_path)):
      self.detected = False
      return

    self._val_path = val_path
    self._scale_path = scale_path

  def _ReadCore(self):
    with open(self._val_path, 'r') as f:
      val = int(f.readline().rstrip())
    return val

  def _Read(self, delay=None, samples=1):
    """Reads the light sensor value.

    Args:
        delay: Delay between samples in seconds. 0 means as fast as
               possible.
        samples: Total samples to read.

    Returns:
        The light sensor values in a list.
    """
    if self._mock_mode:
      return _ALS_MOCK_VALUE

    if samples < 1:
      samples = 1
    if delay is None:
      delay = self._DEFAULT_MIN_DELAY

    buf = []
    # The first value might be contaminated by previous settings.
    # We need to skip it for better accuracy.
    self._ReadCore()
    for _ in range(samples):
      time.sleep(delay)
      val = self._ReadCore()
      buf.append(val)

    return buf

  def ReadMean(self, delay=None, samples=1):
    if self._mock_mode:
      return _ALS_MOCK_VALUE

    if not self.detected:
      return None

    buf = self._Read(delay, samples)
    return int(round(float(sum(buf)) / len(buf)))

  def SetScaleFactor(self, scale):
    if self._mock_mode:
      return
    if not self.detected:
      return

    with open(self._scale_path, 'w') as f:
      f.write(str(int(round(scale))))
    return

  def GetScaleFactor(self):
    if self._mock_mode:
      return _ALS_MOCK_SCALE_FACTOR
    if not self.detected:
      return None

    with open(self._scale_path, 'r') as f:
      s = int(f.readline().rstrip())
    return s


class LightSensorFixtureTest(unittest.TestCase):
  """Tests light sensor."""
  ARGS = [
    Arg('mock_mode', bool, 'Mock mode allows testing without a fixture.',
        default=False),
    Arg('data_method', str, 'How to read parameters and save test results. '
        'Supported types: SF and USB.', default='USB'),
    Arg('param_pathname', str, 'Pathname of parameter file on '
        'USB drive or shopfloor.', default='camera.params'),
    Arg('shopfloor_ip', str, 'Local IP address for connecting shopfloor. '
        'When data_method = Shopfloor, set as None to use DHCP.',
        default=None, optional=True),
  ]

  # CSS style classes defined in the corresponding HTML file.
  _STYLE_INFO = 'color_idle'
  _STYLE_PASS = 'color_good'
  _STYLE_FAIL = 'color_bad'

  def setUp(self):
    self.ui = test_ui.UI()

    self.internal_queue = Queue.Queue()

    self._fail_cause = None
    self._fixture = None
    self._ignore_enter_key = False
    self._light_state = 0
    self._logs = []
    self._params_loaded = False
    self._params = None
    self._progress = 0
    self._result_status = None

    self._usb_dev_path = None
    self._usb_ready_event = None
    self._module_sn = None
    self._all_time = 0

    self.ui.AddEventHandler(
        'start_test_button_clicked',
        lambda js_args: self._PostInternalQueue(EventType.START_TEST, js_args))
    self.ui.AddEventHandler(
        'exit_test_button_clicked',
        lambda _: self._PostInternalQueue(EventType.EXIT_TEST))
    self.ui.BindKey(
        test_ui.ESCAPE_KEY,
        lambda _: self._PostInternalQueue(EventType.EXIT_TEST))

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

  def _Log(self, text):
    logging.info(text)
    self._logs.append(text)

  def _MakePassLabel(self, msg):
    return test_ui.MakeLabel(msg, css_class=self._STYLE_PASS)

  def _MakeFailLabel(self, msg):
    return test_ui.MakeLabel(msg, css_class=self._STYLE_FAIL)

  def _ResetData(self):
    self._progress = 0
    self.ui.CallJSFunction('ResetUiData', "")

  def _GetModuleSN(self):
    """Read module serial number.

    The module serial number can be read from sysfs for USB camera or from
    i2c for MIPI camera.
    """

    if self._params['sn']['source'] == 'sysfs':
      return self._GetModuleSNSysfs()
    elif self._params['sn']['source'] == 'i2c':
      return self._GetModuleSNI2C()

  def _GetModuleSNSysfs(self):
    success, input_sn = self._ReadSysfs(self._params['sn']['sysfs_path'])

    if success:
      self._Log('Serial number: %s' % input_sn)
      if not re.match(self._params['sn']['format'], input_sn):
        self._Log('Error: invalid serial number.')
        return None
    else:
      return None

    return input_sn

  def _GetModuleSNI2C(self):
    # TODO(wnhuang): replace this with a real implementation
    return '1234ABC'

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

  def _GetLogFilePrefix(self):
    device_sn = shopfloor.get_serial_number() or 'MISSING_SN'
    module_sn = self._module_sn or 'MISSING_MODULE_SN'
    return '_'.join([re.sub(r'\W+', '_', x) for x in
                     [os.environ.get('CROS_FACTORY_TEST_PATH'),
                      device_sn, module_sn]])

  def _SaveTestData(self):
    """Saves test data to USB drive or shopfloor."""
    log_prefix = self._GetLogFilePrefix()

    self._logs.append('')  # add tailing newline
    data_files = [(log_prefix + '.txt', '\n'.join(self._logs))]

    # Skip saving test data for DataMethod.SIMPLE.
    if self.args.data_method == DataMethod.USB:
      self._SaveTestDataToUSB(data_files)
    elif self.args.data_method == DataMethod.SF:
      self._SaveTestDataToShopfloor(data_files)

  def _SaveTestDataToUSB(self, data_files):
    """Saves test data to USB drive.

    Args:
      data_files: list of (filename, file data) pairs.

    Returns:
      Success or not.
    """
    self._UpdateStatus(mid='save_to_usb')
    self._usb_ready_event.wait()
    with MountedMedia(self._usb_dev_path, 1) as mount_point:
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

    self._UpdateProgress(pid='save_to_usb')
    return True

  def _SaveTestDataToShopfloor(self, data_files):
    """Saves test data to shopfloor.

    Args:
      data_files: list of (filename, file data) pairs.
    """
    self._UpdateStatus(mid='save_to_shopfloor')
    network.PrepareNetwork(ip=self.args.shopfloor_ip, force_new_ip=False)
    shopfloor_client = shopfloor.GetShopfloorConnection()

    for filename, data in data_files:
      start_time = time.time()
      shopfloor_client.SaveAuxLog(filename, xmlrpclib.Binary(data))
      factory.console.info('Successfully uploaded %r in %.03f s',
                           filename, time.time() - start_time)
    self._UpdateProgress(pid='save_to_shopfloor')

  def _LoadParams(self):
    """Loads parameters and then shows main test screen."""
    if self.args.data_method == DataMethod.USB:
      self._params = self._LoadParamsFromUSB()
      self._ResetData()
      self.ui.CallJSFunction('OnUSBInit')
    elif self.args.data_method == DataMethod.SF:
      self._params = self._LoadParamsFromShopfloor()

    # Sum all check point time to get total time
    self._all_time = sum(self._params['chk_point'].values())

    # Basic pre-processing of the parameters.
    self.SyncFixture()
    self._Log('Parameter version: %s\n' % self._params['version'])

  def _LoadParamsFromUSB(self):
    """Loads parameters from USB drive."""
    self._usb_ready_event = threading.Event()
    MediaMonitor().Start(on_insert=self._OnUSBInsertion,
                         on_remove=self._OnUSBRemoval)

    while self._usb_ready_event.wait():
      with MountedMedia(self._usb_dev_path, 1) as mount_point:
        pathname = os.path.join(mount_point, self.args.param_pathname)
        try:
          with open(pathname , 'r') as f:
            data = eval(f.read())
            self._params_loaded = True
            return data
        except IOError as e:
          self._Log('Error: fail to read %r: %r' % (pathname, e))
      time.sleep(0.5)

  def _LoadParamsFromShopfloor(self):
    """Loads parameters from shopfloor."""
    network.PrepareNetwork(ip=self.args.shopfloor_ip, force_new_ip=True)
    self.ui.CallJSFunction("OnShopfloorInit")

    factory.console.info('Reading %s from shopfloor', self.args.param_pathname)
    shopfloor_client = shopfloor.GetShopfloorConnection()
    data = eval(shopfloor_client.GetParameter(self.args.param_pathname).data)
    self._params_loaded = True
    return data

  def _OnUSBInsertion(self, dev_path):
    self._usb_dev_path = dev_path
    self._usb_ready_event.set()
    self.ui.CallJSFunction('OnUSBInsertion')

  def _OnUSBRemoval(self, unused_dev_path):
    self._usb_ready_event.clear()
    self._usb_dev_path = None
    self.ui.CallJSFunction('OnUSBRemoval')

  def _OnU2SInsertion(self, _):
    if self._params_loaded:
      self.SyncFixture()

  def _OnU2SRemoval(self, _):
    if self._params_loaded:
      self.ui.CallJSFunction('OnRemoveFixtureConnection')

  def SyncFixture(self, _=None):
    self.ui.CallJSFunction('OnDetectFixtureConnection')
    cnt = 0
    while not self._SetupFixture():
      cnt += 1
      if cnt >= self._params['fixture']['n_retry']:
        self.ui.CallJSFunction('OnRemoveFixtureConnection')
        return
      time.sleep(self._params['fixture']['retry_delay'])
    self.ui.CallJSFunction('OnAddFixtureConnection')

  def _SetupFixture(self):
    """Initialize the communication with the fixture."""
    try:
      self._fixture = Fixture(self._params['fixture'], self.args.mock_mode)
      self._fixture.Connect()

      # Go with the default(first) lighting intensity.
      self._light_state = 0
      self._fixture.SetLight(self._light_state)
      self._fixture.AssertSuccess()
    except Exception as e:
      self._fixture = None
      self._Log(str(e) + '\n')
      self._Log('Failed to initialize the test fixture.\n')
      return False
    self._Log('Test fixture successfully initialized.\n')
    return True

  def _WriteVPD(self, calib_result):
    self._UpdateStatus(mid='dump_to_vpd')
    conf = self._params['als']
    if not calib_result:
      self._UpdateResult(False, FailCause.CalibData)
      self._Log('ALS calibration data is incorrect.\n')
      return False
    if (not self.args.mock_mode and
        Spawn(conf['save_vpd'] % calib_result, shell=True)):
      self._UpdateResult(False, FailCause.WriteVPD)
      self._Log('Writing VPD data failed!\n')
      return False
    self._Log('Successfully calibrated ALS scales.\n')
    self._UpdateProgress(pid='dump_to_vpd')
    return True

  def StartTest(self, _=None):
    self._ResetData()
    self._UpdateStatus(mid='start_test')

    if not self._SetupFixture():
      self._UpdateStatus(mid='fixture_fail')
      self.ui.CallJSFunction('OnRemoveFixtureConnection')
      return
    self._UpdateProgress(pid='start_test')

    self._StartALSTest()
    self._FinalizeTest()

  def _StartALSTest(self):
    self._module_sn = self._GetModuleSN()
    if not self._module_sn:
      self._UpdateResult(False, FailCause.ModuleSN)
      self._Log('Failed to get module serial number')
      return

    self._UpdateStatus(mid='init_als')
    conf = self._params['als']
    als = ALS(conf['val_path'], conf['scale_path'], self.args.mock_mode)

    if not als.detected:
      self._UpdateResult(False, FailCause.ALSInit)
      self._Log('Failed to initialize the ALS.\n')
      return
    als.SetScaleFactor(conf['calibscale'])
    self._UpdateProgress(pid='init_als')

    # Go through all different lighting settings
    # and record ALS values.
    calib_result = 0
    try:
      vals = []
      while True:
        # Get ALS values.
        self._UpdateStatus(mid='read_als%d' % self._light_state)
        scale = als.GetScaleFactor()
        val = als.ReadMean(delay=conf['read_delay'], samples=conf['n_samples'])
        vals.append(val)
        self._Log('Lighting preset lux value: %d\n' %
                 conf['luxs'][self._light_state])
        self._Log('ALS value: %d\n' % val)
        self._Log('ALS calibration scale: %d\n' % scale)

        # Check if it is a false read.
        if not val:
          self._UpdateResult(False, FailCause.ALSValue)
          self._Log('The ALS value is stuck at zero.\n')
          return

        # Compute calibration data if it is the calibration target.
        if conf['luxs'][self._light_state] == conf['calib_lux']:
          calib_result = int(round(float(conf['calib_target']) / val * scale))
          self._Log('ALS calibration data will be %d\n' %
                       calib_result)
        self._UpdateProgress(pid='read_als%d' % self._light_state)

        # Go to the next lighting preset.
        if not self._SwitchToNextLight():
          break

      # Check value ordering
      # Skipping value ordering check when in mock mode since we don't have
      # real ALS device
      if not self.args.mock_mode:
        for i, li in enumerate(conf['luxs']):
          for j in range(i):
            if ((li > conf['luxs'][j] and vals[j] >= vals[i]) or
              (li < conf['luxs'][j] and vals[j] <= vals[i])):
              self._UpdateResult(False, FailCause.ALSOrder)
              self._Log('The ordering of ALS values is wrong.\n')
              return
    except (FixtureException, serial.serialutil.SerialException):
      self._fixture = None
      self._UpdateResult(None)
      self._Log('The test fixture was disconnected!\n')
      self.ui.CallJSFunction('OnRemoveFixtureConnection')
      return
    except:
      self._Log(traceback.format_exc())
      self._UpdateResult(False, FailCause.Unknown)
      self._Log('Failed to read values from ALS or unknown error.\n' +
                   traceback.format_exc())
      return
    self._Log('Successfully recorded ALS values.\n')

    # Save ALS values to vpd for FATP test.
    if not self._WriteVPD(calib_result):
      return
    self._UpdateResult(True)

  def _FinalizeTest(self):
    result_map = {
      True: 'PASSED',
      False: 'FAILED',
      None: 'UNTESTED'
    }
    self._UpdateStatus(mid='end_test')
    self._Log('Result in summary:\n%s%s\n' %
              (result_map[self._result_status],
              (': %s' % self._fail_cause) if not self._result_status else ''))
    self._UpdateProgress(pid='end_test')

    self._SaveTestData()

    # Display final result on UI
    def get_str(ret, prefix, cause=None):
      if ret:
        return self._MakePassLabel(prefix + 'PASS')
      if ret is None:
        return self._MakeFailLabel(prefix + 'UNFINISHED: ' + cause)
      return self._MakeFailLabel(prefix + 'FAIL:' + cause)

    als_result = get_str(self._result_status, 'ALS: ', self._fail_cause)
    self._UpdateStatus(msg=als_result)

    self._UpdateProgress(value=100)

  def _SwitchToNextLight(self):
    self._UpdateStatus(mid='adjust_light')
    conf = self._params['als']
    self._light_state += 1
    self._fixture.SetLight(self._light_state)
    self._UpdateProgress(pid='adjust_light')
    self._fixture.AssertSuccess()
    if self._light_state >= len(conf['luxs']):
      return False
    self._UpdateStatus(mid='wait_fixture')
    self._fixture.WaitForLightSwitch()
    self._UpdateProgress(pid='wait_fixture')
    return True

  def _RegisterEvents(self, events):
    for event in events:
      assert hasattr(self, event)
      self.ui.AddEventHandler(event, getattr(self, event))

  def _UpdateStatus(self, mid=None, msg=None):
    message = ''
    if msg:
      message = msg
    elif mid:
      message = test_ui.MakeLabel(self._params['message'][mid + '_en'],
                                  self._params['message'][mid + '_zh'],
                                  self._params['msg_style'][mid])
    self.ui.CallJSFunction('UpdateTestStatus', message)

  def _UpdateProgress(self, pid=None, value=None, add=True):
    if value:
      percent = value
    elif pid:
      if add:
        self._progress += self._params['chk_point'][pid]
      else:
        self._progress = self._params['chk_point'][pid]
      percent = int(round((float(self._progress) / self._all_time) * 100))
    self.ui.CallJSFunction('UpdatePrograssBar', '%d%%' % percent)

  def _UpdateResult(self, result, cause=None):
    self._result_status = result
    self._fail_cause = cause

  def _StartSerialMonitor(self):
    MediaMonitor('usb-serial').Start(on_insert=self._OnU2SInsertion,
                                     on_remove=self._OnU2SRemoval)

  def runTest(self):
    ui_thread = self.ui.Run(blocking=False)

    self.ui.CallJSFunction('InitLayout',
                           self.args.data_method == 'shopfloor',
                           self._ignore_enter_key)

    self._LoadParams()
    self._StartSerialMonitor()

    while True:
      event = self._PopInternalQueue(wait=True)
      if event.event_type == EventType.START_TEST:
        with leds.Blinker(_LED_PATTERN):
          self.StartTest()
      elif event.event_type == EventType.EXIT_TEST:
        factory.log('%s test finished' % self.__class__)
        if self._result_status:
          self.ui.Pass()
        else:
          self.ui.Fail('ALS test failed.')
        break
      else:
        raise ValueError('Invalid event type.')

    ui_thread.join()
