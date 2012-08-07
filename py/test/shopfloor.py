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

import logging
import os
import urlparse
import xmlrpclib
from xmlrpclib import Binary, Fault

import factory_common # pylint: disable=W0611
from cros.factory.utils import net_utils
from cros.factory.test import factory


# Name of the factory shared data key that maps to session info.
KEY_SHOPFLOOR_SESSION = 'shopfloor.session'

# Session data will be serialized, so we're not using class/namedtuple. The
# session is a simple dictionary with following keys:
SESSION_SERIAL_NUMBER = 'serial_number'
SESSION_SERVER_URL = 'server_url'
SESSION_ENABLED = 'enabled'

API_GET_HWID = 'GetHWID'
API_GET_VPD = 'GetVPD'

# Default port number from shopfloor_server.py.
_DEFAULT_SERVER_PORT = 8082

# Environment variable containing the shopfloor server URL (for
# testing). Setting this overrides the shopfloor server URL and
# causes the shopfloor server to be considered enabled.
SHOPFLOOR_SERVER_ENV_VAR_NAME = 'CROS_SHOPFLOOR_SERVER_URL'

# Exception message when shopfloor server is not configured.
SHOPFLOOR_NOT_CONFIGURED_STR = "Shop floor server URL is not configured"

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

def _fetch_current_session():
  """Gets current shop floor session from factory states shared data.

  If no session is stored yet, create a new default session.
  """
  if factory.has_shared_data(KEY_SHOPFLOOR_SESSION):
    session = factory.get_shared_data(KEY_SHOPFLOOR_SESSION)
  else:
    session = {SESSION_SERIAL_NUMBER: None,
          SESSION_SERVER_URL: None,
          SESSION_ENABLED: False}
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


def get_server_url():
  """Gets last configured shop floor server URL."""
  return (os.environ.get(SHOPFLOOR_SERVER_ENV_VAR_NAME) or
      _get_session(SESSION_SERVER_URL))


def detect_default_server_url():
  """Tries to find a default shop floor server URL.

    Searches from lsb-* files and deriving from mini-omaha server location.
  """
  lsb_values = factory.get_lsb_data()
  # FACTORY_OMAHA_URL is written by factory_install/factory_install.sh
  omaha_url = lsb_values.get('FACTORY_OMAHA_URL', None)
  if omaha_url:
    omaha = urlparse.urlsplit(omaha_url)
    netloc = '%s:%s' % (omaha.netloc.split(':')[0], _DEFAULT_SERVER_PORT)
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
  # Use GetHWID to check serial number.
  return get_instance().GetHWID(serial_number)


@_server_api
def get_hwid():
  """Gets HWID associated with current pinned serial number."""
  return get_instance().GetHWID(get_serial_number())


@_server_api
def get_vpd():
  """Gets VPD associated with current pinned serial number."""
  return get_instance().GetVPD(get_serial_number())

@_server_api
def get_registration_code_map():
  """Gets registration codes associated with current pinned serial number."""
  return get_instance().GetRegistrationCodeMap(get_serial_number())


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
