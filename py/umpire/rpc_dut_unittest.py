#!/usr/bin/trial --temp-directory=/tmp/_trial_temp/
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import glob
import logging
import mox
import os
import shutil
import time
from twisted.internet import reactor
from twisted.trial import unittest
from twisted.web import server, xmlrpc
import xmlrpclib

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.bundle_selector import SelectRuleset
from cros.factory.umpire.rpc_dut import (
    LogDUTCommands,
    RootDUTCommands,
    UmpireDUTCommands,
    FACTORY_STAGES)
from cros.factory.umpire.umpire_env import UmpireEnvForTest
from cros.factory.umpire.utils import ConcentrateDeferreds
from cros.factory.umpire.version import UMPIRE_VERSION_MAJOR
from cros.factory.umpire.web.xmlrpc import XMLRPCContainer
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils

TEST_RPC_PORT = net_utils.GetUnusedPort()
TESTDIR = os.path.abspath(os.path.join(os.path.split(__file__)[0], 'testdata'))
TESTCONFIG = os.path.join(TESTDIR, 'enable_update.yaml')


class DUTRPCTest(unittest.TestCase):

  def setUp(self):
    self.env = UmpireEnvForTest()
    shutil.copy(TESTCONFIG, self.env.active_config_file)

    # Create empty files for resources.
    for res in ['complete.gz##d41d8cd9',
                'install_factory_toolkit.run#ftk_v0.1#d41d8cd9',
                'efi.gz##d41d8cd9',
                'firmware.gz#bios_v0.3:ec_v0.2#d41d8cd9',
                'hwid.gz##d41d8cd9',
                'vmlinux##d41d8cd9',
                'oem.gz##d41d8cd9',
                'rootfs-release.gz#release_v9876.0.0#d41d8cd9',
                'rootfs-test.gz#test_v5432.0.0#d41d8cd9',
                'install_factory_toolkit.run#ftk_v0.4#d41d8cd9',
                'state.gz##d41d8cd9']:
      file_utils.TouchFile(os.path.join(self.env.resources_dir, res))

    self.env.LoadConfig()
    self.mox = mox.Mox()
    self.proxy = xmlrpc.Proxy('http://localhost:%d' % TEST_RPC_PORT,
                              allowNone=True)
    root_commands = RootDUTCommands(self.env)
    umpire_dut_commands = UmpireDUTCommands(self.env)
    log_dut_commands = LogDUTCommands(self.env)
    xmlrpc_resource = XMLRPCContainer()
    xmlrpc_resource.AddHandler(root_commands)
    xmlrpc_resource.AddHandler(umpire_dut_commands)
    xmlrpc_resource.AddHandler(log_dut_commands)
    self.twisted_port = reactor.listenTCP(  # pylint: disable=E1101
        TEST_RPC_PORT, server.Site(xmlrpc_resource))
    # The device info that matches TESTCONFIG
    self.device_info = {
      'x_umpire_dut': {
          'mac': 'aa:bb:cc:dd:ee:ff',
          'sn': '0C1234567890',
          'mlb_sn': 'SN001',
          'stage': 'SMT'},
      'components': {
          'device_factory_toolkit': 'd41d8cd9',
          'rootfs_release': 'release_v9876.0.0',
          'rootfs_test': 'test_v5432.0.0',
          'firmware_ec': 'ec_v0.2',
          'firmware_bios': 'bios_v0.3'}}

  def tearDown(self):
    self.twisted_port.stopListening()
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def Call(self, function, *args):
    return self.proxy.callRemote(function, *args)

  def testPing(self):
    def CheckResult(result):
      self.assertEqual(result, {'version': UMPIRE_VERSION_MAJOR})
      return result

    d = self.Call('Ping')
    d.addCallback(CheckResult)
    return d

  def testTime(self):
    def CheckTime(result):
      timediff = time.time() - result
      logging.debug('testTime timediff = %f', timediff)
      self.assertTrue(timediff <= 0.1)
      return result

    d = self.Call('GetTime')
    d.addCallback(CheckTime)
    return d

  def testListParameters(self):
    def CheckList(result):
      logging.debug('list parameters = %s', str(result))
      self.assertEqual(result, [])
      return result

    d = self.Call('ListParameters', 'parameters_*')
    d.addCallback(CheckList)
    return d

  def testGetUpdateNoUpdate(self):
    def CheckNoUpdate(result):
      logging.debug('no update result: %s', str(result))
      for unused_component, update_info in result.iteritems():
        self.assertFalse(update_info['needs_update'])
      return result

    deferreds = []
    for stage in FACTORY_STAGES:
      noupdate_info = copy.deepcopy(self.device_info)
      noupdate_info['x_umpire_dut']['stage'] = stage
      d = self.Call('GetUpdate', noupdate_info)
      d.addCallback(CheckNoUpdate)
      deferreds.append(d)
    return ConcentrateDeferreds(deferreds)

  def testGetUpdate(self):
    def CheckSingleComponentUpdate(result):
      logging.debug('update result:\n\t%r', result)
      self.assertEqual(1, sum(result[component]['needs_update'] for component in
                              result))
      return result

    update_info = copy.deepcopy(self.device_info)
    ruleset = SelectRuleset(self.env.config, update_info['x_umpire_dut'])
    logging.debug('selected ruleset: %s', str(ruleset))
    deferreds = []
    for component, stage_range in ruleset['enable_update'].iteritems():
      # Make a new copy.
      update_info = copy.deepcopy(self.device_info)
      update_info['x_umpire_dut']['stage'] = stage_range[0]
      update_info['components'][component] = 'force update'
      deferred = self.Call('GetUpdate', update_info)
      # There's only one component needs update.
      deferred.addCallback(CheckSingleComponentUpdate)
      deferreds.append(deferred)
    return ConcentrateDeferreds(deferreds)

  def testUploadReport(self):
    def CheckTrue(result):
      self.assertEqual(result, True)
      return result

    def CheckReport(content, namestrings=None):
      if namestrings is None:
        namestrings = []
      report_files = glob.glob(os.path.join(
          self.env.umpire_data_dir, 'report', '*', '*'))
      logging.debug('report files: %r', report_files)
      self.assertTrue(report_files)
      report_path = report_files[0]
      with open(report_path, 'rb') as f:
        self.assertEqual(f.read(), content)
      for name in namestrings:
        self.assertIn(name, report_path)
      return True

    d = self.Call('UploadReport', 'serial1234', xmlrpclib.Binary('content'),
                  'rpt_name5678', 'stage90')
    d.addCallback(CheckTrue)
    d.addCallback(lambda _: CheckReport(
        'content', namestrings=['serial1234', 'rpt_name5678', 'stage90',
                                'report', 'rpt.xz']))
    return d

  def testUploadEvent(self):
    def CheckTrue(result):
      self.assertEqual(result, True)
      return result

    def CheckEvent(content):
      event_files = glob.glob(os.path.join(
          self.env.umpire_data_dir, 'eventlog', '*', '*'))
      logging.debug('event files: %r', event_files)
      self.assertTrue(event_files)
      event_path = event_files[0]
      with open(event_path, 'r') as f:
        self.assertEqual(f.read(), content)
      return True

    d = self.Call('UploadEvent', 'event_log_name', '123')
    d.addCallback(CheckTrue)
    d.addCallback(lambda _: CheckEvent('123'))
    d.addCallback(lambda _: self.Call('UploadEvent', 'event_log_name', '456'))
    d.addCallback(CheckTrue)
    d.addCallback(lambda _: CheckEvent('123456'))
    return d


if os.environ.get('LOG_LEVEL'):
  logging.basicConfig(
      level=logging.DEBUG,
      format='%(levelname)5s %(message)s')
else:
  logging.disable(logging.CRITICAL)
