#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrapper for Factory Shop Floor.

This module provides a simple interface for all factory tests to access ChromeOS
factory shop floor system.

The common flow is:
  - Sets shop floor server URL by shopfloor.set_server_url(url).
  - Tries shopfllor.check_serial_number(sn) until a valid value is found.
  - Calls shopfloor.set_enabled(True) to notify other tests.
  - Gets data by shopfloor.get_*() (ex, get_hwid()).
  - Uploads reports by shopfloor.upload_report(blob, name).
  - Finalize by shopfloor.finalize()

For the protocol details, check:
 src/platform/factory/py/shopfloor/factory_server.py.
"""

import hashlib
import logging
import os
import time
import urlparse
import xmlrpclib
from xmlrpclib import Binary

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test import factory
from cros.factory.test import state
from cros.factory.umpire.client import get_update
from cros.factory.umpire.client import umpire_server_proxy
from cros.factory.utils import debug_utils
from cros.factory.utils import file_utils


# Name of the factory shared data key that maps to session info.
KEY_SHOPFLOOR_SESSION = 'shopfloor.session'

# Session data will be serialized, so we're not using class/namedtuple. The
# session is a simple dictionary with following keys:
SESSION_SERVER_URL = 'server_url'
SESSION_ENABLED = 'enabled'

# Default port number from factory_server.py.
DEFAULT_SERVER_PORT = 8082

# Environment variable containing the shopfloor server URL (for
# testing). Setting this overrides the shopfloor server URL and
# causes the shopfloor server to be considered enabled.
SHOPFLOOR_SERVER_ENV_VAR_NAME = 'CROS_SHOPFLOOR_SERVER_URL'

# Exception message when shopfloor server is not configured.
SHOPFLOOR_NOT_CONFIGURED_STR = 'Shop floor server URL is not configured'

# Default timeout and retry interval for getting a valid shopfloor instance.
SHOPFLOOR_TIMEOUT_SECS = 10  # Timeout for shopfloor connection.
SHOPFLOOR_RETRY_INTERVAL_SECS = 10  # Seconds to wait between retries.

# Some tests refer to "shopfloor.Fault" so we need to export it from
# shopfloor.
Fault = xmlrpclib.Fault

# ----------------------------------------------------------------------------
# Exception Types


class ServerFault(Exception):
  """Server fault exception."""
  pass


def _server_api(call):
  """Decorator of calls to remote server.

  Converts xmlrpclib.Fault generated during remote procedural call to better
  and simplified form (shopfloor.ServerFault).
  """
  def wrapped_call(*args, **kargs):
    try:
      return call(*args, **kargs)
    except xmlrpclib.Fault as e:
      logging.exception('Shopfloor server:')
      raise ServerFault(e.faultString.partition(':')[2])
  wrapped_call.__name__ = call.__name__
  return wrapped_call

# ----------------------------------------------------------------------------
# Utility Functions


def _fetch_current_session():
  """Gets current shop floor session from factory states shared data.

  If no session is stored yet, create a new default session.
  """
  if state.has_shared_data(KEY_SHOPFLOOR_SESSION):
    session = state.get_shared_data(KEY_SHOPFLOOR_SESSION)
  else:
    session = {
        SESSION_SERVER_URL: None,
        SESSION_ENABLED: False,
    }
    state.set_shared_data(KEY_SHOPFLOOR_SESSION, session)
  return session


def _set_session(key, value):
  """Sets shop floor session value to factory states shared data."""
  # Currently there's no locking/transaction mechanism in state shared_data,
  # so there may be race-condition issue if multiple background tests try to
  # set shop floor session data at the same time. However since shop floor
  # session should be singularily configured in the very beginning, let's fix
  # this only if that really becomes an issue.
  session = _fetch_current_session()
  assert key in session, 'Unknown session key: %s' % key
  session[key] = value
  state.set_shared_data(KEY_SHOPFLOOR_SESSION, session)


def _get_session(key):
  """Gets shop floor session value from factory states shared data."""
  session = _fetch_current_session()
  assert key in session, 'Unknown session key: %s' % key
  return session[key]


def is_enabled():
  """Checks if current factory is configured to use shop floor system."""
  return (bool(os.environ.get(SHOPFLOOR_SERVER_ENV_VAR_NAME)) or
          _get_session(SESSION_ENABLED))


def set_enabled(enabled):
  """Enable/disable using shop floor in current factory flow."""
  _set_session(SESSION_ENABLED, enabled)


def set_server_url(url):
  """Sets default shop floor server URL for further calls."""
  _set_session(SESSION_SERVER_URL, url)


def get_server_url(detect=True):
  """Gets shop floor server URL.

  Args:
    detect: If True, attempts to detect the URL with
      detect_default_server_url().
  """
  url = (os.environ.get(SHOPFLOOR_SERVER_ENV_VAR_NAME) or
         _get_session(SESSION_SERVER_URL))
  if detect:
    url = url or detect_default_server_url()
  return url


def detect_default_server_url():
  """Tries to find a default shop floor server URL.

    Searches from lsb-* files and deriving from mini-omaha server location.
  """
  lsb_values = factory.get_lsb_data()
  # FACTORY_OMAHA_URL is written by factory_install/factory_install.sh
  omaha_url = lsb_values.get('FACTORY_OMAHA_URL', None)
  if omaha_url:
    omaha = urlparse.urlsplit(omaha_url)
    netloc = '%s:%s' % (omaha.netloc.split(':')[0], DEFAULT_SERVER_PORT)
    return urlparse.urlunsplit((omaha.scheme, netloc, '/', '', ''))
  return None


def get_instance(url=None, detect=False, timeout=None, quiet=False):
  """Gets an instance (for client side) to access the shop floor server.

  Args:
    url: URL of the shop floor server. If None, use the value in
      factory shared data.
    detect: If True, attempt to detect the server URL if none is
      specified.
    timeout: If not None, the timeout in seconds. This timeout is for RPC
      calls on the proxy, not for get_instance() itself.
    quiet: Suppresses error messages when shopfloor can not be reached.

  Returns:
    A TimeoutUmpireServerProxy object that can work with either
    simple XMLRPC server or Umpire server.
  """
  if not url:
    url = get_server_url(detect=detect)
  if not url:
    raise Exception(SHOPFLOOR_NOT_CONFIGURED_STR)
  return umpire_server_proxy.TimeoutUmpireServerProxy(
      url, quiet=quiet, allow_none=True, verbose=False, timeout=timeout)


@_server_api
def check_server_status(instance=None):
  """Checks if the given instance is successfully connected.

  Args:
    instance: Instance object created get_instance, or None to create a
        new instance.

  Returns:
    True for success, otherwise raise exception.
  """
  try:
    if instance is None:
      instance = get_instance()
    instance.Ping()
  except Exception:
    raise
  return True


# ----------------------------------------------------------------------------
# Functions to access shop floor server by APIs defined by ChromeOS factory shop
# floor system (see src/platform/factory/py/shopfloor/*).


@_server_api
def check_serial_number(serial_number):
  """Checks if given serial number is valid."""
  return get_instance().CheckSN(serial_number)


@_server_api
def get_hwid():
  """Gets HWID associated with current pinned serial number."""
  return get_instance().GetHWID(state.GetSerialNumber())


@_server_api
def get_hwid_updater():
  """Gets HWID updater, if any."""
  hwid_updater = None
  proxy = get_instance()
  if proxy.use_umpire:
    hwid_updater = get_update.GetUpdateForHWID(proxy)
  else:
    hwid_updater = proxy.GetHWIDUpdater()
    if isinstance(hwid_updater, Binary):
      hwid_updater = hwid_updater.data
  return hwid_updater


@_server_api
def get_firmware_updater():
  """Gets firmware updater, if any."""
  firmware_updater = None
  proxy = get_instance()
  if proxy.use_umpire:
    firmware_updater = get_update.GetUpdateForFirmware(proxy)
  else:
    raise Exception('Firmware update from network is only supported by Umpire')

  if not firmware_updater:
    logging.info('No firmware updater available on shopfloor')
    return False

  with open(paths.FACTORY_FIRMWARE_UPDATER_PATH, 'wb') as f:
    f.write(firmware_updater)

  logging.info('Writing firmware updater from shopfloor to %s',
               paths.FACTORY_FIRMWARE_UPDATER_PATH)
  os.chmod(paths.FACTORY_FIRMWARE_UPDATER_PATH, 0755)
  return True


def update_local_hwid_data(dut, target_dir='/usr/local/factory/hwid'):
  """Updates HWID information from shopfloor server.

  Executes the HWID updater retrieved from the shopfloor server
  (which generally overwrites files in /usr/local/factory/hwid).

  Returns:
    True if updated, False if no update was available.
  """
  updater_data = get_hwid_updater()
  if updater_data:
    with dut.temp.TempFile(
        prefix='hwid_updater.', suffix='.sh') as hwid_updater_sh:
      dut.WriteFile(hwid_updater_sh, updater_data)
      dut.CheckCall(['chmod', '0755', hwid_updater_sh])
      factory.console.info(
          'Received HWID updater %s from shopfloor server (md5sum %s); '
          'executing',
          hwid_updater_sh,
          hashlib.md5(updater_data).hexdigest())

      console_log_path = paths.CONSOLE_LOG_PATH
      file_utils.TryMakeDirs(os.path.dirname(console_log_path))
      with open(console_log_path, 'a') as log:
        if not dut.path.isdir(target_dir):
          dut.CheckCall(['mkdir', '-p', target_dir])
        dut.CheckCall([hwid_updater_sh, target_dir],
                      stdout=log, stderr=log)
        dut.CheckCall('sync')
      # TODO(youcheng): invalidate cache of dut instance in goofy properly
      dut.info.Invalidate('hwid_database_version')
    return True
  else:
    factory.log('No HWID update available from shopfloor server')
    return False


@_server_api
def get_vpd():
  """Gets VPD associated with current pinned serial number."""
  return get_instance().GetVPD(state.GetSerialNumber())


@_server_api
def get_registration_code_map():
  """Gets registration codes associated with current pinned serial number."""
  return get_instance().GetRegistrationCodeMap(state.GetSerialNumber())


@_server_api
def upload_report(blob, name=None):
  """Uploads a report (generated by gooftool) to shop floor server.

  Args:
    blob: The report (usually a gzipped bitstream) data to upload.
    name: An optional file name suggestion for server. Usually this
        should be the default file name created by gooftool; for reports
        generated by other tools, None allows server to choose arbitrary name.
  """
  get_instance().UploadReport(state.GetSerialNumber(), Binary(blob), name)


@_server_api
def finalize():
  """Notifies shop floor server this DUT has finished testing."""
  get_instance().Finalize(state.GetSerialNumber())


def GetShopfloorConnection(
    timeout_secs=SHOPFLOOR_TIMEOUT_SECS,
    retry_interval_secs=SHOPFLOOR_RETRY_INTERVAL_SECS):
  """Returns a shopfloor client object.

  Try forever until a connection of shopfloor is established.

  Args:
    timeout_secs: Timeout for shopfloor connection.
    retry_interval_secs: Seconds to wait between retries.
  """
  factory.console.info('Connecting to shopfloor...')
  iteration = 0
  while True:
    iteration += 1
    try:
      shopfloor_client = get_instance(
          detect=True, timeout=timeout_secs)
      check_server_status(shopfloor_client)
      break
    except Exception:
      exception_string = debug_utils.FormatExceptionOnly()
      # Log only the exception string, not the entire exception,
      # since this may happen repeatedly.
      factory.console.info(
          'Unable to sync with shopfloor server in iteration [%3d], '
          'retry after [%2dsecs]: %s',
          iteration, retry_interval_secs, exception_string)
    time.sleep(retry_interval_secs)
  return shopfloor_client


def UploadAuxLogs(file_paths, ignore_on_fail=False, dir_name=None):
  """Attempts to upload arbitrary files to the shopfloor server.
  Args:
    file_paths: file paths which would like to be uploaded.
    ignore_on_fail: do not raise exception if the value is True.
    dir_name: relative directory on shopfloor.
  """
  shopfloor_client = GetShopfloorConnection()
  for file_path in file_paths:
    try:
      chunk = open(file_path, 'r').read()
      log_name = os.path.basename(file_path)
      if dir_name:
        log_name = os.path.join(dir_name, log_name)
      factory.console.info('Uploading %s', log_name)
      start_time = time.time()
      shopfloor_client.SaveAuxLog(log_name, Binary(chunk))
      factory.console.info('Successfully synced %s in %.03f s',
                           log_name, time.time() - start_time)
    except Exception:
      if ignore_on_fail:
        factory.console.info(
            'Failed to sync with shopfloor for [%s], ignored',
            log_name)
      else:
        raise
