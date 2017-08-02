#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This file starts a server for integration of factory shop floor system.

To use it, invoke as a standalone program and specify the URL of backend shop
floor service.

Example:
  ./factory_server http://localhost:8090/
"""


import csv
import glob
import logging
import optparse
import os
import shutil
import signal
from SimpleXMLRPCServer import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
import socket
import SocketServer
import threading
import time
import xmlrpclib

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor import factory_update_server, factory_log_server
from cros.factory.test.env import paths
from cros.factory.test.rules.registration_codes import CheckRegistrationCode
from cros.factory.utils import config_utils
from cros.factory.utils import debug_utils
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils.process_utils import Spawn


Binary = xmlrpclib.Binary

DEFAULT_SERVER_PORT = 8082
# By default, this server is supposed to serve on same host running omaha
# server, accepting connections from client devices; so the address to bind is
# "all interfaces (0.0.0.0)". For partners running server on clients, they may
# want to change address to "localhost".
_DEFAULT_SERVER_ADDRESS = '0.0.0.0'

# Environment variables that can be used to set shop floor server address and
# port.
SHOPFLOOR_ADDR_ENV_VAR = 'CROS_SHOPFLOOR_ADDR'
SHOPFLOOR_PORT_ENV_VAR = 'CROS_SHOPFLOOR_PORT'

# A service running outside docker on default port.
DEFAULT_SHOPFLOOR_SERVICE_URL = 'http://localhost:8090'

EVENTS_DIR = 'events'
INCREMENTAL_EVENTS_DIR = 'events_incremental'
REPORTS_DIR = 'reports'
AUX_LOGS_DIR = 'aux_logs'
UPDATE_DIR = 'update'
PARAMETERS_DIR = 'parameters'
FACTORY_LOG_DIR = 'system_logs'
REGISTRATION_CODE_LOG_CSV = 'registration_code_log.csv'
LOGS_DIR_FORMAT = 'logs.%Y%m%d'
HOURLY_DIR_FORMAT = 'logs.%Y%m%d-%H'

IN_PROGRESS_SUFFIX = '.INPROGRESS'


class NewlineTerminatedCSVDialect(csv.excel):
  lineterminator = '\n'


class ServerException(Exception):
  pass


class FactoryServer(object):
  """A Factory Server for ChromeOS Manufacturing (deprecated by Umpire).

  :ivar data_dir: The top-level directory for shopfloor data.
  :ivar address: The IP address for the shopfloor server to bind on.
  :ivar port: The port for the shopfloor server to bind on.
  :ivar update_server: An FactoryUpdateServer for factory environment update.
  :ivar log_server: An FactoryLogServer for factory log files to be uploaded
   from DUT.
  :ivar _auto_archive_logs: An optional path to use for auto-archiving
   logs (see the --auto-archive-logs command-line argument).  This
   must contain the string 'DATE'.
  :ivar _auto_archive_logs_days: Number of days of logs to save.
  :ivar _auto_archive_logs_dir_exists: True if the parent of _auto_archive_logs
   existed the last time we checked, False if not, or None if we've
   never checked.
  """

  NAME = 'ChromeOSFactoryServer'
  VERSION = 5

  def __init__(self, data_dir, address, port, auto_archive_logs,
               auto_archive_logs_days, shopfloor_service_url=None,
               miniomaha_payload_url=None, updater=None):
    """Initializes the server.

    Args:
      data_dir: A path to folder for accessing data.
      address: The IP address to bind server.
      port: The port number to listen.
      auto_archive_logs: See _auto_archive_logs property.
      auto_archive_logs_days: See _auto_archive_logs_days property.
      shopfloor_service_url: An URL to shopfloor service backend.
      miniomaha_payload_url: An URL to Mini-Omaha cros_payload JSON file.
      updater: A reference to factory updater. Factory updater provides
               interfaces compatible to FactoryUpdateServer. Including
               Start, Stop, hwid_path, GetTestMD5, NeedsUpdate and rsync_port.
    """
    self.data_dir = data_dir
    self.address = address
    self.port = port

    self.update_dir = None
    self.update_server = None
    self.factory_log_dir = None
    self.log_server = None
    self.events_rotate_hourly = False
    self.reports_rotate_hourly = False
    self._auto_archive_logs = None
    self._auto_archive_logs_days = None
    self._auto_archive_logs_dir_exists = None

    if auto_archive_logs_days > 0 and auto_archive_logs:
      assert 'DATE' in auto_archive_logs, (
          '--auto-archive-logs flag must contain the string DATE')
      self._auto_archive_logs = auto_archive_logs
      self._auto_archive_logs_days = auto_archive_logs_days

    if shopfloor_service_url is None:
      shopfloor_service_url = config_utils.LoadConfig('factory_server').get(
          'shopfloor_service_url', DEFAULT_SHOPFLOOR_SERVICE_URL)
    shopfloor_service_url = shopfloor_service_url.rstrip('/')
    self.service = xmlrpclib.ServerProxy(shopfloor_service_url, allow_none=True)
    logging.info('Using shopfloor service from %s', shopfloor_service_url)

    self.miniomaha_payload_url = (
        miniomaha_payload_url or
        config_utils.LoadConfig('factory_server').get(
            'miniomaha_payload_url', ''))
    logging.info('Using %r as Mini-Omaha cros_payload JSON URL.',
                 self.miniomaha_payload_url)

    if not os.path.exists(self.data_dir):
      logging.warn('Data directory %s does not exist; creating it',
                   self.data_dir)
      os.makedirs(self.data_dir)

    # Create parameters directory
    self.parameters_dir = os.path.realpath(
        os.path.join(self.data_dir, PARAMETERS_DIR))
    file_utils.TryMakeDirs(self.parameters_dir)

    if updater is None:
      # Dynamic test directory for holding updates is called "update" in
      # data_dir.
      self.update_dir = os.path.join(self.data_dir, UPDATE_DIR)
      file_utils.TryMakeDirs(self.update_dir)
      self.update_dir = os.path.realpath(self.update_dir)
      self.update_server = factory_update_server.FactoryUpdateServer(
          self.update_dir,
          rsyncd_addr=self.address,
          rsyncd_port=(self.port + 1),
          on_idle=(self._AutoSaveLogs if self._auto_archive_logs else None))
      # Create factory log directory
      self.factory_log_dir = os.path.join(self.data_dir, FACTORY_LOG_DIR)
      file_utils.TryMakeDirs(self.factory_log_dir)
      self.factory_log_dir = os.path.realpath(self.factory_log_dir)
      self.log_server = factory_log_server.FactoryLogServer(
          self.factory_log_dir,
          rsyncd_addr=self.address,
          rsyncd_port=(self.port + 2))
    else:
      # Use external update server and log server
      self.update_server = updater
      self.log_server = updater
      # When using external updater, events and reports rotate hourly
      self.reports_rotate_hourly = True
      self.events_rotate_hourly = True

  def _Start(self):
    """Starts the base class."""
    if self.update_server:
      logging.debug('Starting factory update server...')
      self.update_server.Start()
    logging.debug('Starting factory log server...')
    self.log_server.Start()

  def _Stop(self):
    """Stops the base class."""
    if self.update_server:
      self.update_server.Stop()
    self.log_server.Stop()

  def _AutoSaveLogs(self):
    """Implements functionality to automatically save logs to USB.

    (See the description of the --auto-archive-logs command-line argument
    for details.)
    """
    auto_archive_dir = os.path.dirname(self._auto_archive_logs)
    new_auto_archive_logs_dir_exists = os.path.isdir(auto_archive_dir)
    if new_auto_archive_logs_dir_exists != self._auto_archive_logs_dir_exists:
      # If the auto-archive directory is newly present (or not present),
      # log a message.
      if new_auto_archive_logs_dir_exists:
        logging.info('Auto-archive directory %s found; will auto-archive '
                     "past %d days' logs there if not present",
                     auto_archive_dir, self._auto_archive_logs_days)
      else:
        logging.info('Auto-archive directory %s not found; create it (or mount '
                     "media there) to auto-archive past %d days' logs",
                     auto_archive_dir, self._auto_archive_logs_days)
      self._auto_archive_logs_dir_exists = new_auto_archive_logs_dir_exists

    if new_auto_archive_logs_dir_exists:
      for days_ago in xrange(1, self._auto_archive_logs_days + 1):
        past_day = time.localtime(time.time() - days_ago * 86400)
        past_day_logs_dir_name = time.strftime(LOGS_DIR_FORMAT, past_day)
        archive_name = os.path.join(
            self._auto_archive_logs.replace(
                'DATE', time.strftime('%Y%m%d', past_day)))
        if os.path.exists(archive_name):
          # We've already done this.
          continue

        past_day_logs_dir = os.path.join(self.data_dir, REPORTS_DIR,
                                         past_day_logs_dir_name)
        if not os.path.exists(past_day_logs_dir):
          # There aren't any logs from past_day.
          continue

        in_progress_name = archive_name + IN_PROGRESS_SUFFIX
        logging.info('Archiving %s to %s', past_day_logs_dir, archive_name)

        Spawn(['tar', '-I', file_utils.GetCompressor('bz2'),
               '-cf', in_progress_name,
               '-C', os.path.join(self.data_dir, REPORTS_DIR),
               past_day_logs_dir_name],
              check_call=True, log=True, log_stderr_on_error=True)
        shutil.move(in_progress_name, archive_name)
        logging.info('Finishing archiving %s to %s',
                     past_day_logs_dir, archive_name)

  def _Timestamp(self):
    return time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())

  def _UnwrapBlob(self, blob):
    """Unwraps a blob object."""
    return blob.data if isinstance(blob, xmlrpclib.Binary) else blob

  def _SaveReport(self, report_name, report_blob):
    """Saves a report to disk and checks its integrity.

    Args:
      report_path: Name of the report.
      report_blob: Contents of the report.

    Raises:
      ServerException on error.
    """
    report_path = os.path.join(self._GetReportsDir(), report_name)
    in_progress_path = report_path + IN_PROGRESS_SUFFIX
    try:
      with open(in_progress_path, 'wb') as f:
        f.write(report_blob)
      self._CheckReportIntegrity(in_progress_path)
      shutil.move(in_progress_path, report_path)
    finally:
      try:
        # Attempt to remove the in-progress file (e.g., if the
        # integrity check failed)
        os.unlink(in_progress_path)
      except OSError:
        pass

  def _CheckReportIntegrity(self, report_path):
    """Checks the integrity of a report.

    This checks to make sure that "tar tf" on the report does not return any
    errors, and that the report contains var/factory/log/factory.log.

    Raises:
      ServerException on error.
    """
    process = Spawn(['tar', '-tf', report_path], log=True,
                    read_stdout=True, read_stderr=True)

    if process.returncode:
      error = 'Corrupt report: tar failed'
    elif (paths.FACTORY_LOG_PATH_ON_DEVICE.lstrip('/') not in
          process.stdout_data.split('\n')):
      error = 'Corrupt report: %s missing' % (
          paths.FACTORY_LOG_PATH_ON_DEVICE.lstrip('/'))
    else:
      # OK!  Save the MD5SUM (removing the INPROGRESS suffix if any)
      # and return.
      md5_path = report_path
      if report_path.endswith(IN_PROGRESS_SUFFIX):
        md5_path = md5_path[:-len(IN_PROGRESS_SUFFIX)]
      md5_path += '.md5'
      try:
        with open(md5_path, 'w') as f:
          Spawn(['md5sum', report_path], stdout=f, check_call=True)
      except Exception:
        try:
          os.unlink(md5_path)
        except OSError:
          pass
        raise
      return

    error += ': tar returncode=%d, stderr=%r' % (
        process.returncode, process.stderr_data)
    logging.error(error)
    raise ServerException(error)

  def _GetLogsDir(self, subdir=None, log_format=LOGS_DIR_FORMAT):
    """Returns the active logs directory.

    This is the data directory base plus a path element 'subdir'. When
    log_format is not None, it creates one more level of log folder to
    rotate the logs. Default log_format is "logs.YYMMDD", where YYMMDD
    is today's date in the local time zone.  This creates the directory
    if it does not exist.

    Args:
      subdir: If not None, this is appended to the path.
      log_format: strftime log format for log rotation.
    """
    ret = self.data_dir
    if subdir:
      ret = os.path.join(ret, subdir)
      file_utils.TryMakeDirs(ret)
    if log_format:
      ret = os.path.join(ret, time.strftime(log_format))
      file_utils.TryMakeDirs(ret)
    return ret

  def _GetEventsDir(self):
    """Returns the active events directory."""
    return self._GetLogsDir(EVENTS_DIR, log_format=None)

  def _GetIncrementalEventsDir(self):
    """Returns the active incremental events directory."""
    return self._GetLogsDir(INCREMENTAL_EVENTS_DIR,
                            log_format=HOURLY_DIR_FORMAT)

  def _GetReportsDir(self):
    """Returns the active reports directory."""
    if self.reports_rotate_hourly:
      return self._GetLogsDir(REPORTS_DIR, log_format=HOURLY_DIR_FORMAT)
    return self._GetLogsDir(REPORTS_DIR)

  def _GetAuxLogsDir(self):
    """Returns the active auxiliary logs directory."""
    return self._GetLogsDir(AUX_LOGS_DIR)

  def SetEventHourlyRotation(self, value):
    """Enables the option for additional hourly rotation of events."""
    self.events_rotate_hourly = value
    return self.events_rotate_hourly

  def SetReportHourlyRotation(self, value):
    """Enables the option for hourly rotation of reports."""
    self.reports_rotate_hourly = value
    return self.reports_rotate_hourly

  def Ping(self):
    """Always returns true (for client to check if server is working)."""
    return True

  def GetCROSPayloadURL(self, x_umpire_dut):
    """Returns URL of cros_payload JSON file on Mini-Omaha."""
    del x_umpire_dut  # Unused.
    return self.miniomaha_payload_url

  def ListParameters(self, pattern):
    """Lists files that match the pattern in parameters directory.

     Args:
       pattern: A pattern string for glob to list matched files.

     Returns:
       A list of matched files.

     Raises:
       ValueError if caller is trying to query outside parameters directory.
    """
    glob_pathname = os.path.abspath(os.path.join(self.parameters_dir, pattern))
    if not glob_pathname.startswith(self.parameters_dir):
      raise ValueError('ListParameters is limited to parameter directory')

    matched_file = glob.glob(glob_pathname)
    # Only return files.
    matched_file = filter(os.path.isfile, matched_file)
    return [os.path.relpath(x, self.parameters_dir) for x in matched_file]

  # TODO(itspeter): Implement DownloadParameter.
  def GetParameter(self, path):
    """Gets the assigned parameter file.

     Args:
       path: A relative path for locating the parameter.

     Returns:
       Content of the parameter. It is always wrapped in a shopfloor.Binary
       object to provides best flexibility.

     Raises:
       ValueError if the parameter does not exist or is not under
       parameters folder.
    """
    abspath = os.path.abspath(os.path.join(self.parameters_dir, path))
    if not abspath.startswith(self.parameters_dir):
      raise ValueError('GetParameter is limited to parameter directory')

    if not os.path.isfile(abspath):
      raise ValueError('File does not exist or it is not a file')

    return xmlrpclib.Binary(open(abspath).read())

  def GetHWIDUpdater(self):
    """Returns a HWID updater bundle, if available.

    Rgeturns:
      The binary-encoded contents of a file named 'hwid_*' in the data
      directory.  If there are no such files, returns None.

    Raises:
      ServerException if there are >1 HWID bundles available.
    """
    path = self.update_server.hwid_path
    return xmlrpclib.Binary(open(path).read()) if path else None

  def UploadReport(self, serial, report_blob, report_name=None, stage=None):
    """Uploads a report file.

    Args:
      serial: A string of device serial number.
      report_blob: Blob of compressed report to be stored (must be prepared by
          shopfloor.Binary)
      report_name: (Optional) Suggested report file name. This is uslally
          assigned by factory test client programs (ex, gooftool); however
          server implementations still may use other names to store the report.
      stage: (Optional) Prefix of the default report file name.

    Returns:
      True on success.

    Raises:
      ValueError if serial is invalid, or other exceptions defined by individual
      modules. Note this will be converted to xmlrpclib.Fault when being used as
      a XML-RPC server module.
    """
    name = report_name or '%s-%s-%s.rpt.xz' % (
        stage or 'FA', serial, self._Timestamp())
    return self._SaveReport(name, self._UnwrapBlob(report_blob))

  def SaveAuxLog(self, name, contents):
    """Saves an auxiliary log into the logs.$(DATE)/aux_logs directory.

    In general, this should probably be compressed to save space.

    Args:
      name: Name of the report.  Any existing log with the same name will be
        overwritten.  Subdirectories are allowed.
      contents: Contents of the report.  If this is binary, it should be
        wrapped in a shopfloor.Binary object.
    """
    contents = self._UnwrapBlob(contents)

    # Disallow absolute paths and paths with '..'.
    assert not os.path.isabs(name)
    assert '..' not in os.path.split(name)

    path = os.path.join(self._GetAuxLogsDir(), name)
    file_utils.TryMakeDirs(os.path.dirname(path))
    with open(path, 'wb') as f:
      f.write(contents)

  def LogRegistrationCodeMap(self, hwid, registration_code_map,
                             log_filename='registration_code_log.csv',
                             board=None):
    """Logs that a particular registration code has been used.
    Args:
      hwid: HWID object, could be None.
      registration_code_map: A dict contains 'user' and 'group' reg code.
      log_filename: File to append log to.
      board: Board name. If None, will try to derive it from hwid.

    Raises:
      ValueError if the registration code is invalid.
      ValueError if both board and hwid are None.
    """
    for key in ('user', 'group'):
      CheckRegistrationCode(registration_code_map[key])

    if not board:
      if hwid:
        board = hwid.partition(' ')[0]
      else:
        raise ValueError('Both board and hwid are missing.')

    if not hwid:
      hwid = ''

    # See http://goto/nkjyr for file format.
    with open(os.path.join(self.data_dir, log_filename), 'ab') as f:
      csv.writer(f, dialect=NewlineTerminatedCSVDialect).writerow([
          board,
          registration_code_map['user'],
          registration_code_map['group'],
          time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()),
          hwid])
      os.fdatasync(f.fileno())

  def GetFactoryLogPort(self):
    """Returns the port to use for rsync factory logs.

    Returns:
      The port, or None if there is no factory log server available.
    """
    return self.log_server.rsyncd_port if self.log_server else None

  def GetTestMd5sum(self):
    """Gets the latest md5sum of dynamic test tarball.

    Returns:
      A string of md5sum.  None if no dynamic test tarball is installed.
    """
    return self.update_server.GetTestMd5sum()

  def NeedsUpdate(self, device_md5sum):
    """Checks if the device with device_md5sum needs an update."""
    return self.update_server.NeedsUpdate(device_md5sum)

  def GetUpdatePort(self):
    """Returns the port to use for rsync updates.

    Returns:
      The port, or None if there is no update server available.
    """
    return self.update_server.rsyncd_port if self.update_server else None

  def UploadEvent(self, log_name, chunk):
    """Uploads a chunk of events.

    In addition to append events to a single file, we appends event to a
    directory that split on an hourly basis in order to fetch events in a timely
    approach if events_rotate_hourly flag set to True.

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
    chunk = self._UnwrapBlob(chunk)

    log_file = os.path.join(self._GetEventsDir(), log_name)
    with open(log_file, 'a') as f:
      f.write(chunk)

    # Wrote events split on an hourly basis
    if self.events_rotate_hourly:
      log_file = os.path.join(self._GetIncrementalEventsDir(), log_name)
      with open(log_file, 'a') as f:
        f.write(chunk)

    return True

  def GetTime(self):
    """Returns the current time in seconds since the epoch."""
    return time.time()

  def Finalize(self, serial_number):
    """Deprecated API."""
    return self.NotifyEvent({'serial_number': serial_number}, 'Finalize')

  def FinalizeFQC(self, serial_number):
    """Deprecated API."""
    return self.NotifyEvent({'serial_number': serial_number}, 'Refinalize')

  # Functions below are Shopfloor Service API.

  def GetVersion(self):
    """Returns the version of supported protocol."""
    return self.service.GetVersion()

  def NotifyStart(self, data, station):
    """Notifies shopfloor backend that DUT entered a manufacturing station."""
    return self.service.NotifyStart(data, station)

  def NotifyEnd(self, data, station):
    """Notifies shopfloor backend that DUT leaves a manufacturing station."""
    return self.service.NotifyEnd(data, station)

  def NotifyEvent(self, data, event):
    """Notifies shopfloor backend that the DUT has performed an event."""
    return self.service.NotifyEvent(data, event)

  def GetDeviceInfo(self, data):
    """Returns information about the device's expected configuration."""
    return self.service.GetDeviceInfo(data)

  def ActivateRegCode(self, ubind_attribute, gbind_attribute, hwid):
    """Notifies shopfloor backend that DUT has deployed a registration code."""
    return self.service.ActivateRegCode(ubind_attribute, gbind_attribute, hwid)

  def UpdateTestResult(self, data, test_id, status, details=None):
    """Sends the specified test result to shopfloor backend."""
    return self.service.UpdateTestResult(data, test_id, status, details)


