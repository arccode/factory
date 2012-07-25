#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import subprocess
import unittest
from logging import handlers

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn, PIPE


class SpawnTest(unittest.TestCase):
  def setUp(self):
    log_entries = self.log_entries = []

    class Target(object):
      def handle(self, record):
        log_entries.append((record.levelname, record.msg % record.args))

    self.handler = handlers.MemoryHandler(capacity=0, target=Target())
    logging.getLogger().addHandler(self.handler)

  def tearDown(self):
    logging.getLogger().removeHandler(self.handler)

  def testNoShell(self):
    process = Spawn(['echo', 'f<o>o'],
                    stdout=PIPE, stderr=PIPE,
                    log=True)
    stdout, stderr = process.communicate()
    self.assertEquals('f<o>o\n', stdout)
    self.assertEquals('', stderr)
    self.assertEquals(0, process.returncode)
    self.assertEquals([('INFO',
                        '''Running command: "echo \'f<o>o\'"''')],
                      self.log_entries)

  def testShell(self):
    process = Spawn('echo foo', shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    log=True)
    stdout, stderr = process.communicate()
    self.assertEquals('foo\n', stdout)
    self.assertEquals('', stderr)
    self.assertEquals(0, process.returncode)
    self.assertEquals([('INFO', 'Running command: "echo foo"')],
                      self.log_entries)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
