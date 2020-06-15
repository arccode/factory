#!/usr/bin/env python3
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import time
import unittest

from cros.factory.utils import log_utils


class NoisyLoggerTest(unittest.TestCase):

  class Counter:

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
    self.assertEqual(c1.counter, 1)
    self.assertEqual(c2.counter, 0)
    a.Log('test')
    self.assertEqual(c1.counter, 1)
    self.assertEqual(c2.counter, 1)
    a.Log('test')
    self.assertEqual(c1.counter, 1)
    self.assertEqual(c2.counter, 2)
    a.Log('different')
    self.assertEqual(c1.counter, 2)
    self.assertEqual(c2.counter, 2)
    a.Log('different')
    self.assertEqual(c1.counter, 2)
    self.assertEqual(c2.counter, 3)

  def testSupressLimit(self):
    c = self.Counter()
    a = log_utils.NoisyLogger(c.Call, suppress_limit=3)
    a.Log('test')
    self.assertEqual(c.counter, 1)
    a.Log('test')
    self.assertEqual(c.counter, 1)
    a.Log('test')
    self.assertEqual(c.counter, 1)
    a.Log('test')
    self.assertEqual(c.counter, 1)
    a.Log('test')
    self.assertEqual(c.counter, 2)
    a.Log('test')
    self.assertEqual(c.counter, 2)
    a.Log('test')
    self.assertEqual(c.counter, 2)
    a.Log('test')
    self.assertEqual(c.counter, 2)
    a.Log('test')
    self.assertEqual(c.counter, 3)
    a.Log('different')
    self.assertEqual(c.counter, 4)
    a.Log('different')
    self.assertEqual(c.counter, 4)

  def testSupressTimeout(self):
    c = self.Counter()
    a = log_utils.NoisyLogger(c.Call, suppress_limit=100, suppress_timeout=0.1)
    a.Log('test')
    self.assertEqual(c.counter, 1)
    a.Log('test')
    self.assertEqual(c.counter, 1)
    a.Log('test')
    self.assertEqual(c.counter, 1)
    a.Log('test')
    self.assertEqual(c.counter, 1)
    time.sleep(0.11)
    a.Log('test')
    self.assertEqual(c.counter, 2)
    a.Log('test')
    self.assertEqual(c.counter, 2)
    a.Log('test')
    self.assertEqual(c.counter, 2)


if __name__ == '__main__':
  unittest.main()
