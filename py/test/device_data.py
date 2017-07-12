#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module to manipulate device manufacturing information.

The "Device Data" is a set of mapping data storing manufacturing information for
DUT (device under test), including peripheral information (for example if
touchscreen should be available or not), per-device provisioned data (also known
as Vital Product Data - VPD; for example serial number or shipping region), test
status (has passed SMT, FATP, or other stations).

The Device Data is shared by tests in Chrome OS Factory Software, the test
harness "Goofy" and the "Shopfloor Service API". The values usually come from
pre-defined values, shopfloor backend, or set by tests using manual selection
or barcode scanner (especially serial numbers).

Device Data can be considered as a mapping or dictionary, with following keys:

- ``serials``: A dictionary for serial numbers of device, components, and
  mainboard.  All serial numbers here will be logged by `testlog`, including:

  - ``serial_number``: The serial number of "device" itself (printed on device
    panel).
  - ``mlb_serial_number``: The serial number of main logic board (mainboard).

- ``component``: A dictionary to indicate what peripherals should exist, for
  example:

  - ``has_touchscreen``: A touch screen should be available.

- ``vpd``: A dict for what VPD values need to be set, including:

  - ``ro``: VPD values in RO section (RO_VPD), usually including:

    - ``region``: Region code as defined in http://go/cros-regions.

  - ``rw``: VPD values in RW section (RW_VPD), usually including:

    - ``ubind_attribute``: User registration code.
    - ``gbind_attribute``: Group registration code.

- ``hwid``: A value of probed Hardware ID.
- ``factory``: A dict for manufacturing flow control, used by shopfloor
  backends. See Shopfloor Service API for more details.

For example, a typical device usually has both device serial number and
main board serial number, region VPD, registration codes, thus the device data
will be set to::

  {
    'serials': {
      'serial_number': 'SN1234567890',
      'mlb_serial_number': 'MLB1234567890'
    },
    'vpd': {
      'ro': {
        'region': 'us'
      },
      'rw': {
        'ubind_attribute': '12345',
        'gbind_attribute': '54321',
      }
    }
  }

Using Device Data
-----------------
Device Data is internally stored as Python dict inside shelves, and provided by
`cros.factory.test.state` module via RPC calls.

To get all data as single dict,
use ``GetAllDeviceData``. To get partial data, use ``GetDeviceData`` with key
names joined using dot. For example, to fetch only the ``ro`` values inside
``vpd``::

  GetDeviceData('vpd.ro')

The key names are also defined in this module. All constants starting with
``KEY_`` are complete key names for ``GetDeviceData`` to use. Constants starting
with ``NAME_`` are key names (no dot) of the single dict. For example, following
calls are equivalent if ``vpd.ro.region`` exists::

  GetDeviceData('vpd.ro.region')
  GetDeviceData('vpd').get('ro').get('region')
  GetDeviceData(KEY_VPD).get(NAME_RO).get(NAME_REGION)
  GetDeviceData(KEY_VPD_RO).get(NAME_REGION)
  GetDeviceData(KEY_VPD_REGION)

If ``vpd.ro`` does not exist, ``get('ro')`` will return None so you can't invoke
another ``get('region')`` on it. So using the complete key path
(``vpd.ro.region``) provides an easier way to retrieve single value without
worrying if the intermediate dictionaries exist or not.

Using Serial Number
-------------------
There are some special helpers to access serial number. ``GetSerialNumber`` and
``SetSerialNumber`` expect names of serial numbers (``NAME_*``). But as a syntax
sugar, they will also accept keys with ``KEY_SERIALS`` prefixed. For example,
following calls are equivalent::

  GetSerialNumber('serial_number')
  GetSerialNumber(NAME_SERIAL_NUMBER)
  GetSerialNumber(KEY_SERIAL_NUMBER)
  GetDeviceData(KEY_SERIAL_NUMBER)

Note when setting serial numbers (``SetSerialNumber``), a value evaluates to
false (None, false, empty string...) will **delete** the stored serial number.

