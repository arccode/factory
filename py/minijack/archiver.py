# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

import factory_common  # pylint: disable=W0611
from cros.factory.minijack import db
from cros.factory.minijack.models import Event, Attr, Device


FINALIZED_TEST = 'GoogleRequiredTests.Finalize'
STATUS_ARCHIVED = 'ARCHIVED'


class Archiver(object):
  """Minijack Archiver.

  Given a date, Minijack Arhiver helps moving records in the Event and Attr
  tables before the date, from the main database, to the backup databases.
  And also marks the devices archived in the Device table.

  Properties:
    _db_path: The path of the Minijack DB file.
    _main_db: The database object of the main Minijack DB.
    _backup_dbs: The database object dict of the backup DBs, with dates as keys.
  """
  def __init__(self, minijack_db_path):
    self._db_path = minijack_db_path
    self._main_db = db.Database()
    self._main_db.Init(self._db_path)
    self._backup_dbs = {}

  def __del__(self):
    for database in self._backup_dbs.itervalues():
      database.Close()
    self._main_db.Close()

  def GetOrInitDatabase(self, date):
    """Gets or inits the database by given a date as its filename suffix.

    Args:
      date: A string of the date suffix of the database file.

    Return:
      A database instance.
    """
    if date not in self._backup_dbs:
      database = db.Database()
      database.Init('.'.join([self._db_path, date]))
      self._backup_dbs[date] = database
    return self._backup_dbs[date]

  def ArchiveBefore(self, date):
    """Archives Event/Attr records of finalized devices before the given date.

    Args:
      date: A string of the date.
    """
    condition = Device(latest_test=FINALIZED_TEST)
    for row in self._main_db.IterateAll(condition):
      if (row and row.latest_test_time < date and
          row.minijack_status != STATUS_ARCHIVED):
        device_id = row.device_id
        logging.info('Archiving a device record (%s)', device_id)
        backup_db = self.GetOrInitDatabase(GetDate(row.latest_test_time))
        for condition in (Event(device_id=device_id),
                          Attr(device_id=device_id)):
          backup_db.InsertMany(self._main_db.GetAll(condition))
          self._main_db.DeleteAll(condition)
        update = Device(device_id=device_id, minijack_status=STATUS_ARCHIVED)
        self._main_db.Update(update)


def GetDate(time_str):
  """Gets the date from a time string.

  For example: "2013-04-27T10:57:59.778Z" -> "20130427".

  Args:
    time_str: A string of event TIME field.

  Return:
    A string of the date.
  """
  return time_str.split('T')[0].replace('-', '')
