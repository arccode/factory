# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Wrapper for Factory Shop Floor.

This module provides a simple interface for all factory tests to access ChromeOS
factory shop floor system.

The test program can use set_enabled() and is_enabled() to set/query the status
of shop floor system usage, set_server_url() to configure shop floor server
location, then set_serial_number() to bind device, get_*() to retrieve data.

For the protocol details, check:
 src/platform/factory-utils/factory_setup/shopfloor_server.
"""

import urlparse
import xmlrpclib
from xmlrpclib import Binary, Fault

import factory_common
from autotest_lib.client.cros import factory


# Key names for factory state shared data
KEY_ENABLED = "shopfloor.enabled"
KEY_SERVER_URL = "shopfloor.server_url"
KEY_SERIAL_NUMBER = "shopfloor.serial_number"

KEY_GET_HWID = "shopfloor.GetHWID"
KEY_GET_VPD = "shopfloor.GetVPD"
ALL_CACHED_DATA_KEYS = (KEY_GET_HWID, KEY_GET_VPD)

API_GET_HWID = 'GetHWID'
API_GET_VPD = 'GetVPD'

# Default port number from shopfloor_server.py.
_DEFAULT_SERVER_PORT = 8082

# ----------------------------------------------------------------------------
# Utility Functions


def is_enabled():
    """Checks if current factory is configured to use shop floor system.

    Return True if shop floor is enabled, otherwise False.
    """
    return factory.get_shared_data(KEY_ENABLED, False)


def set_enabled(enabled):
    """Enable/disable using shop floor in current factory flow."""
    factory.set_shared_data(KEY_ENABLED, enabled)


def set_server_url(url):
    """Sets default shop floor server URL for further calls."""
    factory.set_shared_data(KEY_SERVER_URL, url)


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


def get_instance(url=None):
    """Gets an instance (for client side) to access the shop floor server.

    @param url: URL of the shop floor server. If None, use the value in
            factory shared data.
    @return An object with all public functions from shopfloor.ShopFloorBase.
    """
    if not url:
        url = factory.get_shared_data(KEY_SERVER_URL)
    return xmlrpclib.ServerProxy(url, allow_none=True, verbose=False)


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


def set_serial_number(serial_number):
    """Sets a serial number as pinned in factory shared data."""
    # TODO(hungte) Move serial number somewhere else (disk, memory) to prevent
    # dependency on factory modules.
    factory.set_shared_data(KEY_SERIAL_NUMBER, serial_number)


def get_serial_number():
    """Gets current pinned serial number from factory shared data."""
    return factory.get_shared_data(KEY_SERIAL_NUMBER)


def get_data(key_name, api_name, force):
    """Gets (and cache) a shop floor system data.

    @param key_name: The key name of data to access (KEY_*).
    @param api_name: The shop floor remote API name to query given key (API_*).
    @param force: True to discard cache and re-fetch data from remote shop floor
        server; False to use cache from factory shared data, if available.

    @return: The data associated by key_name.
    """
    value = factory.get_shared_data(key_name, None)
    if force or (value is None):
        value = getattr(get_instance(), api_name)(get_serial_number())
        factory.set_shared_data(key_name, value)
    return value


def expire_cached_data():
    """Discards any data cached by get_data."""
    # TODO(hungte) Drop the caching system if no partners really needs it.
    for key in ALL_REMOTE_DATA_KEYS:
        if not factory.has_shared_data(key):
            continue
        factory.del_shared_data(key)


def check_serial_number(serial_number):
    """Checks if given serial number is valid."""
    # Use GetHWID to check serial number.
    return get_instance().GetHWID(serial_number)


def get_hwid(force=False):
    """Gets HWID associated with current pinned serial number.

    @param force: False to use previously cached data; True to discard cache.
    """
    return get_data(KEY_GET_HWID, API_GET_HWID, force)


def get_vpd(force=False):
    """Gets VPD associated with current pinned serial number.

    @param force: False to use previously cached data; True to discard cache.
    """
    return get_data(KEY_GET_VPD, API_GET_VPD, force)


def upload_report(blob, name=None):
    """Uploads a report (generated by gooftool) to shop floor server.

    @param blob: The report (usually a gzipped bitstream) data to upload.
    @param name: An optional file name suggestion for server. Usually this
        should be the default file name created by gooftool; for reports
        generated by other tools, None allows server to choose arbitrary name.
    """
    get_instance().UploadReport(get_serial_number(), Binary(blob), name)


def finalize():
    """Notifies shop floor server this DUT has finished testing."""
    get_instance().Finalize(get_serial_number())