API Spec
--------
"""

import collections
import logging
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.test import event
from cros.factory.test.rules import privacy
from cros.factory.test import state
from cros.factory.utils import config_utils
from cros.factory.utils import shelve_utils


# Helper utility for manipulating keys.
JoinKeys = shelve_utils.DictKey.Join

# Keys for accessing device data.
KEY_SERIALS = 'serials'
NAME_SERIAL_NUMBER = 'serial_number'
NAME_MLB_SERIAL_NUMBER = 'mlb_serial_number'
KEY_SERIAL_NUMBER = JoinKeys(KEY_SERIALS, NAME_SERIAL_NUMBER)
KEY_MLB_SERIAL_NUMBER = JoinKeys(KEY_SERIALS, NAME_MLB_SERIAL_NUMBER)

KEY_VPD = 'vpd'
NAME_RO = 'ro'
NAME_RW = 'rw'
KEY_VPD_RO = JoinKeys(KEY_VPD, NAME_RO)
KEY_VPD_RW = JoinKeys(KEY_VPD, NAME_RW)

NAME_REGION = 'region'
NAME_USER_REGCODE = 'ubind_attribute'
NAME_GROUP_REGCODE = 'gbind_attribute'
KEY_VPD_REGION = JoinKeys(KEY_VPD_RO, NAME_REGION)
KEY_VPD_USER_REGCODE = JoinKeys(KEY_VPD_RW, NAME_USER_REGCODE)
KEY_VPD_GROUP_REGCODE = JoinKeys(KEY_VPD_RW, NAME_GROUP_REGCODE)

KEY_COMPONENT = 'component'
KEY_COMPONENT_HAS_TOUCHSCREEN = JoinKeys(KEY_COMPONENT, 'has_touchscreen')

KEY_HWID = 'hwid'
KEY_FACTORY = 'factory'


def _GetInstance():
  """An internal helper utility to get DEVICE_DATA from state module."""
  return state.get_instance().data_shelf[state.KEY_DEVICE_DATA]


def CheckValidDeviceDataKey(key, key_prefix=None):
  """Checks if given key is a valid device data key.

  Args:
    key: A string of key for device data.
    key_prefix: Key must start with this token.

  Raises:
    KeyError if the key is not valid.
  """
  prefix, dot, postfix = key.partition('.')
  if key_prefix and prefix != key_prefix:
    raise KeyError('Key %s must start with %s.' % (key, key_prefix))
  top_level_keys = [KEY_SERIALS, KEY_HWID, KEY_VPD, KEY_COMPONENT, KEY_FACTORY]
  if prefix not in top_level_keys:
    raise KeyError('Key %s must start with one of %r' % (key, top_level_keys))
  if prefix == KEY_SERIALS:
    if '.' in postfix:
      raise KeyError('Serial number name must not contain dots: %s' % postfix)
  elif prefix == KEY_HWID:
    if dot != '':
      raise KeyError('HWID must not have sub keys: %s' % postfix)
  elif prefix == KEY_VPD:
    vpd_sections = [NAME_RO, NAME_RW]
    section, unused_dot, name = postfix.partition('.')
    if section not in vpd_sections:
      raise KeyError('VPD key [%s] must be in the sections: %s' %
                     (key, vpd_sections))
    if '.' in name:
      raise KeyError('VPD entry name must not contain dots: %s' % name)
  return True


def GetDeviceData(key, default=None):
  """Returns the device data associated by key.

  Args:
    key: A string of key to access device data.
    default: The default value if key does not exist.

  Returns:
    Associated value if key exists in device data, otherwise the value specified
    by default. Defaults to None.
  """
  if not isinstance(key, basestring):
    raise KeyError('key must be a string')

  return _GetInstance().GetValue(key, default)


def GetAllDeviceData():
  """Returns all device data in a single dict."""
  return _GetInstance().Get({})


def GetDeviceDataSelector():
  """Returns the data shelf selector rooted at device data.

  This is primarily used by invocation module to resolve TestListArgs.
  """
  return _GetInstance()


def _PostUpdateSystemInfo():
  if not os.getenv(event.CROS_FACTORY_EVENT):
    logging.debug('No CROS_FACTORY_EVENT found, ignore posting event.')
    return

  try:
    with event.EventClient() as event_client:
      event_client.post_event(
          event.Event(event.Event.Type.UPDATE_SYSTEM_INFO))
  except Exception:
    logging.exception('Failed to post update event')


def DeleteDeviceData(delete_keys, optional=False):
  """Deletes given keys from device data.

  Args:
    delete_keys: A list of keys (or a single string) to be deleted.
    optional: False to raise a KeyError if not found.

  Returns:
    The updated dictionary.
  """
  if isinstance(delete_keys, basestring):
    delete_keys = [delete_keys]
  logging.info('Deleting device data: %s', delete_keys)
  data = state.get_instance().delete_shared_data_dict_item(
      state.KEY_DEVICE_DATA, delete_keys, optional)
  logging.info('Updated device data; complete device data is now %s',
               privacy.FilterDict(data))
  _PostUpdateSystemInfo()
  return data


def UpdateDeviceData(new_device_data):
  """Updates existing device data with given new dict data.

  Args:
    new_device_data: A dict with key/value pairs to update.  Old values
        are overwritten.

  Returns:
    The updated dictionary.
  """
  logging.info('Updating device data: setting %s',
               privacy.FilterDict(new_device_data))
  data = state.get_instance().update_shared_data_dict(
      state.KEY_DEVICE_DATA, new_device_data)
  logging.info('Updated device data; complete device data is now %s',
               privacy.FilterDict(data))
  _PostUpdateSystemInfo()
  return data


def _GetSerialNumberKey(name):
  """Returns a full path or serial number key for Device Data API to access."""
  if '.' not in name:
    return JoinKeys(KEY_SERIALS, name)
  CheckValidDeviceDataKey(name, KEY_SERIALS)
  return name


def _GetSerialNumberName(key):
  """Returns the name part of serial number key."""
  return _GetSerialNumberKey(key).partition('.')[2]


def GetAllSerialNumbers():
  """Returns all serial numbers available in device data as dict."""
  return GetDeviceData(KEY_SERIALS, {})


def ClearAllSerialNumbers():
  """Clears all serial numbers stored in device data."""
  DeleteDeviceData([KEY_SERIALS], optional=True)


def GetSerialNumber(name=NAME_SERIAL_NUMBER):
  """Returns a serial number (default to device serial number)."""
  return GetDeviceData(_GetSerialNumberKey(name))


def SetSerialNumber(name, value):
  """Sets a serial number to give nvalue.

  Args:
    name: A string to indicate serial number name.
    value: A string representing the serial number, or anything evaluated
           as False to delete the serial number.
  """
  UpdateSerialNumbers({name: value})


def UpdateSerialNumbers(dict_):
  """Updates stored serial numbers by given dict.

  Args:
    dict_: A mapping of serial number names and values to change.
           A value evaluated as False will delete the serial number from device
           data.
  """
  assert isinstance(dict_, dict)
  new_dict = {}
  keys_to_delete = []
  for key, value in dict_.iteritems():
    if value:
      new_dict[_GetSerialNumberName(key)] = value
    else:
      keys_to_delete.append(_GetSerialNumberKey(key))

  if dict_:
    UpdateDeviceData({KEY_SERIALS: new_dict})

  if keys_to_delete:
    DeleteDeviceData(keys_to_delete, optional=True)


def FlattenData(data, parent=''):
  """An helper utility to flatten multiple layers of dict into one dict.

  For example, {'a': {'b': 'c'}} => {'a.b': 'c'}

  Args:
    data: The dict type data to be flattened.
    parent: A string to encode as key prefix for recursion.

  Returns:
    A flattened dict.
  """
  items = []
  for k, v in data.iteritems():
    new_key = JoinKeys(parent, k) if parent else k
    if isinstance(v, collections.Mapping):
      items.extend(FlattenData(v, new_key).items())
    else:
      items.append((new_key, v))
  return dict(items)


def LoadConfig(config_name=None):
  """Helper utility to load a JSON config that represents device data.

  Args:
    config_name: A string for name to be passed to config_utils.LoadConfig.

  Returns:
    A dictionary as device data (already flattened).
  """
  return FlattenData(
      config_utils.LoadConfig(config_name, schema_name='device_data'))