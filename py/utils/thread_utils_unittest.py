#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import Queue
import threading
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import thread_utils


class ThreadUtilsUnittest(unittest.TestCase):
  def setUp(self):
    self.errors = Queue.Queue()

  def _TestOneThread(self, index):
    try:
      with thread_utils.SetLocalEnv(a=index):
        self.assertEqual(thread_utils.LocalEnv(), {'a': index})
        with thread_utils.SetLocalEnv(b=index + 1):
          self.assertEqual(thread_utils.LocalEnv(),
                           {'a': index, 'b': index + 1})
        with thread_utils.SetLocalEnv(a=index + 2, b=index + 1):
          self.assertEqual(thread_utils.LocalEnv(),
                           {'a': index + 2, 'b': index + 1})
        self.assertEqual(thread_utils.LocalEnv(), {'a': index})
      self.assertEqual(thread_utils.LocalEnv(), {})
    except Exception as e:
      self.errors.put(e)

  def testSingleThread(self):
    self._TestOneThread(0)

  def testMultiThread(self):
    threads = []
    for index in xrange(10):
      threads.append(
          threading.Thread(target=self._TestOneThread, args=(index, )))
      threads[-1].start()

    for thread in threads:
      thread.join()

    errors = []
    while not self.errors.empty():
      errors.append(self.errors.get())

    self.assertFalse(errors)


if __name__ == '__main__':
  unittest.main()
