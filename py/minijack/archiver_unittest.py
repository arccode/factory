#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.archiver import Archiver, STATUS_ARCHIVED
from cros.factory.minijack.db import Database
from cros.factory.minijack.models import Event, Attr, Device


class ArchiverTest(unittest.TestCase):
  def setUp(self):
    self._temp_dir = tempfile.mkdtemp()
    self._db_path = os.path.join(self._temp_dir, 'minijack_db')

    # Generate the log on the main database:
    #   finalized: 1, 3, 5, 7, 9
    #   archived: 3
    self._main_db = Database()
    self._main_db.Init(self._db_path)
    for i in range(1, 11):
      self._main_db.Insert(Device(
          device_id=('did:%d' % i),
          latest_test=('GoogleRequiredTests.Finalize' if i % 2 else 'Other'),
          latest_test_time=('2013-05-%02dT12:34:56.789Z' % i),
          minijack_status=(STATUS_ARCHIVED if i == 3 else '')))

      # The archived device, i.e. 3, has no Event/Attr record.
      if i != 3:
        self._main_db.Insert(Event(
            event_id=('eid:%d' % i),
            device_id=('did:%d' % i),
            time=('2013-05-%02dT12:34:56.789Z' % i)))
        self._main_db.Insert(Attr(
            device_id=('did:%d' % i),
            time=('2013-05-%02dT12:34:56.789Z' % i)))

  def testArchiveBefore(self):
    archiver = Archiver(self._db_path)
    archiver.ArchiveBefore('2013-05-07')

    for i in range(1, 11):
      backup_db_path = self._db_path + ('.201305%02d' % i)

      # Before the date: 1, 2, 3, 4, 5, 6
      # Before the data and finalized: 1, 3, 5.
      # Before the data and finalized and not archived: 1, 5.
      if i in (1, 5):
        # Check the backup database file exists.
        self.assertTrue(os.path.isfile(backup_db_path))
        backup_db = Database()
        backup_db.Init(backup_db_path)

        # Check the Table/Attr rows moved to the backup db.
        condition = Event(device_id=('did:%d' % i))
        self.assertFalse(self._main_db.CheckExists(condition))
        self.assertTrue(backup_db.CheckExists(condition))

        condition = Attr(device_id=('did:%d' % i))
        self.assertFalse(self._main_db.CheckExists(condition))
        self.assertTrue(backup_db.CheckExists(condition))

        # Check the minijack_status field in Device updated.
        condition = Device(device_id=('did:%d' % i))
        device = self._main_db.GetOne(condition)
        self.assertEquals(STATUS_ARCHIVED, device.minijack_status)

        backup_db.Close()
      else:
        self.assertFalse(os.path.isfile(backup_db_path))

        # The archived device, i.e. 3, has no Event/Attr record.
        if (i != 3):
          # Check the Table/Attr rows are still there.
          condition = Event(device_id=('did:%d' % i))
          self.assertTrue(self._main_db.CheckExists(condition))
          condition = Attr(device_id=('did:%d' % i))
          self.assertTrue(self._main_db.CheckExists(condition))

  def tearDown(self):
    self._main_db.Close()
    shutil.rmtree(self._temp_dir, ignore_errors=True)


if __name__ == "__main__":
  unittest.main()
