# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""RF test flow framework.

It defines common portion of various fixture involved tests.
"""

import threading

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import EventLog
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.utils import net_utils

class RfFramework(object):
  ARGS = [
      Arg('category', str,
          'Describes what category it is, should be one of calibration,'
          'production, conductive or debug.'),
      Arg('parameters', list,
          'A list of regular expressions indicates parameters to download from'
          'shopfloor server.', default=list()),
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

  def setUp(self):
    self.event_log = EventLog.ForAutoTest()
    self.interactive_mode = False
    # Initiate an UI
    self.ui = test_ui.UI()
    # TODO(itspeter): Set proper title and context for initial screen.
    self.template = ui_templates.OneSection(self.ui)
    self.key_pressed = threading.Condition()
    self.ui.Run(blocking=False)

    # Allowed user to apply fine controls in engineering_mode
    if self.ui.InEngineeringMode():
      # TODO(itspeter): expose more options in run-time.
      factory.console.debug('engineering mode detected.')

  def runTest(self):
    if self.args.pre_test_outside_shield_box:
      self.PrepareNetwork()
      if len(self.args.parameters) > 0:
        self.DownloadParameters()

      self.PreTestOutsideShieldBox()

    if self.args.pre_test_inside_shield_box:
      self.PrepareNetwork()
      self.PreTestInsideShieldBox()
      # TODO(itspeter): Support multiple language in prompt.
      self.Prompt(
          'Precheck passed.<br>'
          'Please press SPACE key to continue after shield-box is closed.',
          force_prompt=True)

    # Primary test
    # TODO(itspeter): Blinking the keyboard indicator.
    # TODO(itspeter): Timing on PrimaryTest().
    self.PrimaryTest()
    self.Prompt('Shield-box required testing finished.<br>'
                'Rest of the test can be executed without a shield-box.<br>'
                'Please press SPACE key to continue.',
                force_prompt=True)

    # Post-test
    if self.args.post_test:
      self.PostTest()

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
