# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""RF test flow framework.

It defines common portion of various fixture involved tests.
"""

import logging
import os
import threading
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import EventLog
from cros.factory.goofy.goofy import CACHES_DIR
from cros.factory.test import factory
from cros.factory.test import leds
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.utils import net_utils

class RfFramework(object):
  NORMAL_MODE = 'Normal'
  DETAIL_PROMPT = 'Detail prompts'
  DETAIL_PROMPT_WITHOUT_EQUIPMENT = 'Detail prompts without equipment'

  ARGS = [
      Arg('category', str,
          'Describes what category it is, should be one of calibration,'
          'production, conductive or debug.'),
      Arg('config_file', str,
          'Describes where configuration locates.'),
      Arg('parameters', list,
          'A list of regular expressions indicates parameters to download from '
          'shopfloor server.', default=list()),
      Arg('blinking_pattern', list,
          'A list of blinking state that will be passed to Blinker for '
          'inside shield-box primary test. '
          'More details of format could be found under Blinker.__init__()',
          default=[(0b111, 0.10), (0b000, 0.10)], ),
      Arg('static_ip', str,
          'Static IP for the DUT; default to acquire one from DHCP.',
          default=None, optional=True),
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

  def setUp(self):
    self.event_log = EventLog.ForAutoTest()
    self.caches_dir = os.path.join(CACHES_DIR, 'parameters')
    self.interactive_mode = False
    self.equipment_enabled = True
    self.mode = self.NORMAL_MODE
    # Initiate an UI
    self.ui = test_ui.UI()
    # TODO(itspeter): Set proper title and context for initial screen.
    self.template = ui_templates.OneSection(self.ui)
    self.key_pressed = threading.Condition()
    self.ui_thread = self.ui.Run(blocking=False)
    self.failures = []

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
    if self.args.pre_test_outside_shield_box:
      self.template.SetState('Preparing network.')
      self.PrepareNetwork()
      if len(self.args.parameters) > 0:
        self.template.SetState('Downloading parameters.')
        self.DownloadParameters()

      # Load the main configuration.
      with open(os.path.join(
          self.caches_dir, self.args.config_file), "r") as fd:
        self.config = yaml.load(fd.read())

      self.template.SetState('Runing outside shield box test.')
      self.PreTestOutsideShieldBox()
      self.EnterFactoryMode()
      self.Prompt(
          'Procedure outside shield-box is completed.<br>'
          'Please press SPACE key to continue.',
          force_prompt=True)

    try:
      if self.args.pre_test_inside_shield_box:
        self.template.SetState('Preparing network.')
        self.PrepareNetwork()
        self.template.SetState('Runing pilot test inside shield box.')
        self.PreTestInsideShieldBox()
        # TODO(itspeter): Support multiple language in prompt.
        self.Prompt(
            'Precheck passed.<br>'
            'Please press SPACE key to continue after shield-box is closed.',
            force_prompt=True)

      # Primary test
      # TODO(itspeter): Timing on PrimaryTest().
      self.template.SetState('Runing primary test.')
      with leds.Blinker(self.args.blinking_pattern):
        self.PrimaryTest()

      # Light all LEDs to indicates test is completed.
      leds.SetLeds(leds.LED_SCR|leds.LED_NUM|leds.LED_CAP)
      self.Prompt(
          'Shield-box required testing finished.<br>'
          'Rest of the test can be executed without a shield-box.<br>'
          'Please press SPACE key to continue.',
          force_prompt=True)
      leds.SetLeds(0)

      # Post-test
      if self.args.post_test:
        self.template.SetState('Runing post test.')
        self.PostTest()

    finally:
      self.ExitFactoryMode()

    # Fail the test if failure happened.
    if len(self.failures) > 0:
      self.ui.Fail('\n'.join(self.failures))
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

  def DownloadParameters(self):
    """Downloads parameters from shopfloor."""
    raise NotImplementedError(
        'Called without implementing DownloadParameters')

  def EnterFactoryMode(self):
    """Prepares factory specific environment."""
    raise NotImplementedError(
        'Called without implementing EnterFactoryMode')

  def ExitFactoryMode(self):
    """Exits factory specific environment.

    This function will be called when test exits."""
    raise NotImplementedError(
        'Called without implementing ExitFactoryMode')

  def IsInRange(self, observed, threshold_min, threshold_max):
    """Returns True if threshold_min <= observed <= threshold_max.

    If either thresholds are None, then the comparison will always succeed."""
    if threshold_min is not None and observed < threshold_min:
      return False
    if threshold_max is not None and observed > threshold_max:
      return False
    return True

  def FormattedPower(self, power, format_str='%7.2f'):
    """Returns a formatted power while allowing power be a None."""
    return 'None' if power is None else (format_str % power)

  def PrepareNetwork(self):
    def ObtainIp():
      if self.args.static_ip is None:
        net_utils.SendDhcpRequest()
      else:
        net_utils.SetEthernetIp(self.args.static_ip)
      return True if net_utils.GetEthernetIp() else False

    _PREPARE_NETWORK_TIMEOUT_SECS = 30 # Timeout for network preparation.
    factory.console.info('Detecting Ethernet device...')
    net_utils.PollForCondition(condition=(
        lambda: True if net_utils.FindUsableEthDevice() else False),
        timeout=_PREPARE_NETWORK_TIMEOUT_SECS,
        condition_name='Detect Ethernet device')

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