def _LoadFactoryUpdater(updater_name):
  """Loads factory updater module.

  Args:
    updater_name: Name of updater module containing a FactoryUpdateServer class.

  Returns:
    Module reference.
  """
  logging.debug('_LoadUpdater: trying %s', updater_name)
  return __import__(updater_name,
                    fromlist=['FactoryUpdater']).FactoryUpdater


class MyXMLRPCServer(SocketServer.ThreadingMixIn,
                     SimpleXMLRPCServer):
  """XML/RPC server subclass that logs method calls."""
  # For saving method name and exception between _marshaled_dispatch and
  # _dispatch.
  local = threading.local()

  def _marshaled_dispatch(  # pylint: disable=W0221
      self, data, dispatch_method=None, path=None):
    self.local.method = None
    self.local.exception = None

    response_data = ''
    start_time = time.time()
    try:
      extra_args = [path] if path else []
      response_data = SimpleXMLRPCServer._marshaled_dispatch(
          self, data, dispatch_method, *extra_args)
      return response_data
    finally:
      logging.info('%s %s [%.3f s, %d B in, %d B out]%s',
                   self.local.client_address[0],
                   self.local.method,
                   time.time() - start_time,
                   len(data),
                   len(response_data),
                   (': %s' % self.local.exception
                    if self.local.exception else ''))

  def _dispatch(self, method, params):
    try:
      self.local.method = method
      return SimpleXMLRPCServer._dispatch(self, method, params)
    except Exception:
      logging.exception('Exception in method %s', method)
      self.local.exception = debug_utils.FormatExceptionOnly()
      raise


