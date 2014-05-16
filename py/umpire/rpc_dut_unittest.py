#!/usr/bin/trial --temp-directory=/tmp/_trial_temp/
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import logging
import mox
import os
import time
from twisted.internet import reactor
from twisted.trial import unittest
from twisted.web import server, xmlrpc

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.bundle_selector import SelectRuleset
from cros.factory.umpire.rpc_dut import (
    BasicDUTCommands,
    CommonDUTCommands,
    FACTORY_STAGES)
from cros.factory.umpire.umpire_env import UmpireEnv
from cros.factory.umpire.utils import ConcentrateDeferreds
from cros.factory.umpire.version import UMPIRE_VERSION_MAJOR
from cros.factory.umpire.web.xmlrpc import XMLRPCContainer


TEST_RPC_PORT = 8088
TESTDIR = os.path.abspath(os.path.join(os.path.split(__file__)[0], 'testdata'))
TESTCONFIG = os.path.join(TESTDIR, 'enable_update.yaml')


class DUTRPCTest(unittest.TestCase):

  def setUp(self):
    self.env = UmpireEnv()
    self.env.base_dir = TESTDIR
    self.env.LoadConfig(custom_path=TESTCONFIG)
    self.mox = mox.Mox()
    self.proxy = xmlrpc.Proxy('http://localhost:%d' % TEST_RPC_PORT,
                              allowNone=True)
    basic_commands = BasicDUTCommands(self.env)
    common_commands = CommonDUTCommands(self.env)
    xmlrpc_resource = XMLRPCContainer()
    xmlrpc_resource.AddHandler(basic_commands)
    xmlrpc_resource.AddHandler(common_commands)
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
          'device_factory_toolkit': '00000002',
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
      for dummy_component, update_info in result.iteritems():
        self.assertFalse(update_info['need_update'])
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
      self.assertEqual(1, sum(result[component]['need_update'] for component in
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


if os.environ.get('LOG_LEVEL'):
  logging.basicConfig(
      level=logging.DEBUG,
      format='%(levelname)5s %(message)s')
else:
  logging.disable(logging.CRITICAL)
