# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# DESCRIPTION:
# This test is used to verify the functionality of bluetooth device.
# The functionality under test are:
# 1. Detect the specified number of bluetooth adapter on dut.
# 2. Scan remote bluetooth device and try to find at least one device.
# 3. If a remote device keyword is given, the test will only care
#    the devices whose 'Name' contains keyword. This applies to item 4 as well.
# 4. If an RSSI threshold value is given, check that the largest average RSSI
#    among all scanned devices >= threshold.
# 5. Try to pair and connect with the bluetooth input device. Now it supports
#    mouse.
# Check the ARGS in BluetoothTest for the detail of arguments.

import factory_common # pylint: disable=W0611
import glob
import logging
import sys
import time
import unittest

from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.test.test_ui import MakeLabel
from cros.factory.test.utils import Retry, StartDaemonThread
from cros.factory.system.bluetooth import BluetoothManager
from cros.factory.system.bluetooth import BluetoothManagerException


_TEST_TITLE = MakeLabel('Bluetooth functional Test', u'蓝牙功能测试')
_MSG_DETECT_ADAPTER = MakeLabel('Detect bluetooth adapter', u'检测蓝牙适配器')
_MSG_TURN_ON_DEVICE = MakeLabel('Enable the connection ability of'
                                ' bluetooth device and press Enter',
                                u'启用蓝牙装置的连接功能然后按输入键',
                                'start-font-size')
_MSG_SCAN_DEVICE = MakeLabel('Scanning...', u'扫描中...', 'start-font-size')
_MSG_TURN_ON_INPUT_DEVICE = MakeLabel('Enable the connection ability of '
                                      'input bluetooth device and press Enter',
                                      u'启用蓝牙输入装置的连接功能然后按输入键',
                                      'start-font-size')
_MSG_PAIR_INPUT_DEVICE = MakeLabel('Pairing to input device now...',
                                   u'配对到蓝牙输入设备...',
                                   'start-font-size')
_MSG_CONNECT_INPUT_DEVICE = MakeLabel('Connecting to input device now...',
                                      u'连接到蓝牙输入设备...',
                                      'start-font-size')
_MSG_TEST_INPUT = MakeLabel('Please test input. '
                            'Press Escape to fail and Enter to pass',
                            u'请测试输入, 如果失败, 请按Esc键'
                            u'如果成功，请按Enter键',
                            'start-font-size')
INPUT_MAX_RETRY_TIMES = 10
INPUT_RETRY_INTERVAL = 2


class DetectAdapterTask(FactoryTask):
  """The task checking number of adapters.

     Detects adapters from dbus and checks if the number of adapters
     matches the expected number.

  Args:
     expected_adapter_count: The expected number of bluetooth adapters.
  """
  # pylint: disable=W0231
  def __init__(self, test, expected_adapter_count):
    self._test = test
    self._expected_adapter_count = expected_adapter_count

  def Run(self):
    self._test.template.SetState(_MSG_DETECT_ADAPTER)
    adapters = BluetoothManager().GetAdapters(
        self._test.args.detect_adapters_retry_times,
        self._test.args.detect_adapters_interval_secs)
    if len(adapters) == self._expected_adapter_count:
      self.Pass()
    else:
      self.Fail('DetectAdapter: expect %d and find %d adapter(s).' %
                (self._expected_adapter_count, len(adapters)))


class TurnOnTask(FactoryTask):
  """The task to ask operator to turn on bluetooth device and press enter.

  Args:
    message: Html code containing message to show on the screen.
  """
  def __init__(self, test, message): # pylint: disable=W0231
    self._test = test
    self._message = message

  def Cleanup(self):
    """Unbinds the Enter key after this task is done."""
    self._test.ui.UnbindKey(test_ui.ENTER_KEY)

  def Run(self):
    self._test.template.SetState(self._message)
    self._test.ui.AppendCSS('.start-font-size {font-size: 2em;}')
    self._test.ui.BindKey(test_ui.ENTER_KEY, lambda _: self.Pass())
    logging.info('wait for enter key')


