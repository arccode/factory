# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The package initialization and abstract base class for shop floor systems.

Every implementations should inherit ShopFloorBase and override the member
functions to interact with their real shop floor system.
"""

import csv
import glob
import logging
import os
import time
import xmlrpclib

# In current implementation, we use xmlrpclib.Binary to prepare blobs.
from xmlrpclib import Binary

import factory_common
from cros.factory.shopfloor import factory_update_server
from cros.factory.test import utils


EVENTS_DIR = 'events'
REPORTS_DIR = 'reports'
UPDATE_DIR = 'update'
HWID_UPDATER_PATTERN = 'hwid_*'
REGISTRATION_CODE_LOG_CSV = 'registration_code_log.csv'


class NewlineTerminatedCSVDialect(csv.excel):
  lineterminator = '\n'


class ShopFloorException(Exception):
  pass


class ShopFloorBase(object):
  """Base class for shopfloor servers.

  Properties:
    config: The configuration data provided by the '-c' argument to
      shopfloor_server.
    data_dir: The top-level directory for shopfloor data.
  """

  NAME = 'ShopFloorBase'
  VERSION = 4

  def __init__(self):
    self.data_dir = None  # Set by shopfloor_server
    self.update_dir = None
    self.update_server = None

  def _InitBase(self):
    """Initializes the base class."""
    if not os.path.exists(self.data_dir):
      logging.warn('Data directory %s does not exist; creating it',
                   self.data_dir)
      os.makedirs(self.data_dir)

    # Dynamic test directory for holding updates is called "update" in data_dir.
    self.update_dir = os.path.join(self.data_dir, UPDATE_DIR)
    utils.TryMakeDirs(self.update_dir)
    self.update_dir = os.path.realpath(self.update_dir)
    self.update_server = factory_update_server.FactoryUpdateServer(
        self.update_dir)

  def _StartBase(self):
    """Starts the base class."""
    if self.update_server:
      logging.debug('Starting factory update server...')
      self.update_server.Start()

  def _StopBase(self):
    """Stops the base class."""
    if self.update_server:
      self.update_server.Stop()

  def GetLogsDir(self, subdir=None):
    """Returns the active logs directory.

    This is the data directory base plus a path element "logs.YYMMDD",
    where YYMMDD is today's date in the local time zone.  This creates
    the directory if it does not exist.

    Args:
      subdir: If not None, this is appended to the path.
    """
    ret = os.path.join(self.data_dir,
                       time.strftime('logs.%Y%m%d'))
    if subdir:
      ret = os.path.join(ret, subdir)
    utils.TryMakeDirs(ret)
    return ret

  def GetEventsDir(self):
    """Returns the active events directory."""
    return self.GetLogsDir(EVENTS_DIR)

  def GetReportsDir(self):
    """Returns the active reports directory."""
    return self.GetLogsDir(REPORTS_DIR)

  def Init(self):
    """Initializes the shop floor system.

    Subclasses should implement this rather than __init__.
    """
    pass

  def Ping(self):
    """Always returns true (for client to check if server is working)."""
    return True

  def GetHWID(self, serial):
    """Returns appropriate HWID according to given serial number.

    Args:
      serial: A string of device serial number.

    Returns:
      The associated HWID string.

    Raises:
      ValueError if serial is invalid, or other exceptions defined by individual
      modules. Note this will be converted to xmlrpclib.Fault when being used as
      a XML-RPC server module.
    """
    raise NotImplementedError('GetHWID')

  def _GetHWIDUpdaterPath(self):
    """Returns the path to HWID updater bundle, if available.

    Returns:
      The path to the file (or None).

    Raises:
      ShopFloorException if there are >1 HWID bundles available.
    """
    bundles = (
        glob.glob(os.path.join(
            self.data_dir, HWID_UPDATER_PATTERN)) +
        glob.glob(os.path.join(
            self.data_dir, UPDATE_DIR, HWID_UPDATER_PATTERN)))
    if not bundles:
      return None

    if len(bundles) > 1:
      error = ('Multiple HWID bundles available: %s (please '
               'delete all but one)' % bundles)
      logging.error(error)
      raise ShopFloorException(error)

    return bundles[0]

  def GetHWIDUpdater(self):
    """Returns a HWID updater bundle, if available.

    Returns:
      The binary-encoded contents of a file named 'hwid_*' in the data
      directory.  If there are no such files, returns None.

    Raises:
      ShopFloorException if there are >1 HWID bundles available.
    """
    path = self._GetHWIDUpdaterPath()
    return Binary(open(path).read()) if path else None

  def GetVPD(self, serial):
    """Returns VPD data to set (in dictionary format).

    Args:
      serial: A string of device serial number.

    Returns:
      VPD data in dict {'ro': dict(), 'rw': dict()}

    Raises:
      ValueError if serial is invalid, or other exceptions defined by individual
      modules. Note this will be converted to xmlrpclib.Fault when being used as
      a XML-RPC server module.
    """
    raise NotImplementedError('GetVPD')

  def UploadReport(self, serial, report_blob, report_name=None):
    """Uploads a report file.

    Args:
      serial: A string of device serial number.
      report_blob: Blob of compressed report to be stored (must be prepared by
          shopfloor.Binary)
      report_name: (Optional) Suggested report file name. This is uslally
          assigned by factory test client programs (ex, gooftool); however
          server implementations still may use other names to store the report.

    Returns:
      True on success.

    Raises:
      ValueError if serial is invalid, or other exceptions defined by individual
      modules. Note this will be converted to xmlrpclib.Fault when being used as
      a XML-RPC server module.
    """
    raise NotImplementedError('UploadReport')

  def Finalize(self, serial):
    """Marks target device (by serial) to be ready for shipment.

    Args:
      serial: A string of device serial number.

    Returns:
      True on success.

    Raises:
      ValueError if serial is invalid, or other exceptions defined by individual
      modules. Note this will be converted to xmlrpclib.Fault when being used as
      a XML-RPC server module.
    """
    raise NotImplementedError('Finalize')

  def GetRegistrationCodeMap(self, serial):
    """Returns the registration code map for the given serial number.

    Returns:
      {'user': registration_code, 'group': group_code}

    Raises:
      ValueError if serial is invalid, or other exceptions defined by individual
      modules. Note this will be converted to xmlrpclib.Fault when being used as
      a XML-RPC server module.
    """
    raise NotImplementedError('GetRegistrationCode')

  def GetAuxData(self, table_name, id):  # pylint: disable=W0622
    """Returns a row from an auxiliary table.

    Args:
      table_name: The table containing the desired row.
      id: The ID of the row to return.

    Returns:
      A map of properties from the given table.

    Raises:
      ValueError if the ID cannot be found in the table.  Note this will be
      converted to xmlrpclib.Fault when being used as an XML-RPC server
      module.
    """
    raise NotImplementedError('GetAuxData')

  def LogRegistrationCodeMap(self, hwid, registration_code_map):
    """Logs that a particular registration code has been used."""
    with open(os.path.join(
        self.GetLogsDir(), "registration_code_log.csv"), "ab") as f:
      platform = hwid.split()[0]

      csv.writer(f, dialect=NewlineTerminatedCSVDialect).writerow([
        platform, registration_code_map['user'], registration_code_map['group'],
        time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())])
      os.fdatasync(f.fileno())

  def GetTestMd5sum(self):
    """Gets the latest md5sum of dynamic test tarball.

    Returns:
      A string of md5sum.  None if no dynamic test tarball is installed.
    """
    if not self.update_dir:
      return None

    md5file = os.path.join(self.update_dir,
                           factory_update_server.FACTORY_DIR,
                           factory_update_server.LATEST_MD5SUM)
    if not os.path.isfile(md5file):
      return None
    with open(md5file, 'r') as f:
      return f.readline().strip()

  def GetUpdatePort(self):
    """Returns the port to use for rsync updates.

    Returns:
      The port, or None if there is no update server available.
    """
    return self.update_server.rsyncd_port if self.update_server else None

  def UploadEvent(self, log_name, chunk):
    """Uploads a chunk of events.

    Args:
      log_name: A string of the event log filename. Event logging module creates
          event files with an unique identifier (uuid) as part of the filename.
      chunk: A string containing one or more events. Events are in YAML format
          and separated by a "---" as specified by YAML. A chunk contains one or
          more events with separator.

    Returns:
      True on success.

    Raises:
      IOError if unable to save the chunk of events.
    """
    if isinstance(chunk, Binary):
      chunk = chunk.data

    log_file = os.path.join(self.GetEventsDir(), log_name)
    with open(log_file, 'a') as f:
      f.write(chunk)
    return True

  def GetTime(self):
    """Returns the current time in seconds since the epoch."""
    return time.time()


# Alias ShopFloorBase to ShopFloor, so that this module can be run directly.
ShopFloor = ShopFloorBase
