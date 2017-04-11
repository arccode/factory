#!/usr/bin/python -u
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import threading
import unittest
import xmlrpclib

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service import rpc_server
from cros.factory.utils import net_utils


_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class RPCServerTest(unittest.TestCase):
  def setUp(self):
    self.ip = '127.0.0.1'
    self.port = net_utils.FindUnusedTCPPort()
    self.service = rpc_server.HWIDService(
        address=(self.ip, self.port), standalone=True)
    self.service_thread = threading.Thread(target=self.service.RunForever)
    self.service_thread.setDaemon(True)
    self.service_thread.start()
    self.proxy = xmlrpclib.ServerProxy('http://%s:%d/' % (self.ip, self.port))

    with open(os.path.join(_TEST_DATA_PATH, 'TEST_BOARD'), 'r') as f:
      self.board = f.read()
    with open(os.path.join(_TEST_DATA_PATH, 'NEW_TEST_BOARD'), 'r') as f:
      self.new_board = f.read()

  def tearDown(self):
    self.service.ShutDown()

  def testValidateConfigPass(self):
    result = self.proxy.ValidateConfig(self.board)
    self.assertEquals(result['success'], True)
    self.assertEquals(result['ret'], None)

  def testValidateConfigEmptyInput(self):
    result = self.proxy.ValidateConfig('')
    self.assertEquals(result['success'], False)
    self.assertNotEquals(result['ret'], None)

  def testValidateConfigAndUpdateChecksumPass(self):
    result = self.proxy.ValidateConfigAndUpdateChecksum(self.new_board,
                                                        self.board)
    with open(os.path.join(_TEST_DATA_PATH, 'NEW_TEST_BOARD.golden'), 'r') as f:
      golden = f.read()

    self.assertEquals(result['success'], True)
    self.assertEquals(result['ret'].encode('UTF-8'), golden)

  def testValidateConfigAndUpdateChecksumFail(self):
    result = self.proxy.ValidateConfigAndUpdateChecksum(self.board,
                                                        self.new_board)
    self.assertEquals(result['success'], False)


if __name__ == '__main__':
  unittest.main()