class ScanDevicesTask(FactoryTask):
  """The task to scan bluetooth devices around.

  In this task, the test will control the first adapter from BluetoothManager
  and scan devices around for timeout_secs. The task passed if there is at least
  one device.
  If target_addresses is provided, the test will also check if it can find
  at least one device specified in target_addresses list.

  Args:
    timeout_secs: The time duration to scan for devices.
  """
  # pylint: disable=W0231
  def __init__(self, test):
    self._test = test
    self._keyword = test.args.keyword
    self._average_rssi_threshold = test.args.average_rssi_threshold
    self._scan_counts = 1
    if self._average_rssi_threshold is not None:
      self._scan_counts = test.args.scan_counts
    self._timeout_secs = test.args.scan_timeout_secs

    self._progress_thread = None

  def SetAndStartScanProgressBar(self, timeout_secs):
    """Control progress bar fo a duration of timeout_secs."""
    def UpdateProgressBar():
      """Updates progress bar for a duration of timeout_secs"""
      start_time = time.time()
      end_time = start_time + timeout_secs
      while time.time() < end_time:
        self._test.template.SetProgressBarValue(int(
            100 * (time.time() - start_time) / timeout_secs))
        time.sleep(0.2)
      self._test.template.SetProgressBarValue(100)
      logging.debug('UpdateProgressBar stopped.')

    self._test.template.DrawProgressBar()
    self._progress_thread = StartDaemonThread(target=UpdateProgressBar,
                                              name='ProgressThread')

  def FilterByKeyword(self, devices):
    """Returns the devices filtered by self._keyword.

    If self._keyword is None, leave devices as it is.
    """
    if self._keyword is None:
      return devices

    filtered_devices = dict()
    for mac, props in devices.iteritems():
      if 'Name' not in props:
        logging.warning('Device %s: %s does not have "Name" property.',
                        mac, props)
        continue

      if self._keyword in props['Name']:
        filtered_devices[mac] = props
        logging.info('Device %s: "Name" property %s matches keyword %s.',
                      mac, props['Name'], self._keyword)
    return filtered_devices

  def UpdateRssi(self, devices_rssis, devices):
    """Updates devices_rssis using RSSI property in devices.

    Args:
      devices_rssis: A dict. Keys are mac addresses and values are lists of
        scanned RSSI value.
      devices: A dict. Keys are mac addresses and values are dicts of
        properties.
    """
    for mac, props in devices.iteritems():
      if 'RSSI' not in props:
        logging.warning('Device %s: %s does not have "RSSI" property.',
                        mac, props)
        continue
      if mac in devices_rssis:
        devices_rssis[mac].append(props['RSSI'])
      else:
        devices_rssis[mac] = [props['RSSI']]
    logging.info('UpdateRssi: %s', devices_rssis)

  def Run(self):
    bluetooth_manager = BluetoothManager()
    adapter = bluetooth_manager.GetFirstAdapter()

    # Records RSSI of each scan and calculates average rssi.
    candidate_rssis = dict()

    for _ in xrange(self._scan_counts):
      self._test.template.SetState(_MSG_SCAN_DEVICE)
      self.SetAndStartScanProgressBar(self._timeout_secs)
      devices = bluetooth_manager.ScanDevices(adapter, self._timeout_secs)
      self._progress_thread.join()

      logging.info('Found %d device(s).', len(devices))
      for mac, props in devices.iteritems():
        try:
          logging.info('Device found: %s. Name: %s, RSSI: %d',
                        mac, props["Name"], props['RSSI'])
        except KeyError:
          logging.exception('Name or RSSI is not available in %s', mac)

      self.UpdateRssi(candidate_rssis, self.FilterByKeyword(devices))

    logging.info('Found %d candidate device(s) in %s scans.',
                 len(candidate_rssis), self._scan_counts)
    factory.console.info('Candidate devices scan results: %s',
        dict((str(k), [int(r) for r in v])
             for k, v in candidate_rssis.iteritems()))

    if len(candidate_rssis) == 0:
      self.Fail('ScanDevicesTask: Fail to find any candidate device.')
      return

    # No need to test RSSI
    if self._average_rssi_threshold is None:
      self.Pass()
      return

    # Calculates maximum average RSSI.
    max_average_rssi_mac, max_average_rssi = None, -sys.float_info.max
    for mac, rssis in candidate_rssis.iteritems():
      average_rssi = float(sum(rssis)) / len(rssis)
      logging.info('Device %s has average RSSI: %f', mac, average_rssi)
      if average_rssi > max_average_rssi:
        max_average_rssi_mac, max_average_rssi = mac, average_rssi

    logging.info('Device %s has the largest average RSSI: %f',
                 max_average_rssi_mac, max_average_rssi)

    if self._average_rssi_threshold > max_average_rssi:
      factory.console.error('The largest average RSSI %f does not meet'
                            ' threshold %f.',
                            max_average_rssi, self._average_rssi_threshold)
      self.Fail('ScanDeviceTask: The largest average RSSI %f of device %s does'
                ' not meet threshold %f.' % (
                    max_average_rssi, max_average_rssi_mac,
                    self._average_rssi_threshold))
    else:
      factory.console.info('The largest average RSSI %f meets threshold %f.',
                           max_average_rssi, self._average_rssi_threshold)
      self.Pass()


