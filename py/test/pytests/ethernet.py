# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for basic ethernet connectivity."""

import re
import logging
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.device import device_utils
from cros.factory.test import event as test_event
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils.net_utils import DEFAULT_ETHERNET_NAME_PATTERNS

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
      Arg('iface', str, 'Interface name for testing.', default=None,
          optional=True),
      Arg('interface_name_patterns', list, 'The ethernet interface name patterns',
          default=DEFAULT_ETHERNET_NAME_PATTERNS, optional=True),
      Arg('link_only', bool, 'Only test if link is up or not', default=False),
      Arg('use_swconfig', bool, 'Use swconfig for polling link status.',
          default=False),
      Arg('swconfig_switch', str, 'swconfig switch name.', default='switch0'),
      Arg('swconfig_ports', (int, list), 'swconfig port numbers. Either '
          'a single int or a list of int.', default=None, optional=True),
      Arg('swconfig_expected_speed', (int, list),
          ('expected link speed, if a list is given, each integer in the list '
           'will be paired with each port in swconfig_ports.'),
          default=None, optional=True)
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_CSS_ETHERNET)
    self.template.SetState(_HTML_ETHERNET)

    if self.args.auto_start:
      self.ui.AddEventHandler('StartTest', self.StartTest)
      self.ui.PostEvent(test_event.Event(test_event.Event.Type.TEST_UI_EVENT,
                                         subtype='StartTest'))
    else:
      self.ui.BindKey(test_ui.SPACE_KEY, self.StartTest)
    self.ui.SetHTML(_MSG_ETHERNET_INFO, id='ethernet_title')
    if bool(self.args.test_url) != bool(self.args.md5sum):
      raise ValueError('Should both assign test_url and md5sum.')
    if self.args.use_swconfig:
      if not self.args.link_only:
        raise ValueError('Should set link_only=True if use_swconfig is set.')
      if self.args.swconfig_ports is None:
        raise ValueError('Should assign swconfig_ports if use_swconfig is'
                         'set.')
    elif self.args.link_only and not self.args.iface:
      raise ValueError('Should assign iface if link_only is set.')

  def GetEthernetInterfaces(self):
    interfaces = []
    for pattern in self.args.interface_name_patterns:
      interfaces += [
          self.dut.path.basename(path) for path in
          self.dut.Glob('/sys/class/net/' + pattern)]
    return interfaces

  def GetInterface(self):
    devices = self.GetEthernetInterfaces()
    if self.args.iface:
      return self.args.iface if self.args.iface in devices else None
    else:
      return self.GetCandidateInterface()

  def GetCandidateInterface(self):
    devices = self.GetEthernetInterfaces()
    if not devices:
      self.fail('No ethernet interface')
      return None
    else:
      for dev in devices:
        if 'usb' not in self.dut.path.realpath('/sys/class/net/%s' % dev):
          factory.console.info('Built-in ethernet device %s found.', dev)
          self.dut.CheckCall(['ifconfig', dev, 'up'], log=True)
          return dev
    return None

  def GetFile(self):
    self.dut.CheckCall(['rm', '-f', _LOCAL_FILE_PATH])
    logging.info('Try connecting to %s', self.args.test_url)

    try:
      self.dut.CheckCall(['wget', '-O', _LOCAL_FILE_PATH, '-T', '2',
                          self.args.test_url], log=True)
    except Exception as e:
      factory.console.info('Failed to get file: %s', e)
    else:
      md5sum_output = self.dut.CheckOutput(
          ['md5sum', _LOCAL_FILE_PATH], log=True).strip().split()[0]
      logging.info('Got local file md5sum %s', md5sum_output)
      logging.info('Golden file md5sum %s', self.args.md5sum)
      if md5sum_output == self.args.md5sum:
        factory.console.info('Successfully connected to %s', self.args.test_url)
        return True
      else:
        factory.console.info('md5 checksum error')
    return False

  def CheckLinkSimple(self, dev):
    if dev:
      status = self.dut.ReadSpecialFile(
          '/sys/class/net/%s/carrier' % dev).strip()
      if int(status):
        self.ui.Pass()
        return True
      else:
        self.ui.Fail('Link is down on dev %s' % dev)
        return False

  def GetEthernetIp(self, interface):
    output = self.dut.CallOutput(
        ['ip', 'addr', 'show', 'dev', interface], log=True)
    match = re.search(r'^\s+inet ([.0-9]+)/([0-9]+)', output, re.MULTILINE)
    if match:
      return match.group(1)
    else:
      return None

  def CheckLinkSWconfig(self):
    if type(self.args.swconfig_ports) == int:
      self.args.swconfig_ports = [self.args.swconfig_ports]

    if not isinstance(self.args.swconfig_expected_speed, list):
      swconfig_expected_speed = (
          [self.args.swconfig_expected_speed] * len(self.args.swconfig_ports))
    else:
      swconfig_expected_speed = self.args.swconfig_expected_speed

    self.assertEqual(len(self.args.swconfig_ports),
                     len(swconfig_expected_speed))

    for port, speed in zip(self.args.swconfig_ports, swconfig_expected_speed):
      status = self.dut.CheckOutput(
          ['swconfig', 'dev', self.args.swconfig_switch,
           'port', str(port), 'get', 'link'])
      if 'up' in status:
        factory.console.info('Link is up on switch %s port %d',
                             self.args.swconfig_switch, port)
        if speed:
          speed_str = '{0}baseT'.format(speed)
          if speed_str not in status:
            self.ui.Fail('The negociated speed is not expected (%r not in %r)' %
                         (speed_str, status))
      else:
        self.ui.Fail('Link is down on switch %s port %d' %
                     (self.args.swconfig_switch, port))
        return False

    self.ui.Pass()
    return True

  def StartTest(self, event):
    del event  # Unused.
    # Only retry 5 times
    for unused_i in xrange(5):
      eth = self.GetInterface()
      if self.args.link_only:
        if not self.args.use_swconfig:
          if self.CheckLinkSimple(eth):
            break
        else:
          if self.CheckLinkSWconfig():
            break
      else:
        if eth:
          if self.args.test_url is None:
            ethernet_ip = self.GetEthernetIp(eth)
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

    if self.args.link_only:
      self.ui.Fail('Cannot find interface %s' % self.args.iface)
    elif self.args.test_url is None:
      self.ui.Fail('Cannot get ethernet IP')
    else:
      self.ui.Fail('Failed to download url %s' % self.args.test_url)

  def runTest(self):
    self.ui.Run()
