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
from cros.factory.test.args import Arg
from cros.factory.utils import net_utils

SHOPFLOOR_TIMEOUT_SECS = 10 # Timeout for shopfloor connection.
SHOPFLOOR_RETRY_INTERVAL_SECS = 10 # Seconds to wait between retries.

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


class RfFramework(object):
  NORMAL_MODE = 'Normal'
  DETAIL_PROMPT = 'Detail prompts'
  DETAIL_PROMPT_WITHOUT_EQUIPMENT = 'Detail prompts without equipment'

  ARGS = [
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
      Arg('pre_test_outside_shield_box', bool,
          'True to execute PreTestOutsideShieldBox.',
          default=True),
      Arg('pre_test_inside_shield_box', bool,
          'True to execute PreTestInsideShieldBox.',
          default=True),
      Arg('post_test', bool,
          'True to execute PostTest.',
          default=True)
      ]

  def __init__(self, *args, **kwargs):
    super(RfFramework, self ).__init__(*args, **kwargs)
    self.config = None
    self.calibration_target = None
    self.calibration_config = None
    self.field_to_record = dict()
    self.aux_logs = list()
    self.unique_identification = None

  def setUp(self):
    self.caches_dir = os.path.join(CACHES_DIR, 'parameters')
    self.interactive_mode = False
    self.calibration_mode = False
    self.equipment_enabled = True
    self.mode = self.NORMAL_MODE
    # Initiate an UI
    self.ui = test_ui.UI()
    # TODO(itspeter): Set proper title and context for initial screen.
    self.template = ui_templates.OneSection(self.ui)
    self.key_pressed = threading.Condition()
    self.ui_thread = self.ui.Run(blocking=False)
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
    if self.ui.InEngineeringMode():
      factory.console.debug('engineering mode detected.')
      self.mode = self.SelectMode(
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

  def runTest(self):
    self.unique_identification = self.GetUniqueIdentification()
    self.Prompt(MSG_START, force_prompt=True)

    if self.args.pre_test_outside_shield_box:
      self.PrepareNetwork(self.args.static_ips.pop())
      if len(self.args.parameters) > 0:
        self.template.SetState(MSG_DOWNLOADING_PARAMETERS)
        self.DownloadParameters(self.args.parameters)

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
          self.ui.Fail(failure)
          self.ui_thread.join()
        self.calibration_target = (
            self.calibration_target[self.unique_identification])
        factory.console.info('Calibration target=\n%s',
            self.calibration_target)

      # Load the main configuration.
      with open(os.path.join(
          self.caches_dir, self.args.config_file), "r") as fd:
        self.config = yaml.load(fd.read())
      factory.console.info('Loaded config = %r', self.config['annotation'])

    try:
      self.template.SetState(MSG_RUNNING_OUTSIDE_SHIELD_BOX)
      self.PreTestOutsideShieldBox()
      self.Prompt(MSG_OUTSIDE_SHIELD_BOX_COMPLETED, force_prompt=True)

      if self.args.pre_test_inside_shield_box:
        self.PrepareNetwork(self.args.static_ips.pop())
        # TODO(itspeter): Ask user to enter shield box information.
        # TODO(itspeter): Verify the validity of shield-box and determine
        #                 the corresponding calibration_config.

        # Load the calibration_config.
        with open(os.path.join(
            self.caches_dir, self.args.calibration_config)) as fd:
          self.calibration_config = yaml.load(fd.read())
        self.LogDetail(event_log_key='calibration_config',
                       field_to_record=self.calibration_config,
                       postfix='.cal_data.csv')

        self.template.SetState(MSG_CHECKING_SHIELD_BOX)
        self.PreTestInsideShieldBox()
        # TODO(itspeter): Support multiple language in prompt.
        self.Prompt(MSG_SHIELD_BOX_CHECKED, force_prompt=True)

      # Primary test
      # TODO(itspeter): Timing on PrimaryTest().
      self.template.SetState(MSG_RUNNING_PRIMARY_TEST)
      with leds.Blinker(self.args.blinking_pattern):
        self.PrimaryTest()
      # Save useful info to the CSV and eventlog.
      self.LogDetail(event_log_key='measurement_details',
                     field_to_record=self.field_to_record)

      # Light all LEDs to indicates test is completed.
      leds.SetLeds(leds.LED_SCR|leds.LED_NUM|leds.LED_CAP)
      self.Prompt(MSG_PRIMARY_TEST_COMPLETED, force_prompt=True)
      leds.SetLeds(0)

      # Post-test
      if self.args.post_test:
        self.PrepareNetwork(self.args.static_ips.pop())
        self.template.SetState(MSG_POST_TEST)
        self.PostTest()
        # Upload the aux_logs to shopfloor server.
        self.UploadAuxLogs(self.aux_logs)
    finally:
      self.ExitFactoryMode()

    # Fail the test if failure happened.
    if len(self.failures) > 0:
      self.ui.Fail('\n'.join(self.failures))
    else:
      self.ui.Pass()
    self.ui_thread.join()

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

  def NormalizeAsFileName(self, token):
    return re.sub(r'\W+', '', token)

  def LogDetail(self, event_log_key, field_to_record, postfix='.csv'):
    # Column names
    DEVICE_ID = 'device_id'
    DEVICE_SN = 'device_sn'
    MODULE_ID = 'module_id'
    PATH = 'path'
    INVOCATION = 'invocation'
    FAILURES = 'failures'

    # log to event log.
    field_to_record[MODULE_ID] = self.unique_identification
    Log(event_log_key, **field_to_record)

    # additional fields that need to be added becasue they are recorded
    # in event log by default and we need them in csv as well.
    device_sn = shopfloor.get_serial_number() or 'MISSING_SN'
    path = os.environ.get('CROS_FACTORY_TEST_PATH')

    field_to_record[FAILURES] = self.failures
    field_to_record[DEVICE_SN] = device_sn
    field_to_record[DEVICE_ID] = GetDeviceId()
    field_to_record[PATH] = path
    field_to_record[INVOCATION] = os.environ.get('CROS_FACTORY_TEST_INVOCATION')
    csv_path = '%s_%s_%s%s' % (
        time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()),
        self.NormalizeAsFileName(device_sn),
        self.NormalizeAsFileName(path), postfix)
    csv_path = os.path.join(factory.get_log_root(), 'aux', csv_path)
    utils.TryMakeDirs(os.path.dirname(csv_path))
    self.aux_logs.append(csv_path)
    WriteCsv(csv_path, [field_to_record],
             [MODULE_ID, DEVICE_SN, DEVICE_ID, PATH, FAILURES, INVOCATION])
    factory.console.info('Details saved to %s', csv_path)

  def GetShopfloorConnection(
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

  def DownloadParameters(self, parameters):
    """Downloads parameters from shopfloor and saved to state/caches."""
    factory.console.info('Start downloading parameters...')
    shopfloor_client = self.GetShopfloorConnection()
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

  def UploadAuxLogs(self, file_paths, ignore_on_fail=False):
    """Attempts to upload arbitrary file to the shopfloor server."""
    shopfloor_client = self.GetShopfloorConnection()
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

  def PrepareNetwork(self, static_ip_pair):
    def ObtainIp():
      if static_ip_pair[0] is None:
        net_utils.SendDhcpRequest()
      else:
        net_utils.SetEthernetIp(static_ip_pair[0])
      return True if net_utils.GetEthernetIp() else False

    if static_ip_pair is None:
      return

    _PREPARE_NETWORK_TIMEOUT_SECS = 30 # Timeout for network preparation.
    self.template.SetState(MSG_WAITING_ETHERNET)
    factory.console.info('Detecting Ethernet device...')
    net_utils.PollForCondition(condition=(
        lambda: True if net_utils.FindUsableEthDevice() else False),
        timeout=_PREPARE_NETWORK_TIMEOUT_SECS,
        condition_name='Detect Ethernet device')

    # Only setup the IP if required so.
    current_ip = net_utils.GetEthernetIp(net_utils.FindUsableEthDevice())
    if not current_ip or static_ip_pair[1] is True:
      self.template.SetState(MSG_WAITING_IP)
      factory.console.info('Setting up IP address...')
      net_utils.PollForCondition(condition=ObtainIp,
          timeout=_PREPARE_NETWORK_TIMEOUT_SECS,
          condition_name='Setup IP address')

    factory.console.info('Network prepared. IP: %r', net_utils.GetEthernetIp())

  def SelectMode(self, title, choices):
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
    self.template.SetState(
        test_ui.MakeLabel(
            'Please select the %s and press ENTER.<br>' % title) +
        GenerateRadioButtonsHtml(choices) + '<br>&nbsp;'
        '<p id="select-error" class="test-error">&nbsp;')

    # Handle selected value when Enter pressed.
    self.ui.BindKeyJS(
        '\r',
        'window.test.sendTestEvent("select_value",'
        'function(){'
        '  choices = document.getElementsByName("select-value");'
        '  for (var i = 0; i < choices.length; ++i)'
        '    if (choices[i].checked)'
        '      return choices[i].value;'
        '  return "";'
        '}())')
    self.ui.AddEventHandler(
        'select_value',
        lambda event: GetSelectValue(dict_wrapper, event))
    with self.key_pressed:
      self.key_pressed.wait()
    self.ui.UnbindKey('\r')
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
    self.template.SetState(prompt_str)
    self.ui.BindKey(key_to_wait, lambda _: KeyPressed())
    with self.key_pressed:
      self.key_pressed.wait()
    self.ui.UnbindKey(key_to_wait)

  def RunEquipmentCommand(self, function, *args, **kwargs):
    """Wrapper for controling the equipment command.

    The function will only be called if self.equipment_enabled is True.
    """
    if self.equipment_enabled:
      return function(*args, **kwargs)