class InputTestTask(FactoryTask):
  """The task to test bluetooth input device functionality.

  The task will try to pair with the device and make the connection.
  After the connection, the number of input event should plus one.
  If it does not plus one, the task fails.
  After connection, operator can try to use the input device and press Enter
  to pass checking or Esc to fail the task.
  In the end of test, the task will try to disconnect the device and remove the
  device. If these procedures fail, the task fails.

  Args:
    input_device_mac: The mac address of bluetooth input device.
  """
  def __init__(self, test, input_device_mac): # pylint: disable=W0231
    self._test = test
    self._target_mac = input_device_mac
    self._bt_manager = None
    self._adapter = None
    self._need_to_cleanup = True

  def CheckInputCount(self):
    """Returns the number of input devices from probing /dev/input/event*."""
    number_input = len(glob.glob('/dev/input/event*'))
    logging.info('Found %d input devices.', number_input)
    return number_input

  def FinishProgressBar(self):
    """Sets progress bar to 100 to indicate retry is done."""
    self._test.template.SetProgressBarValue(100)

  def Cleanup(self):
    """Cleans up input device if it was not cleaned"""
    if self._need_to_cleanup:
      success_to_remove = self.RemoveInput()
      if not success_to_remove:
        logging.error('Fail to remove input in Cleanup')

  def RemoveInput(self):
    """Disconnects the input device and removes it.

    Returns:
      If disconnection and removal are both succeeded, return True, return False
      otherwise.
    """
    return_value = True
    try:
      self._bt_manager.SetDeviceConnected(self._adapter, self._target_mac,
                                          False)
      logging.info('Turned off the connection')
    except BluetoothManagerException:
      logging.exception('Fail to turn off the connection.')
      return_value = False
    try:
      self._bt_manager.RemovePairedDevice(self._adapter, self._target_mac)
      logging.info('Remove the device')
    except BluetoothManagerException:
      logging.exception('Fail to remove the device.')
      return_value = False
    return return_value

  def RemoveInputAndQuit(self, success):
    """Removes the input device and quits the task.

    Args:
      success: The task is passed by operator or not.

    Returns:
      If the task is passed by operator and input has been removed successfully,
      pass the task, fail the task otherwise.
    """
    success_to_remove = self.RemoveInput()
    # No need to cleanup again after the task does Pass() or Fail() if removal
    # succeeds here.
    self._need_to_cleanup = not success_to_remove
    if success:
      if success_to_remove:
        self.Pass()
      else:
        self.Fail('InputTestTask: Fail to remove input')
    else:
      self.Fail('Failed by operator')

  def RetryWithProgress(self, message, action_string, target, *args, **kwargs):
    """Trys to run a target function with progress bar

    Args:
      message: The message to show when target function is running.
      action_string: The string to describe the action in logging.
      target: The target function. *args and **kwargs will be passed to target.

    Returns:
      Return the return value of the target function.
    """
    self._test.template.DrawProgressBar()
    self._test.template.SetState(message)

    def _UpdateProgressBar(retry_time, max_retry_time):
      """Updates the progress bar according to retry_time and max_retry_time."""
      logging.info('Update progress bar with retry time: %d,'
                   ' max retry time: %d.', retry_time, max_retry_time)
      self._test.template.SetProgressBarValue(
          int(100 * retry_time / max_retry_time))

    target_result = Retry(INPUT_MAX_RETRY_TIMES, INPUT_RETRY_INTERVAL,
                          _UpdateProgressBar, target, *args, **kwargs)
    self.FinishProgressBar()
    if target_result:
      logging.info('InputTestTask: %s Done.', action_string)
    else:
      logging.error('InputTestTask: %s Fail.', action_string)
    return target_result

  def OperatorTestInput(self):
    """Lets operator test the input and press key to pass/fail the task."""
    logging.info('InputTestTask: Test the input by operator now')
    self._test.template.SetState(_MSG_TEST_INPUT)
    self._test.ui.BindKey(test_ui.ENTER_KEY,
                     lambda _: self.RemoveInputAndQuit(True))
    self._test.ui.BindKey(test_ui.ESCAPE_KEY,
                     lambda _: self.RemoveInputAndQuit(False))

  def Run(self):
    input_count_before_connection = self.CheckInputCount()
    self._bt_manager = BluetoothManager()
    self._adapter = self._bt_manager.GetFirstAdapter()

    try:
      self._bt_manager.RemovePairedDevice(self._adapter, self._target_mac)
    except BluetoothManagerException as e:
      if str(e).find('Does Not Exist'):
        logging.info('Fail to remove device before connection because'
                     ' there is no device there. This is OK.')
      else:
        logging.exception('Fail to remove device while there is a device'
                          ' before connection.')

    success_create_device = self.RetryWithProgress(_MSG_PAIR_INPUT_DEVICE,
        'create paired device', self._bt_manager.CreatePairedDevice,
        self._adapter, self._target_mac)
    if not success_create_device:
      self.Fail('InputTestTask: Fail to create paired device.')
      return

    success_connect_device = self.RetryWithProgress(_MSG_CONNECT_INPUT_DEVICE,
        'connect input device', self._bt_manager.SetDeviceConnected,
        self._adapter, self._target_mac, True)
    if not success_connect_device:
      self.Fail('InputTestTask: Fail to connect device.')
      return

    input_count_after_connection = self.CheckInputCount()
    if input_count_after_connection != input_count_before_connection + 1:
      self.Fail('InputTestTask: input device does not plus one.')
      return

    self.OperatorTestInput()


