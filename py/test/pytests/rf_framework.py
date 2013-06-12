# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""RF test flow framework.

It defines common portion of various fixture involved tests.
"""

import logging
import os
import re
import threading
import time
import unittest
import yaml

from xmlrpclib import Binary

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import Log, GetDeviceId
from cros.factory.goofy.goofy import CACHES_DIR
from cros.factory.rf.tools.csv_writer import WriteCsv
from cros.factory.test import factory
from cros.factory.test import leds
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils
from cros.factory.test.args import Arg, Args
from cros.factory.utils import net_utils

SHOPFLOOR_TIMEOUT_SECS = 10 # Timeout for shopfloor connection.
SHOPFLOOR_RETRY_INTERVAL_SECS = 10 # Seconds to wait between retries.
INSERT_ETHERNET_DONGLE_TIMEOUT_SECS = 30 # Timeout for inserting dongle.
IP_SETUP_TIMEOUT_SECS = 10 # Timeout for setting IP address.

# Common field name shared across CSV and EventLog.
CONFIG_VERSION = 'config_version'
CALIBRATION_VERSION = 'calibration_config_version'
ELAPSED_TIME = 'elapsed_time'
MODULE_ID = 'module_id'
RF_TEST_NAME = 'rf_test_name'

MSG_START = test_ui.MakeLabel(
    'Please press SPACE key to start.',
    u'请按 "空白键" 开始')
MSG_DOWNLOADING_PARAMETERS = test_ui.MakeLabel(
    'Downloading parameters...',
    u'下载测试规格中...')
MSG_WAITING_ETHERNET = test_ui.MakeLabel(
    'Waiting for Ethernet connectivity...',
    u'等待网路介面卡...')
MSG_WAITING_IP = test_ui.MakeLabel(
    'Waiting for IP address...',
    u'等待 IP 设定...')
MSG_RUNNING_OUTSIDE_SHIELD_BOX = test_ui.MakeLabel(
    'Running test outside shield box...',
    u'执行屏蔽箱外测试中...')
MSG_OUTSIDE_SHIELD_BOX_COMPLETED = test_ui.MakeLabel(
    'Procedure outside shield box is completed.<br>'
    'Please press SPACE key to continue.',
    u'屏蔽箱外测试已完成<br>'
    u'请移至屏蔽箱后按 "空白键" 继续')
MSG_CHECKING_SHIELD_BOX = test_ui.MakeLabel(
    'Running pre-test inside shield box...',
    u'检查屏蔽箱中...')
MSG_SHIELD_BOX_CHECKED = test_ui.MakeLabel(
    'Pre-test passed.<br>'
    'Please close shield box, and then press SPACE key to continue.',
    u'屏蔽箱检查已完成<br>'
    u'请关闭箱门后按 "空白键" 继续')
MSG_RUNNING_PRIMARY_TEST = test_ui.MakeLabel(
    'Running main test...',
    u'执行屏蔽箱内主测试中...')
MSG_PRIMARY_TEST_COMPLETED = test_ui.MakeLabel(
    'Shield box testing complete.<br>'
    'The remainder of the test can be executed without a shield box.<br>'
    'Please press SPACE key to continue.',
    u'主测试执行完毕, 请将 DUT 移出屏蔽箱<br>'
    u'按 "空白键" 继续剩馀测试')
MSG_POST_TEST = test_ui.MakeLabel(
    'Running post-test.',
    u'执行剩馀测试中...')

class _RfFrameworkDelegate(object):
  """UI Delegate for RfFramework."""

  def __init__(self):
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self._ui_thread = self.ui.Run(blocking=False)

  def JoinUIThread(self):
    self._ui_thread.join()


# TODO: RfFramework can inherit from TestCase with load_tests protocol.
class RfFramework(object):
  NORMAL_MODE = 'Normal'
  DETAIL_PROMPT = 'Detail prompts'
  DETAIL_PROMPT_WITHOUT_EQUIPMENT = 'Detail prompts without equipment'

  ARGS = [
      Arg('test_name', str,
          'Optional name to identify this test. '
          'It must contain valid characters to be used in file name.',
          default='', optional=True),
      Arg('category', str,
          'Describes what category it is, should be one of calibration,'
          'production, conductive or debug.'),
      Arg('base_directory', str,
          'Relative path to directory for all parameters.'),
      Arg('config_file', str,
          'Describes where configuration locates.'),
      Arg('parameters', list,
          'A list of regular expressions indicates parameters to download from '
          'shopfloor server.', default=list()),
      Arg('calibration_config', str,
          'Calibration parameters used to compensate the pass loss.'),
      Arg('calibration_target', str,
          'A path to calibration_target.', optional=True),
      Arg('blinking_pattern', list,
          'A list of blinking state that will be passed to Blinker for '
          'inside shield-box primary test. '
          'More details of format could be found under Blinker.__init__()',
          default=[(0b111, 0.10), (0b000, 0.10)], ),
      Arg('static_ips', list,
          'Static IP settings for different stages (stack). Format of setting '
          'pair is (IP, override_flag). At the beginning of each stage, IP '
          'setting will be applied if pair is not None. Using None in IP will '
          'acquire one from DHCP. Using False in override flag will preserve '
          'the IP setting in previous stage', default=None, optional=True),
      Arg('use_shopfloor', bool, 'True to communicate with shopfloor.',
          default=True)
      ]

  def __init__(self, *args, **kwargs):
    super(RfFramework, self ).__init__(*args, **kwargs)
    self.config = None
    self.calibration_target = None
    self.calibration_config = None
    self.field_to_csv = dict()
    self.field_to_eventlog = dict()
    self.aux_logs = list()
    self.unique_identification = None

  def setUp(self, delegate=None):
    self.caches_dir = os.path.join(CACHES_DIR, 'parameters')
    self.interactive_mode = False
    self.calibration_mode = False
    self.equipment_enabled = True
    self.mode = self.NORMAL_MODE
    # Initiate an UI
    # TODO(itspeter): Set proper title and context for initial screen.
    self.delegate = delegate or _RfFrameworkDelegate()
    self.key_pressed = threading.Condition()
    self.failures = []
    # point all parameters to the correct path.
    self.args.config_file = os.path.join(
        self.args.base_directory, self.args.config_file)
    if self.args.calibration_target:
      self.args.calibration_target = os.path.join(
          self.args.base_directory, self.args.calibration_target)
    self.args.calibration_config = os.path.join(
        self.args.base_directory, self.args.calibration_config)
    self.args.parameters = ([
        os.path.join(self.args.base_directory, x) for x
            in self.args.parameters])

    # Allowed user to apply fine controls in engineering_mode
    if self.delegate.ui.InEngineeringMode():
      factory.console.debug('engineering mode detected.')
      self.mode = self._SelectMode(
          'mode',
          [self.NORMAL_MODE, self.DETAIL_PROMPT_WITHOUT_EQUIPMENT,
           self.DETAIL_PROMPT])
      if self.mode == self.DETAIL_PROMPT:
        self.interactive_mode = True
      elif self.mode == self.DETAIL_PROMPT_WITHOUT_EQUIPMENT:
        self.interactive_mode = True
        self.equipment_enabled = False

    factory.console.info('mode = %s', self.mode)
    factory.console.info('interactive_mode = %s', self.interactive_mode)
    factory.console.info('equipment_enabled = %s', self.equipment_enabled)

    self.unique_identification = self.GetUniqueIdentification()

  def TestStep0_BeforeFactoryMode(self):
    """Connects shopfloor and downloads parameters. The test has not entered
    factory mode at this step."""
    if self.args.use_shopfloor:
      self._PrepareNetwork()
      if len(self.args.parameters) > 0:
        self.SetHTML(MSG_DOWNLOADING_PARAMETERS)
        self._DownloadParameters(self.args.parameters)

    # Prepare additional parameters if we are in calibration mode.
    if self.args.category == 'calibration':
      self.calibration_mode = True
      # Load the calibration_target
      with open(os.path.join(
          self.caches_dir, self.args.calibration_target), "r") as fd:
        self.calibration_target = yaml.load(fd.read())

      # Confirm if this DUT is in the list of targets.
      if self.unique_identification not in self.calibration_target:
        failure = 'DUT %r is not in the calibration_target' % (
            self.unique_identification)
        factory.console.info(failure)
        self.delegate.Fail(failure)
        self.delegate.JoinUIThread()
      self.calibration_target = (
          self.calibration_target[self.unique_identification])
      factory.console.info('Calibration target=\n%s',
          self.calibration_target)

    # Load the main configuration.
    with open(os.path.join(
        self.caches_dir, self.args.config_file), "r") as fd:
      self.config = yaml.load(fd.read())
    config_version = self.config['annotation']
    factory.console.info('Loaded config = %r', config_version)
    self.field_to_eventlog[CONFIG_VERSION] = config_version
    self.field_to_csv[CONFIG_VERSION] = config_version

  def TestStep1_PrepareOutsideShieldBox(self):
    """Brings up test environments on DUT. Typically enters factory mode here.
    If something goes wrong, operator can handle the error earlier.
    """
    self.SetHTML(MSG_RUNNING_OUTSIDE_SHIELD_BOX)
    self.PreTestOutsideShieldBox()

  def TestStep2_PrepareInsideShieldBox(self):
    """Set up network connnection to the equipment and optionally tests if the
    equipment works.
    """
    self._PrepareNetwork()
    # TODO(itspeter): Ask user to enter shield box information.
    # TODO(itspeter): Verify the validity of shield-box and determine
    #                 the corresponding calibration_config.

    # Load the calibration_config.
    with open(os.path.join(
        self.caches_dir, self.args.calibration_config)) as fd:
      self.calibration_config = yaml.load(fd.read())
    calibration_config_version = self.calibration_config['annotation']
    factory.console.info('Loaded calibration_config = %r',
                         calibration_config_version)
    self.field_to_eventlog[CALIBRATION_VERSION] = calibration_config_version
    self.field_to_csv[CALIBRATION_VERSION] = calibration_config_version

    self.SetHTML(MSG_CHECKING_SHIELD_BOX)
    self.PreTestInsideShieldBox()

  def TestStep3_PrimaryTestInsideShieldBox(self):
    """The primary test."""
    # Primary test
    start_time = time.time()
    self.SetHTML(MSG_RUNNING_PRIMARY_TEST)
    self.PrimaryTest()
    self.field_to_eventlog[ELAPSED_TIME] = time.time() - start_time

    # Save useful info to the CSV and eventlog.
    self.field_to_eventlog[MODULE_ID] = self.unique_identification
    self.field_to_eventlog[RF_TEST_NAME] = self.args.test_name
    Log('measurement_details', **self.field_to_eventlog)
    self._LogToCsv(self.field_to_csv)

  def TestStep4_AfterShieldBox(self):
    """After operator moves DUT outside the shield box, run PostTest() and
    uploads test results to shopfloor.
    """
    # Post-test
    self.SetHTML(MSG_POST_TEST)
    self.PostTest()
    # Upload the aux_logs to shopfloor server.
    if self.args.use_shopfloor:
      self._PrepareNetwork()
      self._UploadAuxLogs(self.aux_logs)

  def runTest(self):
    self.Prompt(MSG_START, force_prompt=True)
    self.TestStep0_BeforeFactoryMode()

    try:
      self.TestStep1_PrepareOutsideShieldBox()
      self.Prompt(MSG_OUTSIDE_SHIELD_BOX_COMPLETED, force_prompt=True)

      self.TestStep2_PrepareInsideShieldBox()
      self.Prompt(MSG_SHIELD_BOX_CHECKED, force_prompt=True)

      with leds.Blinker(self.args.blinking_pattern):
        self.TestStep3_PrimaryTestInsideShieldBox()

      # Light all LEDs to indicate test is completed.
      leds.SetLeds(leds.LED_SCR|leds.LED_NUM|leds.LED_CAP)
      self.Prompt(MSG_PRIMARY_TEST_COMPLETED, force_prompt=True)
      leds.SetLeds(0)

      self.TestStep4_AfterShieldBox()
    finally:
      self.ExitFactoryMode()

    # Fail the test if failure happened.
    if len(self.failures) > 0:
      self.delegate.ui.Fail('\n'.join(self.failures))
    else:
      self.delegate.ui.Pass()
    self.delegate.JoinUIThread()

  def PreTestOutsideShieldBox(self):
    """Placeholder for procedures outside the shield-box before primary test."""
    raise NotImplementedError(
        'Called without implementing PreTestOutsideShieldBox')

  def PreTestInsideShieldBox(self):
    """Placeholder for procedures inside the shield-box before primary test."""
    raise NotImplementedError(
        'Called without implementing PreTestInsideShieldBox')

  def PrimaryTest(self):
    """Placeholder for primary test."""
    raise NotImplementedError(
        'Called without implementing PrimaryTest')

  def PostTest(self):
    """Placeholder for prcedures after primary test."""
    raise NotImplementedError(
        'Called without implementing PostTest')

  def EnterFactoryMode(self):
    """Prepares factory specific environment."""
    raise NotImplementedError(
        'Called without implementing EnterFactoryMode')

  def ExitFactoryMode(self):
    """Exits factory specific environment.

    This function will be called when test exits."""
    raise NotImplementedError(
        'Called without implementing ExitFactoryMode')

  def GetUniqueIdentification(self):
    """Gets the unique identification for module to test."""
    raise NotImplementedError(
        'Called without implementing GetUniqueIdentification')

  def _NormalizeAsFileName(self, token):
    return re.sub(r'\W+', '_', token)

  def _LogToCsv(self, field_to_record, postfix='.csv'):
    # Column names
    DEVICE_ID = 'device_id'
    DEVICE_SN = 'device_sn'
    FAILURES = 'failures'
    INVOCATION = 'invocation'
    PATH = 'path'
    LOG_TIME = 'time'

    # additional fields that need to be added becasue they are recorded
    # in event log by default and we need them in csv as well.
    device_sn = shopfloor.get_serial_number() or 'MISSING_SN'
    path = os.environ.get('CROS_FACTORY_TEST_PATH')

    field_to_record[FAILURES] = self.failures
    field_to_record[DEVICE_SN] = device_sn
    field_to_record[DEVICE_ID] = GetDeviceId()
    field_to_record[PATH] = path
    field_to_record[INVOCATION] = os.environ.get('CROS_FACTORY_TEST_INVOCATION')
    field_to_record[LOG_TIME] = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    field_to_record[MODULE_ID] = self.unique_identification

    csv_path = '%s_%s_%s%s' % (
        field_to_record[LOG_TIME],
        self._NormalizeAsFileName(device_sn),
        self._NormalizeAsFileName(self.args.test_name or path), postfix)
    csv_path = os.path.join(factory.get_log_root(), 'aux', csv_path)
    utils.TryMakeDirs(os.path.dirname(csv_path))
    self.aux_logs.append(csv_path)
    WriteCsv(csv_path, [field_to_record],
             [LOG_TIME, MODULE_ID, DEVICE_SN, DEVICE_ID,
              PATH, FAILURES, INVOCATION])
    factory.console.info('Details saved to %s', csv_path)

  def _GetShopfloorConnection(
      self, timeout_secs=SHOPFLOOR_TIMEOUT_SECS,
      retry_interval_secs=SHOPFLOOR_RETRY_INTERVAL_SECS):
    """Returns a shopfloor client object.

    Try forever until a connection of shopfloor is established.

    Args:
      timeout_secs: Timeout for shopfloor connection.
      retry_interval_secs: Seconds to wait between retries.
    """
    factory.console.info('Connecting to shopfloor...')
    while True:
      try:
        shopfloor_client = shopfloor.get_instance(
            detect=True, timeout=timeout_secs)
        break
      except:  # pylint: disable=W0702
        exception_string = utils.FormatExceptionOnly()
        # Log only the exception string, not the entire exception,
        # since this may happen repeatedly.
        factory.console.info('Unable to sync with shopfloor server: %s',
                             exception_string)
      time.sleep(retry_interval_secs)
    return shopfloor_client

  def _DownloadParameters(self, parameters):
    """Downloads parameters from shopfloor and saved to state/caches."""
    factory.console.info('Start downloading parameters...')
    shopfloor_client = self._GetShopfloorConnection()
    logging.info('Syncing time with shopfloor...')
    goofy = factory.get_state_instance()
    goofy.SyncTimeWithShopfloorServer()

    download_list = []
    for glob_expression in parameters:
      logging.info('Listing %s', glob_expression)
      download_list.extend(
          shopfloor_client.ListParameters(glob_expression))
    logging.info('Download list prepared:\n%s', '\n'.join(download_list))
    assert len(download_list) > 0, 'No parameters found on shopfloor'
    # Download the list and saved to caches in state directory.
    for filepath in download_list:
      utils.TryMakeDirs(os.path.join(
          self.caches_dir, os.path.dirname(filepath)))
      binary_obj = shopfloor_client.GetParameter(filepath)
      with open(os.path.join(self.caches_dir, filepath), 'wb') as fd:
        fd.write(binary_obj.data)
    # TODO(itspeter): Verify the signature of parameters.

  def _UploadAuxLogs(self, file_paths, ignore_on_fail=False):
    """Attempts to upload arbitrary file to the shopfloor server."""
    shopfloor_client = self._GetShopfloorConnection()
    for file_path in file_paths:
      try:
        chunk = open(file_path, 'r').read()
        log_name = os.path.basename(file_path)
        factory.console.info('Uploading %s', log_name)
        start_time = time.time()
        shopfloor_client.SaveAuxLog(log_name, Binary(chunk))
        factory.console.info('Successfully synced %s in %.03f s',
            log_name, time.time() - start_time)
      except:  # pylint: disable=W0702
        if ignore_on_fail:
          factory.console.info(
              'Failed to sync with shopfloor for [%s], ignored',
              log_name)
        else:
          raise

  def _PrepareNetwork(self):
    """Blocks forever until network is prepared."""
    # If static_ips is None, disable network setup.
    if not self.args.static_ips:
      return
    static_ip_pair = self.args.static_ips.pop()

    def ObtainIp():
      if static_ip_pair[0] is None:
        net_utils.SendDhcpRequest()
      else:
        net_utils.SetEthernetIp(static_ip_pair[0], force=static_ip_pair[1])
      return True if net_utils.GetEthernetIp() else False

    while True:
      self.SetHTML(MSG_WAITING_ETHERNET)
      factory.console.info('Detecting Ethernet device...')
      try:
        net_utils.PollForCondition(condition=(
            lambda: True if net_utils.FindUsableEthDevice() else False),
            timeout=INSERT_ETHERNET_DONGLE_TIMEOUT_SECS,
            condition_name='Detect Ethernet device')

        # Only setup the IP if required so.
        current_ip = net_utils.GetEthernetIp(net_utils.FindUsableEthDevice())
        if not current_ip or static_ip_pair[1] is True:
          self.SetHTML(MSG_WAITING_IP)
          factory.console.info('Setting up IP address...')
          net_utils.PollForCondition(condition=ObtainIp,
              timeout=IP_SETUP_TIMEOUT_SECS,
              condition_name='Setup IP address')
          break
        else:
          break
      except:  # pylint: disable=W0702
        exception_string = utils.FormatExceptionOnly()
        factory.console.info('Unable to setup network: %s',
                             exception_string)

    factory.console.info('Network prepared. IP: %r', net_utils.GetEthernetIp())

  def _SelectMode(self, title, choices):
    def GetSelectValue(dict_wrapper, event):
      # As python 2.x doesn't have a nonlocal keyword.
      # simulate the nonlocal by using a dict wrapper.
      select_value = event.data.strip()
      logging.info('Selected value: %s', select_value)
      dict_wrapper['select_value'] = select_value
      with self.key_pressed:
        self.key_pressed.notify()

    def GenerateRadioButtonsHtml(choices):
      '''Generates html snippet for the selection.

      First item will be selected by default.
      '''
      radio_button_html = ''
      for idx, choice in enumerate(choices):
        radio_button_html += (
            '<input name="select-value" type="radio" ' +
            ('checked ' if (idx == 0) else '') +
            'value="%s" id="choice_%d">' % (choice, idx) +
            '<label for="choice_%d">%s</label><br>' % (idx, choice))
      return radio_button_html

    dict_wrapper = dict()
    self.SetHTML(
        test_ui.MakeLabel(
            'Please select the %s and press ENTER.<br>' % title) +
        GenerateRadioButtonsHtml(choices) + '<br>&nbsp;'
        '<p id="select-error" class="test-error">&nbsp;')

    # Handle selected value when Enter pressed.
    self.delegate.ui.BindKeyJS(
        '\r',
        'window.test.sendTestEvent("select_value",'
        'function(){'
        '  choices = document.getElementsByName("select-value");'
        '  for (var i = 0; i < choices.length; ++i)'
        '    if (choices[i].checked)'
        '      return choices[i].value;'
        '  return "";'
        '}())')
    self.delegate.ui.AddEventHandler(
        'select_value',
        lambda event: GetSelectValue(dict_wrapper, event))
    with self.key_pressed:
      self.key_pressed.wait()
    self.delegate.ui.UnbindKey('\r')
    return dict_wrapper['select_value']

  def Prompt(self, prompt_str, key_to_wait=' ', force_prompt=False):
    """Displays a prompt to user and wait for a specific key.

    Args:
      prompt_str: The html snippet to display in the screen.
      key_to_wait: The specific key to wait from user, more details on
        BindKeyJS()'s docstring.
      force_prompt: A prompt call will be vaild if interactive_mode is True by
        default. Set force_prompt to True will override this behavior.
    """
    def KeyPressed():
      with self.key_pressed:
        self.key_pressed.notify()

    if not (force_prompt or self.interactive_mode):
      # Ignore the prompt request.
      return
    self.SetHTML(prompt_str)
    self.delegate.ui.BindKey(key_to_wait, lambda _: KeyPressed())
    with self.key_pressed:
      self.key_pressed.wait()
    self.delegate.ui.UnbindKey(key_to_wait)

  def SetHTML(self, html, append=False):
    self.delegate.template.SetState(html=html, append=append)

  def RunEquipmentCommand(self, function, *args, **kwargs):
    """Wrapper for controling the equipment command.

    The function will only be called if self.equipment_enabled is True.
    """
    if self.equipment_enabled:
      return function(*args, **kwargs)


class RfComboTestLoader(unittest.TestCase):
  """Runs two RfFramework based tests while load/unload DUT on light chamber
  only once. It provides common ARGS[] and __init__(), setUp(), and runTest()
  methods.
  """
  ARGS = [
      # The ARGS list is almost identical to RfFramework.ARGS with exception
      # that some arguments are combo version (argument name ended with
      # '_combo'). For combo arguments, the values are a pair of the
      # corresponding argument in RfFramework.
      #
      # Please see RfFramework.ARGS[] for detailed help.
      #
      # 'calibration_target' is omitted here by purpose because the calibration
      # should run in standalone mode.
      Arg('test_name_combo', tuple, 'Combo arguments.'),
      Arg('category', str, 'Shared argument.'),
      Arg('base_directory_combo', tuple, 'Combo arguments.'),
      Arg('config_file_combo', tuple, 'Combo arguments.'),
      Arg('parameters_combo', tuple, 'Combo arguments.'),
      Arg('calibration_config_combo', tuple, 'Combo arguments.'),
      Arg('blinking_pattern_combo', tuple, 'Combo arguments.'),
      Arg('static_ips_combo', tuple, 'Combo arguments.'),
      Arg('use_shopfloor', bool, 'Shared argument.', default=True)
      ]

  def __init__(self, *args, **kwargs):
    super(RfComboTestLoader, self).__init__(*args, **kwargs)
    self.rf_tests = None
    self.delegate = None

  def attachTests(self, rf_tests):
    """Attaches two RF tests before setUp()."""
    self.rf_tests = rf_tests
    if len(rf_tests) != 2:
      raise ValueError('rf_tests must contain two tests.')

  def setUp(self):
    def _TranslateArg(k, v, test_index):
      """Translates args for RfFramework.
      Returns:
        Translated (key, value) tuple.
      """
      m = re.match(r'^(.*)_combo$', k)
      if m:
        return (m.group(1), v[test_index])
      else:
        return (k, v)

    logging.info('self.rf_tests=%r', self.rf_tests)

    # Enumerate argument names from ARGS (self.args is not iterable).
    arg_list = [arg.name for arg in self.ARGS]
    for test_index in range(2):
      new_dargs = dict(_TranslateArg(k, getattr(self.args, k), test_index)
                       for k in arg_list)
      new_args = Args(*self.rf_tests[test_index].ARGS).Parse(new_dargs)
      setattr(self.rf_tests[test_index], 'args', new_args)
      logging.info('args for RF test #%d are %r', test_index + 1,
                   new_dargs)

    self.delegate = _RfFrameworkDelegate()
    self.rf_tests[0].setUp(self.delegate)
    self.rf_tests[1].setUp(self.delegate)

  def runTest(self):
    # The test sequence cannot be changed arbitrarily.
    #
    #  Test_A        Test_B
    # ---------------------
    #           ==>
    #  Step 0  _____Step 0
    #          ____/
    #  Step 1 /_____Step 1
    #          ____/
    #  Step 2_/     Step 2
    #    |     ____/  |
    #  Step 3_/     Step 3
    #          ____/
    #  Step 4 /____ Step 4
    #
    self.rf_tests[0].Prompt(MSG_START, force_prompt=True)
    self.rf_tests[0].TestStep0_BeforeFactoryMode()
    self.rf_tests[1].TestStep0_BeforeFactoryMode()

    try:
      self.rf_tests[0].TestStep1_PrepareOutsideShieldBox()
      self.rf_tests[1].TestStep1_PrepareOutsideShieldBox()
      self.rf_tests[0].Prompt(MSG_OUTSIDE_SHIELD_BOX_COMPLETED,
                              force_prompt=True)

      # DUT is inside shield box.
      self.rf_tests[0].TestStep2_PrepareInsideShieldBox()
      self.rf_tests[0].Prompt(MSG_SHIELD_BOX_CHECKED, force_prompt=True)
      # Operator closes the door of shield box here.
      with leds.Blinker(self.args.blinking_pattern_combo[0]):
        self.rf_tests[0].TestStep3_PrimaryTestInsideShieldBox()
      with leds.Blinker(self.args.blinking_pattern_combo[1]):
        self.rf_tests[1].TestStep2_PrepareInsideShieldBox()
        # No user interaction at this point because the first test has talked to
        # the equipment earlier.
        self.rf_tests[1].TestStep3_PrimaryTestInsideShieldBox()

      # Light all LEDs to indicate test is completed.
      leds.SetLeds(leds.LED_SCR|leds.LED_NUM|leds.LED_CAP)
      self.rf_tests[0].Prompt(MSG_PRIMARY_TEST_COMPLETED, force_prompt=True)
      leds.SetLeds(0)

      self.rf_tests[0].TestStep4_AfterShieldBox()
      self.rf_tests[1].TestStep4_AfterShieldBox()
    finally:
      self.rf_tests[0].ExitFactoryMode()
      self.rf_tests[1].ExitFactoryMode()

    failures = self.rf_tests[0].failures + self.rf_tests[1].failures
    if len(failures) > 0:
      self.delegate.ui.Fail('\n'.join(failures))
    else:
      self.delegate.ui.Pass()
    self.delegate.JoinUIThread()
