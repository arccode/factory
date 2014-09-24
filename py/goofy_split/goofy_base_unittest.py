#!/usr/bin/python -u
#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The unittest for the main factory flow that runs the factory test."""

import logging
import threading
import time
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory.test import factory
from cros.factory.goofy.goofy_base import GoofyBase

def call_counter():
  """Helper iterator that returns the number of previous calls."""
  count = 0
  while True:
    yield count
    count += 1


class GoofyBaseTest(unittest.TestCase):
  """Base class for GoofyBase test cases."""

  def setUp(self):
    self.goofy = GoofyBase()

  def tearDown(self):
    self.goofy.destroy()

    # Make sure we're not leaving any extra threads hanging around
    # after a second.
    for _ in range(10):
      extra_threads = [t for t in threading.enumerate()
               if t != threading.current_thread()]
      if not extra_threads:
        break
      logging.info('Waiting for %d threads to die', len(extra_threads))

      # Wait another 100 ms
      time.sleep(.1)

    self.assertEqual([], extra_threads)


class EventLoopStopTest(GoofyBaseTest):
  """Check that event loops stop when passed None."""
  def runTest(self):
    counter = call_counter().next
    self.goofy.run_enqueue(counter)
    self.goofy.run_enqueue(counter)
    self.goofy.run_enqueue(None)
    self.goofy.run_enqueue(counter)
    self.goofy.run_enqueue(counter)
    self.goofy.run()

    # The counter should have been incremented exactly twice,
    # because the None should have shut down the run loop
    self.assertEqual(counter(), 2)

class DrainThreadsTest(GoofyBaseTest):
  """Check that we can drain threads correctly """
  def runTest(self):
    counter = call_counter().next
    def thread_task():
      time.sleep(.5)
      counter()
    thread_count = 3
    threads = []
    for i in xrange(thread_count):
      t = threading.Thread(target=thread_task, name='DrainThreadsTest_%d' % i)
      threads.append(t)
      t.start()
    self.goofy.drain_nondaemon_threads()
    # All threads should now have exited, and the counter should have been
    # incremented exactly thread_count times
    for t in threads:
      self.assertFalse(t.is_alive())
    self.assertEqual(counter(), thread_count)


if __name__ == "__main__":
  factory.init_logging('goofy_base_unittest')
  unittest.main()
