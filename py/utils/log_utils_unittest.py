#!/usr/bin/env python2
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import log_utils


class NoisyLoggerTest(unittest.TestCase):

  class Counter(object):

    def __init__(self):
      self.counter = 0

    def Call(self, message):
      del message  # Unused.
      self.counter += 1

  def testUnlimited(self):
    c1 = self.Counter()
    c2 = self.Counter()
    a = log_utils.NoisyLogger(c1.Call, all_suppress_logger=c2.Call)
    a.Log('test')
    self.assertEquals(c1.counter, 1)
    self.assertEquals(c2.counter, 0)
    a.Log('test')
    self.assertEquals(c1.counter, 1)
    self.assertEquals(c2.counter, 1)
    a.Log('test')
    self.assertEquals(c1.counter, 1)
    self.assertEquals(c2.counter, 2)
    a.Log('different')
    self.assertEquals(c1.counter, 2)
    self.assertEquals(c2.counter, 2)
    a.Log('different')
    self.assertEquals(c1.counter, 2)
    self.assertEquals(c2.counter, 3)

  def testSupressLimit(self):
    c = self.Counter()
    a = log_utils.NoisyLogger(c.Call, suppress_limit=3)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    a.Log('test')
    self.assertEquals(c.counter, 2)
    a.Log('test')
    self.assertEquals(c.counter, 2)
    a.Log('test')
    self.assertEquals(c.counter, 2)
    a.Log('test')
    self.assertEquals(c.counter, 2)
    a.Log('test')
    self.assertEquals(c.counter, 3)
    a.Log('different')
    self.assertEquals(c.counter, 4)
    a.Log('different')
    self.assertEquals(c.counter, 4)

  def testSupressTimeout(self):
    c = self.Counter()
    a = log_utils.NoisyLogger(c.Call, suppress_limit=100, suppress_timeout=0.1)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    time.sleep(0.11)
    a.Log('test')
    self.assertEquals(c.counter, 2)
    a.Log('test')
    self.assertEquals(c.counter, 2)
    a.Log('test')
    self.assertEquals(c.counter, 2)


if __name__ == '__main__':
  unittest.main()
