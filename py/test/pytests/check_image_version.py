# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# DESCRIPTION :
# This factory test checks image version in lsb-release. If the version doesn't
# match what's provided in the test argument, flash netboot firmware if it is
# provided.

from distutils.version import StrictVersion, LooseVersion
import logging
import time
import unittest

from cros.factory.event_log import Log
from cros.factory.system import SystemInfo, SystemStatus
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.utils.process_utils import Spawn


_TEST_TITLE = test_ui.MakeLabel('Check Image Version', u'检查映像版本')

_CSS = """
.start-font-size {
  font-size: 2em;
}
"""

# Messages for tasks
_MSG_VERSION_MISMATCH = test_ui.MakeLabel(
    'Factory image version is incorrect. Please re-image this device.',
    u'映像版本不正确，请重新安装。',
    'start-font-size test-error')
_MSG_NETWORK = test_ui.MakeLabel(
    'Please connect to ethernet.',
    u'请连接到以太网。')
_MSG_NETBOOT = test_ui.MakeLabel(
    'Factory image version is incorrect. Press space to re-image.',
    u'映像版本不正确，请按空白键重新安装。')
_MSG_REIMAGING = test_ui.MakeLabel(
    'Flashing netboot firmware...',
    u'烧录网路开机固件...')
_MSG_FLASH_ERROR = test_ui.MakeLabel(
    'Error flashing netboot firmware!',
    u'烧录网路开机固件失败',
    'start-font-size test-error')

# Javascripts and HTML for tasks
_JS_SPACE = '''
    function enableSpaceKeyPressListener() {
      window.addEventListener(
          "keypress",
          function(event) {
            if (event.keyCode == " ".charCodeAt(0)) {
              window.test.sendTestEvent("space_pressed", {});
            }
          });
      window.focus();
    }'''
_LSB_RELEASE_PATH = '/etc/lsb-release'


class ImageCheckTask(FactoryTask):
  def __init__(self, test): # pylint: disable=W0231
    self._test = test

  def CheckNetwork(self):
    while not SystemStatus().eth_on:
      time.sleep(0.5)
      self._test.template.SetState(_MSG_NETWORK)

  def PromptReimage(self):
    self._test.template.SetState(_MSG_NETBOOT)
    self._test.ui.RunJS(_JS_SPACE)
    self._test.ui.CallJSFunction('enableSpaceKeyPressListener')
    self._test.ui.AddEventHandler('space_pressed', lambda _: self.Reimage())

  def Reimage(self):
    self._test.template.SetState(_MSG_REIMAGING)
    try:
      Spawn(['/usr/local/factory/bin/flash_netboot', '-y'] +
            (['-i', self._test.args.netboot_fw]
             if self._test.args.netboot_fw else []),
            check_call=True, log=True, log_stderr_on_error=True)
      Spawn(['reboot'])
    except: # pylint: disable=W0702
      self._test.template.SetState(_MSG_FLASH_ERROR)

  def Run(self):
    ver = SystemInfo().factory_image_version
    Log('image_version', version=ver)
    version_format = (LooseVersion if self._test.args.loose_version
                      else StrictVersion)
    logging.info('Using version format: %r', version_format.__name__)
    logging.info('current version: %r', ver)
    logging.info('expected version: %r', self._test.args.min_version)
    if version_format(ver) < version_format(self._test.args.min_version):
      factory.console.error('Current factory image version is incorrect: %s',
                            ver)
      if self._test.args.reimage:
        self.CheckNetwork()
        if self._test.args.require_space:
          self.PromptReimage()
        else:
          self.Reimage()
      else:
        self._test.template.SetState(_MSG_VERSION_MISMATCH)
      return
    self.Pass()


class CheckImageVersionTest(unittest.TestCase):
  ARGS = [
    Arg('min_version', str, 'Minimum allowed factory image version.'),
    Arg('loose_version', bool, 'Allow any version number representation.',
        default=False),
    Arg('netboot_fw', str, 'The path to netboot firmware image.',
        default=None, optional=True),
    Arg('reimage', bool, 'True to re-image when image version mismatch.',
        default=True, optional=True),
    Arg('require_space', bool,
        'True to require a space key press before reimaging.',
        default=True, optional=True)]

  def __init__(self, *args, **kwargs):
    super(CheckImageVersionTest, self).__init__(*args, **kwargs)
    self._task_list = [ImageCheckTask(self)]
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_CSS)
    self.template.SetTitle(_TEST_TITLE)

  def runTest(self):
    FactoryTaskManager(self.ui, self._task_list).Run()
