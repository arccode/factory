# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for basic ethernet connectivity."""

import logging
import os
import time
import unittest
import urllib2

from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils.file_utils import TryUnlink
from cros.factory.utils.net_utils import GetEthernetInterfaces
from cros.factory.utils.net_utils import GetEthernetIp
from cros.factory.utils.process_utils import Spawn, CheckOutput

_MSG_ETHERNET_INFO = test_ui.MakeLabel(
    'Please plug ethernet cable into built-in ethernet port<br>'
    'Press space to start.',
    zh='请插入网路线到内建网路埠<br>'
    '压下空白键开始测试',
    css_class='ethernet-test-info')

_HTML_ETHERNET = """
<table style="width: 70%%; margin: auto;">
  <tr>
    <td align="center"><div id="ethernet_title"></div></td>
  </tr>
</table>
"""

_CSS_ETHERNET = """
  .ethernet-test-info { font-size: 2em; }
"""

_JS_ETHERNET = """
init = function(autostart) {
  if (autostart) {
    test.sendTestEvent("StartTest", '');
  }
}
window.onkeydown = function(event) {
  if (event.keyCode == 32) { // space
    test.sendTestEvent("StartTest", '');
  }
}
"""

_LOCAL_FILE_PATH = '/tmp/test'

class EthernetTest(unittest.TestCase):
  """Test built-in ethernet port"""
  ARGS = [
    Arg('auto_start', bool, 'Auto start option.', False),
    Arg('test_url', str, 'URL for testing data transmission.',
        optional=True),
    Arg('md5sum', str, 'md5sum of the test file in test_url.',
        optional=True),
    Arg('retry_interval_msecs', int,
        'Milliseconds before next retry.',
        default=1000),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_CSS_ETHERNET)
    self.template.SetState(_HTML_ETHERNET)
    self.ui.RunJS(_JS_ETHERNET)
    self.ui.SetHTML(_MSG_ETHERNET_INFO, id='ethernet_title')
    self.ui.AddEventHandler('StartTest', self.StartTest)
    self.ui.CallJSFunction('init', self.args.auto_start)
    if bool(self.args.test_url) != bool(self.args.md5sum):
      raise ValueError('Should both assign test_url and md5sum.')

  def GetCandidateInterface(self):
    devices = GetEthernetInterfaces()
    if not devices:
      self.fail('No ethernet interface')
      return None
    else:
      for dev in devices:
        if 'usb' not in os.path.realpath('/sys/class/net/%s' % dev):
          factory.console.info('Built-in ethernet device %s found.', dev)
          Spawn(['ifconfig', dev, 'up'], check_call=True, log=True)
          return dev
    return None

  def GetFile(self):
    TryUnlink(_LOCAL_FILE_PATH)
    logging.info('Try connecting to %s', self.args.test_url)
    try:
      remote_file = urllib2.urlopen(self.args.test_url, timeout=2)
    except urllib2.HTTPError as e:
      factory.console.info(
          'Connected to %s but got status code %d: %s.',
          self.args.test_url, e.code, e.reason)
    except urllib2.URLError as e:
      factory.console.info(
          'Failed to connect to %s: %s.', self.args.test_url, e.reason)
    else:
      with open(_LOCAL_FILE_PATH, "w") as local_file:
        local_file.write(remote_file.read())
        local_file.flush()
        os.fdatasync(local_file)
      md5sum_output = CheckOutput(['md5sum', _LOCAL_FILE_PATH],
                                  log=True).strip().split()[0]
      logging.info('Got local file md5sum %s', md5sum_output)
      logging.info('Golden file md5sum %s', self.args.md5sum)
      if md5sum_output == self.args.md5sum:
        factory.console.info('Successfully connected to %s',
                             self.args.test_url)
        return True
      else:
        factory.console.info('md5 checksum error')
    return False

  def StartTest(self, event):  # pylint: disable=W0613
    # Only retry 5 times
    for i in xrange(5): # pylint: disable=W0612
      eth = self.GetCandidateInterface()
      if eth:
        if self.args.test_url is None:
          ethernet_ip = GetEthernetIp(eth)
          if ethernet_ip:
            factory.console.info('Get ethernet IP %s for %s',
                ethernet_ip, eth)
            self.ui.Pass()
            break
        else:
          if self.GetFile():
            self.ui.Pass()
            break
      time.sleep(self.args.retry_interval_msecs / 1000.0)

    if self.args.test_url is None:
      self.ui.Fail('Cannot get ethernet IP')
    else:
      self.ui.Fail('Failed to download url %s' % self.args.test_url)

  def runTest(self):
    self.ui.Run()