class BluetoothTest(unittest.TestCase):
  ARGS = [
    Arg('expected_adapter_count', int, 'Number of bluetooth adapters'
        ' on the machine.', default=1),
    Arg('detect_adapters_retry_times', int, 'Maximum retry time to'
        ' detect adapters', default=10),
    Arg('detect_adapters_interval_secs', int, 'Interval in seconds between each'
        ' retry to detect adapters', default=2),
    Arg('scan_devices', bool, 'Scan bluetooth device.',
        default=False),
    Arg('prompt_scan_message', bool, 'Prompts a message to tell user to enable'
        ' remote devices discovery mode', default=True),
    Arg('keyword', str, 'Only cares remote devices whose "Name" contains'
        ' keyword.', default=None, optional=True),
    Arg('average_rssi_threshold', float, 'Checks the largest average RSSI among'
        ' scanned device is equal to or greater than average_rssi_threshold.',
        default=None, optional=True),
    Arg('scan_counts', int, 'Number of scans to calculate average RSSI',
        default=3),
    Arg('scan_timeout_secs', int, 'Timeout to do one scan', default=5),
    Arg('input_device_mac', str, 'The mac address of bluetooth input device',
        default=None, optional=True),
  ]
  def __init__(self, *args, **kwargs):
    super(BluetoothTest, self).__init__(*args, **kwargs)
    self.ui = test_ui.UI()
    self.template = ui_templates.TwoSections(self.ui)
    self.template.SetTitle(_TEST_TITLE)
    self._task_list = []

  def runTest(self):
    if self.args.expected_adapter_count:
      self._task_list.append(DetectAdapterTask(
          self, self.args.expected_adapter_count))

    if self.args.scan_devices:
      if self.args.prompt_scan_message:
        self._task_list.append(TurnOnTask(self, _MSG_TURN_ON_DEVICE))
      self._task_list.append(ScanDevicesTask(self))

    if self.args.input_device_mac:
      self._task_list.append(TurnOnTask(self, _MSG_TURN_ON_INPUT_DEVICE))
      self._task_list.append(InputTestTask(self, self.args.input_device_mac))

    FactoryTaskManager(self.ui, self._task_list).Run()
