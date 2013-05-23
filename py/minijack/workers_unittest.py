#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.workers import EventLoadingWorker


MOCK_PREAMBLE = lambda x: 'EVENT: preamble\nSEQ: %d\n---\n' % x
MOCK_EVENT = lambda x: 'EVENT: start_test\nSEQ: %d\n---\n' % x


class EventLoadingWorkerTest(unittest.TestCase):
  def testGetLastPreambleFromFile(self):
    log_file = tempfile.NamedTemporaryFile()
    log_file.write(''.join([MOCK_PREAMBLE(1), MOCK_EVENT(2),
                            MOCK_PREAMBLE(3), MOCK_EVENT(4)]))
    log_file.flush()
    preamble = EventLoadingWorker.GetLastPreambleFromFile(log_file.name)
    self.assertDictEqual({
      'EVENT': 'preamble',
      'SEQ': 3,
    }, preamble)

  def testGetYesterdayLogDir(self):
    yesterday = EventLoadingWorker.GetYesterdayLogDir
    self.assertEqual('logs.20130416', yesterday('logs.20130417'))
    self.assertEqual('logs.20130228', yesterday('logs.20130301'))
    self.assertEqual('logs.20131231', yesterday('logs.20140101'))
    self.assertIs(None, yesterday('logs.no_date'))
    self.assertIs(None, yesterday('invalid'))


if __name__ == "__main__":
  logging.disable(logging.WARN)
  unittest.main()
