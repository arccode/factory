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
 src/platform/factory-utils/factory_setup/shopfloor_server.
"""

import hashlib
import logging
import os
import tempfile
import urlparse
import xmlrpclib
from xmlrpclib import Binary

import factory_common # pylint: disable=W0611
from cros.factory import privacy
from cros.factory.test import factory, utils
from cros.factory.test.event import EventClient, Event
from cros.factory.utils import net_utils
from cros.factory.utils.process_utils import Spawn


# Name of the factory shared data key that maps to session info.
KEY_SHOPFLOOR_SESSION = 'shopfloor.session'

# Prefix for auxiliary session data entries.
KEY_SESSION_AUX_PREFIX = 'shopfloor.aux.'

# Key for device data.  This is a dictionary of accumulated data from
# shopfloor calls with information about the configuration of the
# device.
KEY_DEVICE_DATA = 'shopfloor.device'

# Session data will be serialized, so we're not using class/namedtuple. The
# session is a simple dictionary with following keys:
SESSION_SERIAL_NUMBER = 'serial_number'
SESSION_SERVER_URL = 'server_url'
SESSION_ENABLED = 'enabled'

API_GET_HWID = 'GetHWID'
API_GET_VPD = 'GetVPD'

# A key that can be used in get_aux_data() to refer to the
# motherboard.
AUX_TABLE_MLB = 'mlb'

# Default port number from shopfloor_server.py.
DEFAULT_SERVER_PORT = 8082

# Environment variable containing the shopfloor server URL (for
# testing). Setting this overrides the shopfloor server URL and
# causes the shopfloor server to be considered enabled.
SHOPFLOOR_SERVER_ENV_VAR_NAME = 'CROS_SHOPFLOOR_SERVER_URL'

# Exception message when shopfloor server is not configured.
SHOPFLOOR_NOT_CONFIGURED_STR = "Shop floor server URL is not configured"

# Some tests refer to "shopfloor.Fault" so we need to export it from
# shopfloor.
Fault = xmlrpclib.Fault

# ----------------------------------------------------------------------------
# Exception Types

class ServerFault(Exception):
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

def _get_aux_shared_data_key(table_name):
  return KEY_SESSION_AUX_PREFIX + table_name

def _fetch_current_session():
  """Gets current shop floor session from factory states shared data.

  If no session is stored yet, create a new default session.
  """
  if factory.has_shared_data(KEY_SHOPFLOOR_SESSION):
    session = factory.get_shared_data(KEY_SHOPFLOOR_SESSION)
  else:
    session = {
        SESSION_SERIAL_NUMBER: None,
        SESSION_SERVER_URL: None,
        SESSION_ENABLED: False,
        }
    factory.set_shared_data(KEY_SHOPFLOOR_SESSION, session)
  return session


def _set_session(key, value):
  """Sets shop floor session value to factory states shared data."""
  # Currently there's no locking/transaction mechanism in factory shared_data,
  # so there may be race-condition issue if multiple background tests try to
  # set shop floor session data at the same time. However since shop floor
  # session should be singularily configured in the very beginning, let's fix
  # this only if that really becomes an issue.
  session = _fetch_current_session()
  assert key in session, "Unknown session key: %s" % key
  session[key] = value
  factory.set_shared_data(KEY_SHOPFLOOR_SESSION, session)


def _get_session(key):
  """Gets shop floor session value from factory states shared data."""
  session = _fetch_current_session()
  assert key in session, "Unknown session key: %s" % key
  return session[key]


def reset():
  """Resets session data from factory states shared data."""
  if factory.has_shared_data(KEY_SHOPFLOOR_SESSION):
    factory.del_shared_data(KEY_SHOPFLOOR_SESSION)


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


def get_instance(url=None, detect=False, timeout=None):
  """Gets an instance (for client side) to access the shop floor server.

  @param url: URL of the shop floor server. If None, use the value in
      factory shared data.
  @param detect: If True, attempt to detect the server URL if none is
    specified.
  @param timeout: If not None, the timeout in seconds. This timeout is for RPC
    calls on the proxy, not for get_instance() itself.
  @return An object with all public functions from shopfloor.ShopFloorBase.
  """
  if not url:
    url = get_server_url()
  if not url and detect:
    url = detect_default_server_url()
  if not url:
    raise Exception(SHOPFLOOR_NOT_CONFIGURED_STR)
  return net_utils.TimeoutXMLRPCServerProxy(
    url, allow_none=True, verbose=False, timeout=timeout)


def save_aux_data(table_name, id, data):  # pylint: disable=W0622
  """Saves data from an auxiliary table."""
  logging.info('Setting aux data for table %r to ID %r, value %r',
               table_name, id, data)
  factory.set_shared_data(_get_aux_shared_data_key(table_name),
                          (id, data))


def select_aux_data(table_name, id):  # pylint: disable=W0622
  """Selects a row in an auxiliary table.

  This row's data will be returned for future invocations of
  get_selected_aux_data.

  For instance, one might call:

    select_aux_data('mlb', 'MLB00001')

  ...and from then on,

    get_selected_aux_data('mlb')

  will return the data from the 'mlb' table corresponding to ID 'MLB00001'.

  Returns:
    The data for that row.

  Raises:
    ValueError if the row cannot be found in the shopfloor server.
  """
  data = get_aux_data(table_name, id)
  save_aux_data(table_name, id, data)
  return data


@_server_api
def check_server_status(instance=None):
  """Checks if the given instance is successfully connected.

  @param instance: Instance object created get_instance, or None to create a
      new instance.
  @return True for success, otherwise raise exception.
  """
  try:
    if instance is not None:
      instance = get_instance()
    instance.Ping()
  except:
    raise
  return True


# ----------------------------------------------------------------------------
# Functions to access shop floor server by APIs defined by ChromeOS factory shop
# floor system (see src/platform/factory-utils/factory_setup/shopfloor/*).


@_server_api
def set_serial_number(serial_number):
  """Sets a serial number as pinned in factory shared data."""
  _set_session(SESSION_SERIAL_NUMBER, serial_number)


@_server_api
def get_serial_number():
  """Gets current pinned serial number from factory shared data."""
  return _get_session(SESSION_SERIAL_NUMBER)


@_server_api
def check_serial_number(serial_number):
  """Checks if given serial number is valid."""
  return get_instance().CheckSN(serial_number)


@_server_api
def get_hwid():
  """Gets HWID associated with current pinned serial number."""
  return get_instance().GetHWID(get_serial_number())


@_server_api
def get_hwid_updater():
  """Gets HWID updater, if any."""
  hwid_updater = get_instance().GetHWIDUpdater()
  if isinstance(hwid_updater, Binary):
    hwid_updater = hwid_updater.data
  return hwid_updater


def update_local_hwid_data(target_dir='/usr/local/factory/hwid'):
  """Updates HWID information from shopfloor server.

  Executes the HWID updater retrieved from the shopfloor server
  (which generally overwrites files in /usr/local/factory/hwid).

  Returns:
    True if updated, False if no update was available.
  """
  updater_data = get_hwid_updater()
  if updater_data:
    hwid_updater_sh = tempfile.NamedTemporaryFile(
        prefix='hwid_updater.', suffix='.sh', delete=False)
    hwid_updater_sh.write(updater_data)
    os.fchmod(hwid_updater_sh.fileno(), 0755)
    hwid_updater_sh.close()
    # pylint: disable=E1101
    factory.console.info(
        'Received HWID updater %s from shopfloor server (md5sum %s); '
        'executing',
        hwid_updater_sh.name,
        hashlib.md5(open(hwid_updater_sh.name).read()).hexdigest())

    with open(factory.CONSOLE_LOG_PATH, 'a') as log:
      temp_dir = tempfile.mkdtemp(prefix='hwid_updater_',
                                  dir=os.path.dirname(target_dir))
      Spawn([hwid_updater_sh.name, temp_dir],
            stdout=log, stderr=log, log=True,
            check_call=True)
      Spawn(['sync'], check_call=True)
      for root, _, files in os.walk(temp_dir):
        dst_dir = os.path.join(temp_dir, os.path.relpath(root, temp_dir))
        utils.TryMakeDirs(dst_dir)
        for name in files:
          os.rename(os.path.join(root, name), os.path.join(dst_dir, name))
      Spawn(['sync'], check_call=True)
    return True
  else:
    factory.log('No HWID update available from shopfloor server')
    return False

@_server_api
def get_vpd():
  """Gets VPD associated with current pinned serial number."""
  return get_instance().GetVPD(get_serial_number())

@_server_api
def get_registration_code_map():
  """Gets registration codes associated with current pinned serial number."""
  return get_instance().GetRegistrationCodeMap(get_serial_number())


@_server_api
def get_aux_data(table_name, id):  # pylint: disable=W0622
  """Fetches a row from an auxiliary table.

  Args:
    table_name: The auxiliary table from which to return data.
    id: The ID of the row.

  See GetAuxData in py/shopfloor/__init__.py for details.
  """
  return get_instance().GetAuxData(table_name, id)


def get_selected_aux_data(table_name):
  """Returns the previously selected row from an auxiliary table.

  Args:
    table_name: The auxiliary table from which to return data; or
      device_data to use the device data dict.

  Raises:
    ValueError: If select_aux_data has not yet succeeded for this table.
  """
  if table_name == 'device_data':
    return GetDeviceData()

  dummy_id, data = factory.get_shared_data(
      _get_aux_shared_data_key(table_name), default=(None, None))
  if not data:
    raise ValueError('No aux data selected for table %s' % table_name)
  return data


@_server_api
def upload_report(blob, name=None):
  """Uploads a report (generated by gooftool) to shop floor server.

  @param blob: The report (usually a gzipped bitstream) data to upload.
  @param name: An optional file name suggestion for server. Usually this
    should be the default file name created by gooftool; for reports
    generated by other tools, None allows server to choose arbitrary name.
  """
  get_instance().UploadReport(get_serial_number(), Binary(blob), name)


@_server_api
def finalize():
  """Notifies shop floor server this DUT has finished testing."""
  get_instance().Finalize(get_serial_number())


def GetDeviceData():
  """Returns the accumulated dictionary of device data."""
  return factory.get_shared_data(KEY_DEVICE_DATA, {})


def UpdateDeviceData(new_device_data, post_update_event=True):
  """Returns the accumulated dictionary of device data.

  Args:
    new_device_data: A dict with key/value pairs to update.  Old values
      are overwritten.
    post_update_event: If True, posts an UPDATE_SYSTEM_INFO event to
      update the test list.

  Returns:
    The updated dictionary.
  """
  logging.info('Updating device data: setting %s',
               privacy.FilterDict(new_device_data))
  if 'serial_number' in new_device_data:
    set_serial_number(new_device_data['serial_number'])
  data = factory.get_state_instance().update_shared_data_dict(
      KEY_DEVICE_DATA, new_device_data)
  logging.info('Updated device data; complete device data is now %s',
               privacy.FilterDict(data))
  if post_update_event:
    EventClient().post_event(Event(Event.Type.UPDATE_SYSTEM_INFO))
  return data
