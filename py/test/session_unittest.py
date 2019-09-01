#!/usr/bin/env python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittests for test session and invocation."""

import logging
import os
import re
import shutil
import tempfile
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.test import session

UUID_RE = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-'
                     '[a-f0-9]{4}-[a-f0-9]{12}$')


class SessionTest(unittest.TestCase):
  """Unittest for session.py."""

  def setUp(self):
    for path in [
        session.INSTALLATION_ID_PATH,
        session.DEVICE_ID_PATH,
        session.INIT_COUNT_PATH]:
      try:
        os.unlink(path)
      except OSError:
        pass
    session._installation_id = None  # pylint: disable=protected-access
    session._device_id = None  # pylint: disable=protected-access

    self.tmp = tempfile.mkdtemp()

  def tearDown(self):
    shutil.rmtree(self.tmp)

  def testGetBootID(self):
    self.assertRegexpMatches(session.GetBootID(), UUID_RE)

  @mock.patch('session.file_utils.ReadFile', return_value='device_id\n')
  @mock.patch('os.path.exists', return_value=True)
  def testGetDeviceID(self, mock_exists, mock_read_file):
    self.assertEqual('device_id', session.GetDeviceID())
    # Make one more call to ensure the result is cached.
    self.assertEqual('device_id', session.GetDeviceID())
    mock_exists.assert_called_once_with(session.DEVICE_ID_PATH)
    mock_read_file.assert_called_once_with(session.DEVICE_ID_PATH)

  def testGetInstallationID(self):
    installation_id = session.GetInstallationID()
    self.assertRegexpMatches(installation_id, UUID_RE)

    # Remove installation_id and make sure we get the same thing
    # back again, re-reading it from disk
    session._installation_id = None  # pylint: disable=protected-access
    self.assertEqual(installation_id, session.GetInstallationID())

    # Remove the installation_id file; now we should get something
    # *different* back.
    session._installation_id = None  # pylint: disable=protected-access
    os.unlink(session.INSTALLATION_ID_PATH)
    session.GetInstallationID.InvalidateCache()
    self.assertNotEqual(installation_id, session.GetInstallationID())

  def testInitCount(self):
    for i in xrange(-1, 5):
      self.assertEqual(i, session.GetInitCount())
      session.IncrementInitCount()
      self.assertEqual(str(i + 1),
                       open(session.INIT_COUNT_PATH).read())


if __name__ == '__main__':
  logging.basicConfig(
      format=('[%(levelname)s] '
              ' %(threadName)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=logging.INFO,
      datefmt='%Y-%m-%d %H:%M:%S')
  unittest.main()
