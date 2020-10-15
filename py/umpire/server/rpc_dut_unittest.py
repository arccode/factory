#!/usr/bin/env python3
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os
import shutil
import time
import xmlrpc.client

from twisted.internet import reactor
from twisted.trial import unittest
from twisted.web import server
from twisted.web import xmlrpc as twisted_xmlrpc

from cros.factory.umpire import common
from cros.factory.umpire.server import daemon
from cros.factory.umpire.server import rpc_dut
from cros.factory.umpire.server import umpire_env
from cros.factory.umpire.server import unittest_helper
from cros.factory.umpire.server.web import xmlrpc as umpire_xmlrpc
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils


# Forward to the correct executer with additional arguments.
if __name__ == '__main__':
  unittest_helper.ExecScriptWithTrial()


TEST_RPC_PORT = net_utils.FindUnusedPort()
TESTDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'testdata'))
TESTCONFIG = os.path.join(TESTDIR, 'minimal_empty_services_umpire.json')


class DUTRPCTest(unittest.TestCase):

  def setUp(self):
    self.env = umpire_env.UmpireEnvForTest()
    shutil.copy(TESTCONFIG, self.env.active_config_file)

    self.env.LoadConfig()
    self.proxy = twisted_xmlrpc.Proxy(
        b'http://%s:%d' % (net_utils.LOCALHOST.encode('utf-8'), TEST_RPC_PORT),
        allowNone=True)
    self.daemon = daemon.UmpireDaemon(self.env)
    root_commands = rpc_dut.RootDUTCommands(self.daemon)
    umpire_dut_commands = rpc_dut.UmpireDUTCommands(self.daemon)
    log_dut_commands = rpc_dut.LogDUTCommands(self.daemon)
    xmlrpc_resource = umpire_xmlrpc.XMLRPCContainer()
    xmlrpc_resource.AddHandler(root_commands)
    xmlrpc_resource.AddHandler(umpire_dut_commands)
    xmlrpc_resource.AddHandler(log_dut_commands)
    self.twisted_port = reactor.listenTCP(
        TEST_RPC_PORT, server.Site(xmlrpc_resource))
    # The device info that matches TESTCONFIG
    self.device_info = {
        'x_umpire_dut': {
            'mac': 'aa:bb:cc:dd:ee:ff',
            'sn': '0C1234567890',
            'mlb_sn': 'SN001',
            'stage': 'SMT'},
        'components': {
            'device_factory_toolkit': '1234'}}

  def tearDown(self):
    self.twisted_port.stopListening()
    self.env.Close()

  def Call(self, function, *args):
    return self.proxy.callRemote(function, *args)

  def testPing(self):
    def CheckResult(result):
      self.assertEqual(result, {
          'version': common.UMPIRE_DUT_RPC_VERSION,
          'project': None
      })
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
      self.assertEqual(file_utils.ReadFile(report_path), content)
      for name in namestrings:
        self.assertIn(name, report_path)
      return True

    d = self.Call('UploadReport', 'serial1234',
                  xmlrpc.client.Binary(b'content'), 'rpt_name5678', 'stage90')
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
      self.assertEqual(file_utils.ReadFile(event_path, encoding=None), content)
      return True

    d = self.Call('UploadEvent', 'event_log_name', b'123')
    d.addCallback(CheckTrue)
    d.addCallback(lambda _: CheckEvent(b'123'))
    d.addCallback(lambda _: self.Call('UploadEvent', 'event_log_name', b'456'))
    d.addCallback(CheckTrue)
    d.addCallback(lambda _: CheckEvent(b'123456'))
    return d


if os.environ.get('LOG_LEVEL'):
  logging.basicConfig(
      level=logging.DEBUG,
      format='%(levelname)5s %(message)s')
else:
  logging.disable(logging.CRITICAL)
