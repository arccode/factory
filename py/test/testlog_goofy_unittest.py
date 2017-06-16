#!/usr/bin/python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittests for goofy-specific function for testlog."""

import logging
import os
import re
import shutil
import tempfile
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.test import testlog_goofy

UUID_RE = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-'
                     '[a-f0-9]{4}-[a-f0-9]{12}$')


class TestlogGoofyTest(unittest.TestCase):
  """Unittest for testlog_goofy.py."""

  def setUp(self):
    for _ in [testlog_goofy.INSTALLATION_ID_PATH,
              testlog_goofy.DEVICE_ID_PATH,
              testlog_goofy.INIT_COUNT_PATH]:
      try:
        os.unlink(_)
      except OSError:
        pass
    testlog_goofy._installation_id = None  # pylint: disable=protected-access
    testlog_goofy._device_id = None  # pylint: disable=protected-access

    self.tmp = tempfile.mkdtemp()

  def tearDown(self):
    shutil.rmtree(self.tmp)

  def testGetBootID(self):
    assert UUID_RE.match(testlog_goofy.GetBootID())

  @mock.patch('testlog_goofy.file_utils.ReadFile', return_value='device_id\n')
  @mock.patch('os.path.exists', return_value=True)
  def testGetDeviceID(self, mock_exists, mock_read_file):
    self.assertEqual('device_id', testlog_goofy.GetDeviceID())
    # Make one more call to ensure the result is cached.
    self.assertEqual('device_id', testlog_goofy.GetDeviceID())
    mock_exists.assert_called_once_with(testlog_goofy.DEVICE_ID_PATH)
    mock_read_file.assert_called_once_with(testlog_goofy.DEVICE_ID_PATH)

  def testGetInstallationID(self):
    installation_id = testlog_goofy.GetInstallationID()
    assert UUID_RE.match(installation_id), installation_id

    # Remove installation_id and make sure we get the same thing
    # back again, re-reading it from disk
    testlog_goofy._installation_id = None  # pylint: disable=protected-access
    self.assertEqual(installation_id, testlog_goofy.GetInstallationID())

    # Remove the installation_id file; now we should get something
    # *different* back.
    testlog_goofy._installation_id = None  # pylint: disable=protected-access
    os.unlink(testlog_goofy.INSTALLATION_ID_PATH)
    self.assertNotEqual(installation_id, testlog_goofy.GetInstallationID())

  def testInitCount(self):
    for i in xrange(-1, 5):
      self.assertEqual(i, testlog_goofy.GetInitCount())
      testlog_goofy.IncrementInitCount()
      self.assertEqual(str(i + 1),
                       open(testlog_goofy.INIT_COUNT_PATH).read())


if __name__ == '__main__':
  logging.basicConfig(
      format=('[%(levelname)s] '
              ' %(threadName)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=logging.INFO,
      datefmt='%Y-%m-%d %H:%M:%S')
  unittest.main()
