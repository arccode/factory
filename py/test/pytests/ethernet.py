# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for basic ethernet connectivity."""

import logging

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import net_utils


_LOCAL_FILE_PATH = '/tmp/test'


class EthernetTest(test_case.TestCase):
  """Test built-in ethernet port"""
  ARGS = [
      Arg('auto_start', bool, 'Auto start option.', default=False),
      Arg('test_url', str, 'URL for testing data transmission.',
          default=None),
      Arg('md5sum', str, 'md5sum of the test file in test_url.',
          default=None),
      Arg('retry_interval_msecs', int,
          'Milliseconds before next retry.',
          default=1000),
      Arg('iface', str, 'Interface name for testing.', default=None),
      Arg('interface_name_patterns', list,
          'The ethernet interface name patterns',
          default=net_utils.DEFAULT_ETHERNET_NAME_PATTERNS),
      Arg('link_only', bool, 'Only test if link is up or not', default=False),
      Arg('use_swconfig', bool, 'Use swconfig for polling link status.',
          default=False),
      Arg('swconfig_switch', str, 'swconfig switch name.', default='switch0'),
      Arg('swconfig_ports', (int, list), 'swconfig port numbers. Either '
          'a single int or a list of int.', default=None),
      Arg('swconfig_expected_speed', (int, list),
          'expected link speed, if a list is given, each integer in the list '
          'will be paired with each port in swconfig_ports.',
          default=None)
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui.ToggleTemplateClass('font-large', True)
    self.ui.SetState(
        _('Please plug ethernet cable into built-in ethernet port<br>'
          'Press space to start.'))

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
          self.dut.path.basename(path)
          for path in self.dut.Glob('/sys/class/net/' + pattern)
      ]
    return interfaces

  def GetInterface(self):
    devices = self.GetEthernetInterfaces()
    if self.args.iface:
      if self.args.iface in devices:
        if self.CheckNotUsbLanDongle(self.args.iface):
          return self.args.iface
        session.console.info('Not a built-in ethernet device.')
        return None
      return None
    return self.GetCandidateInterface()

  def GetCandidateInterface(self):
    devices = self.GetEthernetInterfaces()
    if not devices:
      self.FailTask('No ethernet interface')
    for dev in devices:
      if self.CheckNotUsbLanDongle(dev):
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
      session.console.info('Failed to get file: %s', e)
    else:
      md5sum_output = self.dut.CheckOutput(
          ['md5sum', _LOCAL_FILE_PATH], log=True).strip().split()[0]
      logging.info('Got local file md5sum %s', md5sum_output)
      logging.info('Golden file md5sum %s', self.args.md5sum)
      if md5sum_output == self.args.md5sum:
        session.console.info('Successfully connected to %s', self.args.test_url)
        return True
      session.console.info('md5 checksum error')
    return False

  def CheckLinkSimple(self, dev):
    status = self.dut.ReadSpecialFile('/sys/class/net/%s/carrier' % dev).strip()
    speed = self.dut.ReadSpecialFile('/sys/class/net/%s/speed' % dev).strip()
    if not int(status):
      self.FailTask('Link is down on dev %s' % dev)

    if int(speed) != 1000:
      self.FailTask('Speed is %sMb/s not 1000Mb/s on dev %s' % (speed, dev))

    self.PassTask()

  def CheckNotUsbLanDongle(self, device):
    if 'usb' not in self.dut.path.realpath('/sys/class/net/%s' % device):
      session.console.info('Built-in ethernet device %s found.', device)
      return True
    return False

  def CheckLinkSWconfig(self):
    if isinstance(self.args.swconfig_ports, int):
      self.args.swconfig_ports = [self.args.swconfig_ports]

    if not isinstance(self.args.swconfig_expected_speed, list):
      swconfig_expected_speed = (
          [self.args.swconfig_expected_speed] * len(self.args.swconfig_ports))
    else:
      swconfig_expected_speed = self.args.swconfig_expected_speed

    self.assertEqual(
        len(self.args.swconfig_ports),
        len(swconfig_expected_speed),
        "Length of swconfig_ports and swconfig_expcted_speed doesn't match.")

    for port, speed in zip(self.args.swconfig_ports, swconfig_expected_speed):
      status = self.dut.CheckOutput(
          ['swconfig', 'dev', self.args.swconfig_switch,
           'port', str(port), 'get', 'link'])

      if 'up' not in status:
        self.FailTask('Link is down on switch %s port %d' %
                      (self.args.swconfig_switch, port))

      session.console.info('Link is up on switch %s port %d',
                           self.args.swconfig_switch, port)
      if speed:
        speed_str = '{0}baseT'.format(speed)
        if speed_str not in status:
          self.FailTask('The negotiated speed is not expected (%r not in %r)' %
                        (speed_str, status))

    self.PassTask()

  def runTest(self):
    if not self.args.auto_start:
      self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

    if self.args.use_swconfig:
      self.CheckLinkSWconfig()

    # Only retry 5 times
    for unused_i in range(5):
      eth = self.GetInterface()
      if eth:
        if self.args.link_only:
          self.CheckLinkSimple(eth)
        elif self.args.test_url:
          if self.GetFile():
            self.PassTask()
        else:
          ethernet_ip, unused_prefix_number = net_utils.GetEthernetIp(eth)
          if ethernet_ip:
            session.console.info('Get ethernet IP %s for %s', ethernet_ip, eth)
            self.PassTask()
      self.Sleep(self.args.retry_interval_msecs / 1000.0)

    if self.args.link_only:
      self.FailTask('Cannot find interface %s' % self.args.iface)
    elif self.args.test_url:
      self.FailTask('Failed to download url %s' % self.args.test_url)
    else:
      self.FailTask('Cannot get ethernet IP')