class MyXMLRPCRequestHandler(SimpleXMLRPCRequestHandler):

  def do_POST(self):
    MyXMLRPCServer.local.client_address = self.client_address
    SimpleXMLRPCRequestHandler.do_POST(self)


def _GetServer(address, port, instance):
  """Get a XML-RPC server in given address and port.

  Args:
    address: Address to bind server.
    port: Port for server to listen.
    instance: Server instance for incoming XML RPC requests.

  Returns:
    The XML-RPC server.
  """
  server = MyXMLRPCServer((address, port), MyXMLRPCRequestHandler,
                          allow_none=True, logRequests=False)
  server.register_introspection_functions()
  server.register_instance(instance)
  return server


def main():
  """Main entry when being invoked by command line."""
  default_data_dir = 'shopfloor_data'
  external_updater_dir = 'updates'
  if not os.path.exists(default_data_dir) and (
      'CROS_WORKON_SRCROOT' in os.environ):
    default_data_dir = os.path.join(
        os.environ['CROS_WORKON_SRCROOT'],
        'src', 'platform', 'factory', 'shopfloor_data')

  parser = optparse.OptionParser()
  parser.add_option('-a', '--address', dest='address', metavar='ADDR',
                    default=_DEFAULT_SERVER_ADDRESS,
                    help='address to bind (default: %default)')
  parser.add_option('-p', '--port', dest='port', metavar='PORT', type='int',
                    default=DEFAULT_SERVER_PORT,
                    help='port to bind (default: %default)')
  parser.add_option('-d', '--data-dir', dest='data_dir', metavar='DIR',
                    default=default_data_dir,
                    help=('data directory for shop floor system '
                          '(default: %default)'))
  parser.add_option('-s', '--shopfloor-service-url',
                    dest='shopfloor_service_url', default=None,
                    help='URL to shopfloor service backend.')
  parser.add_option('-m', '--miniomaha-payload-url',
                    dest='miniomaha_payload_url', default=None,
                    help='URL to cros_payload JSON file on Mini-Omaha.')
  parser.add_option('-v', '--verbose', action='count', dest='verbose',
                    help='increase message verbosity')
  parser.add_option('-q', '--quiet', action='store_true', dest='quiet',
                    help='turn off verbose messages')
  parser.add_option(
      '--auto-archive-logs', metavar='TEMPLATE',
      default='/media/shopfloorlg/logs.DATE.tar.bz2',
      help=("File in which to automatically archive previous few days' logs. "
            "Logs will be archived if this path's parent exists.  The format "
            "must contain the string 'DATE'; this will be replaced with "
            'the date. (default: %default)'))
  parser.add_option(
      '--auto-archive-logs-days', metavar='NUM_DAYS', type=int,
      default=3, help="Number of previous days' logs to save to USB.")
  parser.add_option('-u', '--updater', dest='updater', metavar='UPDATER',
                    default=None,
                    help=('factory updater module to load, in'
                          'PACKAGE.MODULE.CLASS format. E.g.: '
                          'cros.factory.shopfloor.launcher.external_updater '
                          '(default: %default)'))
  parser.add_option('--updater-dir', dest='updater_dir', metavar='UPDATE_DIR',
                    default=external_updater_dir,
                    help='external updater module dir. (default: %default)')
  (options, args) = parser.parse_args()
  if args:
    parser.error('Invalid args: %s' % ' '.join(args))

  verbosity_map = {0: logging.INFO,
                   1: logging.DEBUG}
  verbosity = verbosity_map.get(options.verbose or 0, logging.NOTSET)
  log_format = '%(asctime)s %(levelname)s '
  if options.verbose > 0:
    log_format += '(%(filename)s:%(lineno)d) '
  log_format += '%(message)s'
  logging.basicConfig(level=verbosity, format=log_format)
  if options.quiet:
    logging.disable(logging.INFO)

  # If address and/or port are set in env variables, use them.
  if os.environ.get(SHOPFLOOR_ADDR_ENV_VAR):
    options.address = os.environ.get(SHOPFLOOR_ADDR_ENV_VAR)
  if os.environ.get(SHOPFLOOR_PORT_ENV_VAR):
    options.port = int(os.environ.get(SHOPFLOOR_PORT_ENV_VAR))

  debug_utils.MaybeStartDebugServer()

  # Disable all DNS lookups, since otherwise the logging code may try to
  # resolve IP addresses, which may delay request handling.
  def FakeGetFQDN(name=''):
    return name or 'localhost'
  socket.getfqdn = FakeGetFQDN

  updater = None
  if options.updater:
    logging.debug('Loading factory updater: %s', options.updater)
    updater = _LoadFactoryUpdater(options.updater)(options.updater_dir)

  instance = FactoryServer(options.data_dir, options.address, options.port,
                           options.auto_archive_logs,
                           options.auto_archive_logs_days,
                           shopfloor_service_url=options.shopfloor_service_url,
                           miniomaha_payload_url=options.miniomaha_payload_url,
                           updater=updater)

  def handler(signum, frame):
    del signum, frame  # Unused.
    raise SystemExit

  signal.signal(signal.SIGTERM, handler)
  signal.signal(signal.SIGINT, handler)

  server = _GetServer(address=options.address, port=options.port,
                      instance=instance)
  try:
    instance._Start()  # pylint: disable=protected-access
    logging.debug('Starting RPC server...')
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    logging.info('Server started: http://%s:%s "%s" version %s',
                 options.address, options.port, instance.NAME,
                 instance.VERSION)
    signal.pause()
  finally:
    logging.debug('Stopping RPC Server')
    net_utils.ShutdownTCPServer(server)
    thread.join()
    instance._Stop()  # pylint: disable=protected-access


if __name__ == '__main__':
  main()
