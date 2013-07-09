# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""ChromeOS RMA shop floor system implementation.

This module provides an easy way to setup and use shop floor system for RMA.
It uses YAML files to store per-device information, indexed by RMA number.
The YAML file is created prior to reflashing the device and is used to restore
device-specific information prior to returning it to a customer. The YAML file
is deleted on finalize. If a device is badly damaged, it may not be possible
to extract data from its firmware. Shopfloor API calls for a device without
a matching YAML file return no data, rather than throwing an exception.

YAML file format:

Each device has a file: RMAxxxxxxxx.yaml (where the x's are replaced by the
RMA number).

Example:

!DeviceData
hwid: DEVICE BOMN-SUCH
serial_number: RMA12341234
vpd:
  ro: {initial_locale: en-US, initial_timezone: America/Los_Angeles,
       keyboard_layout: 'xkb:us::eng', serial_number: 2C063017607000163}
  rw: {gbind_attribute: <group code>, ubind_attribute: <user code>}

You may also add files named aux_*.csv; they will be parsed and their
values returned via GetAuxData.  In the header row of aux_*.csv,
column names may optionally be followed by contain a type (one of
bool, int, float, or str) in square brackets; this means values in that
column are parsed as that type.  For instance, if you have a file called
aux_mlb.csv with the following contents:

  id,foo[int],bar
  MLB001,123,baz
  MLB002,456,qux

then:

  GetAuxData('mlb', 'MLB001') == {'foo': 123, 'bar': 'baz'}
  GetAuxData('mlb', 'MLB002') == {'foo': 456, 'bar': 'qux'}

To use this module, run following command in shopfloor folder:
  shopfloor_server.sh -m simple_rma_shopfloor -d <PATH TO DATA DIR>

"""

import csv
import glob
import logging
import os
import re
import time
import threading
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory import shopfloor

# Set any required aux tables here
_REQUIRED_AUX_TABLES = []

# Set any required shopfloor device info fields here, this can be left blank
# for HWIDv2 implementations.
_DEVICE_INFO_FIELDS = ['component.antenna', 'component.camera',
                       'component.has_cellular', 'component.keyboard',
                       'component.pcb_vendor', 'region', 'serial_number', ]

# Set the below to a regex for validating your RMA numbers
_RMA_NUMBER_REGEX = r'^RMA[0-9]{8}$'

# Set the below to True if the RMA number should be accepted only if a
# corresponding YAML file exists, False bypasses the check.
_RMA_NUMBER_YAML_MUST_EXIST = True

def _synchronized(f):
  """
  Decorates a function to grab a lock.
  """
  def wrapped(self, *args, **kw):
    with self._lock: # pylint: disable=W0212
      return f(self, *args, **kw)
  return wrapped


class DeviceData(yaml.YAMLObject):
  yaml_tag = u'!DeviceData'
  def __init__(self, rma_number, vpd, hwid): # pylint: disable=W0231
    self.rma_number = rma_number
    self.vpd = vpd
    self.hwid = hwid

  def __repr__(self):
    return "%s(rma_number=%r, vpd=%r, hwid=%r)" % (
        self.__class__.__name__, self.rma_number, self.vpd, self.hwid)


class ShopFloor(shopfloor.ShopFloorBase):
  """RMA shop floor system, using per-device YAML files as input.

  Device data is read from '<serial_number>.yaml' files in the data directory.
  """
  NAME = "Simple RMA shopfloor."
  VERSION = 2

  def __init__(self):
    super(ShopFloor, self).__init__()
    self.aux_data = {}
    self.data_store = {}
    self._lock = threading.RLock() # Used to serialize shopfloor API calls.

  def Init(self):
    # Load AUX data files.
    for f in glob.glob(os.path.join(self.data_dir, '*.csv')):
      match = re.match('^aux_(\w+)\.csv',
                       os.path.basename(f))
      if not match:
        continue
      table_name = match.group(1)
      logging.info("Reading table %s from %s...", table_name, f)
      assert table_name not in self.aux_data
      self.aux_data[table_name] = LoadAuxCsvData(f)
      logging.info("Loaded %d entries from %s",
                   len(self.aux_data[table_name]), f)

    # Verify all required tables were loaded.
    for required_table in _REQUIRED_AUX_TABLES:
      assert required_table in self.aux_data, (
          "Required AUX table %s not found." % required_table)

    # Try to touch some files inside directory, to make sure the directory is
    # writable, and everything I/O system is working fine.
    stamp_file = os.path.join(self.data_dir, ".touch")
    with open(stamp_file, "w") as stamp_handle:
      stamp_handle.write("%s - VERSION %s" % (self.NAME, self.VERSION))
    os.remove(stamp_file)

  def _GetDataStoreValue(self, serial, key):
    """Returns data_store value matching key for serial or None."""
    self._LoadSerialNumber(serial)
    if serial not in self.data_store:
      logging.info('%s: No \'%s\' value found.', serial, key)
      return None
    value = self.data_store[serial][key]
    logging.info('%s: Fetched value for \'%s\': %s', serial, key, value)
    return value

  def _LoadSerialNumber(self, serial):
    """Loads a matching YAML file for a serial number into the data store.

    Does not reload data if it is already in the data store.
    """
    if serial in self.data_store:
      return
    data_path = os.path.join(self.data_dir, serial + ".yaml")
    if(os.path.exists(data_path)):
      device_data = LoadDeviceData(data_path)
      logging.info('%s: Loading device data.', serial)
      self.data_store[serial] = device_data
    else:
      logging.info('%s: No device data to load.', serial)

  @_synchronized
  def CheckSN(self, serial):
    """Validates whether a rma number is in the correct format.
    Note that for RMA we are using the RMA number as a device specific
    identifier, this is separate from the device's actual serial number
    stored in VPD, however to keep in line with the shopfloor server
    implementation, we call it the serial_number.

    Args:
      serial - RMA number of device.

    Returns:
      True - If the rma number matches the valid format.

    Raises:
      ValueError - If the rma number format is invalid.
    """
    if not re.match(_RMA_NUMBER_REGEX, serial):
      message = "Invalid RMA number: %s" % serial
      raise ValueError(message)
    if _RMA_NUMBER_YAML_MUST_EXIST:
      data_path = os.path.join(self.data_dir, serial + ".yaml")
      if not os.path.exists(data_path):
        message = "RMA YAML not found on shopfloor: %s" % serial
        raise ValueError(message)
    logging.info('Validated RMA number: %s', serial)
    return True

  @_synchronized
  def GetAuxData(self, table_name, id):  # pylint: disable=W0622
    """Fetches auxillary data table value for a given id.

    Args:
      table_name - Name of the auxillary table to fetch from.
      id - identifying string value to fetch value for.

    Returns:
      Value matching provided table and ID if found.

    Raises:
      KeyError - If either table_name or id are invalid.
    """
    try:
      value = self.aux_data[table_name][id]
      logging.info('Fetched %s aux data for %s: %s', table_name, id, value)
    except KeyError:
      raise KeyError, 'No %s data found for %s' % (table_name, id)
    return value

  @_synchronized
  def GetDeviceInfo(self, serial):
    """Fetches the device info for a device.
    Note that this is only used for HWIDv3 implementations.

    Args:
      serial - Serial number of device.

    Returns:
      A dictionary containing information about the expected
      configuration of the device.
    """
    return { key: self._GetDataStoreValue(serial, key)
             for key in _DEVICE_INFO_FIELDS }

  @_synchronized
  def GetHWID(self, serial):
    """Fetches the hardware ID (HWID) for a device.

    Args:
      serial - Serial number of device.

    Returns:
      HWID or None if data for the device can't be found.
    """
    return self._GetDataStoreValue(serial, 'hwid')

  @_synchronized
  def GetRegistrationCodeMap(self, serial):
    """Fetches registration codes for a device.

    Args:
      serial - Serial number of device.

    Returns:
      Registration code dictionary or {} if data for the device can't be found.
    """
    registration_code_map = self._GetDataStoreValue(
                                serial, 'registration_code_map')
    return registration_code_map or {}

  @_synchronized
  def GetVPD(self, serial):
    """Fetches VPD dict for a device.

    Args:
      serial - Serial number of device.

    Returns:
      vpd dictionary or None if data for the device can't be found.
    """
    return self._GetDataStoreValue(serial, 'vpd')

  @_synchronized
  def UploadReport(self, serial, report_blob, report_name=None):
    """Saves the factory log for a device.

    Args:
      serial - Serial number of device.
      report_blob - Report binary data. May be a shopfloor.Binary
                    or a gziped file.
      report_name - (optional) basename of the report file to save.
    """
    def is_gzip_blob(blob):
      """Check (not 100% accurate) if input blob is gzipped."""
      GZIP_MAGIC = '\x1f\x8b'
      return blob[:len(GZIP_MAGIC)] == GZIP_MAGIC

    if isinstance(report_blob, shopfloor.Binary):
      report_blob = report_blob.data
    if not report_name:
      report_name = ('%s-%s.rpt' % (re.sub('[^a-zA-Z0-9]', '', serial),
                                    time.strftime("%Y%m%d-%H%M%S%z")))
      if is_gzip_blob(report_blob):
        report_name += ".gz"
    self.SaveReport(report_name, report_blob)
    logging.info("%s: Saved report", serial)

  @_synchronized
  def Finalize(self, serial):
    """Removes the data store entry and yaml file for a device.

    Args:
      serial - Serial number of device.
    """
    data_path = os.path.join(self.data_dir, serial + ".yaml")
    if(os.path.exists(data_path)):
      os.remove(data_path)
      logging.info("%s: Removed yaml file: %s", serial, data_path)
    logging.info("%s: Finalized", serial)

  @_synchronized
  def SaveDeviceData(self, data, overwrite):
    """Save device data in YAML format.

    Args:
      data - DeviceData. Device data to save.
      overwrite - Bool. Whether to replace any existing device data.

    Returns:
      dict with the following fields:
        status: String with either 'success' or 'conflict'.
        data: (optional) existing device data if there is a conflict.
    """
    filename = '%s.yaml' % data['serial_number']
    filepath = os.path.join(self.data_dir, filename)
    if os.path.isfile(filepath) and not overwrite:
      with open(filepath, 'rb') as yaml_file:
        existing_device_data = yaml.load(yaml_file)
      return {'status': 'conflict', 'data': existing_device_data}
    device_data = DeviceData(data['serial_number'], data['vpd'], data['hwid'])
    with open(filepath, 'w') as yaml_file:
      yaml.dump(device_data, yaml_file)
    return {'status': 'success'}


def LoadDeviceData(filename):
  """Loads a YAML file and returns structured shop floor system data.

  Args:
    filename - string. Full path to yaml file to load.

  Returns:
    dict with the following fields:
      hwid - string. Device hardware ID
      vpd - dict of dicts containing 'ro' and 'rw' VPD data.
      registration_code_map - dict containing 'user' and 'group' codes.
      any additional _DEVICE_INFO_FIELDS values
  """
  with open(filename, 'rb') as yaml_file:
    device_data = yaml.load(yaml_file)

  #TODO(dparker): Use DeviceData objects directly instead of remapping them.
  vpd = device_data.vpd.copy()
  registration_code_map = {'user': vpd['rw']['ubind_attribute'],
                           'group': vpd['rw']['gbind_attribute']}
  del vpd['rw']['ubind_attribute']
  del vpd['rw']['gbind_attribute']
  entry = {'hwid': device_data.hwid,
           'vpd': vpd,
           'registration_code_map': registration_code_map}
  for key in _DEVICE_INFO_FIELDS:
    entry[key] = getattr(device_data, key)
  return entry


def LoadAuxCsvData(csv_file):
  """Parses an aux_*.csv CSV file.  See file docstring for syntax.

  Args:
    csv_file: Path to the file.

  Returns:
    A map. Each item's key is the ID of a row, and the value is a map
    of all columns in the row.

  Raises:
    ValueError if the CSV is not semantically valid.
    Other exceptions as raised by csv.reader.
  """
  def ParseBoolean(value):
    if value in ['0', 'false', 'False']:
      return False
    if value in ['1', 'true', 'True']:
      return True
    raise ValueError('%r is not a Boolean value' % value)

  data = {}

  with open(csv_file, 'rb') as source:
    reader = csv.reader(source)
    headers = reader.next()

    # A list of tuples (name, parser), where parser is a function that
    # can be used to parse the column (e.g., the str or int builtins).
    cols = []
    # Set of all column names, for duplicate detection.
    col_name_set = set()
    # Matches 'foo' or 'foo[int]'.
    HEADER_REGEXP = re.compile('^(\w+)(?:\[(\w+)\])?$')
    PARSERS = {
        'str': str,
        'bool': ParseBoolean,
        'int': int,
        'float': float
        }
    for header in headers:
      match = HEADER_REGEXP.match(header)
      if not match:
        raise ValueError("In %s, header %r does not match regexp %s"
                         % (csv_file, header, HEADER_REGEXP.pattern))

      col_name, col_type = match.groups()
      if col_type:
        parser = PARSERS.get(col_type)
        if not parser:
          raise ValueError("In %s, header %r has unknown type %r"
                           " (should be one of %r)"
                           % (csv_file, col_name, col_type,
                              sorted(PARSERS.keys())))
      else:
        # No type; default to string.
        parser = str
      cols.append((col_name, parser))

      if col_name in col_name_set:
        raise ValueError("In %s, more than one column named %r"
                         % (csv_file, col_name))
      col_name_set.add(col_name)

    # Use the first column as the ID column.
    id_column_name = cols[0][0]

    row_number = 1
    for row in reader:
      row_number += 1
      if len(row) != len(cols):
        raise ValueError("In %s:%d, expected %d columns but got %d",
                         csv_file, row_number, len(headers), len(row))
      row_data = {}

      for value, col in zip(row, cols):
        try:
          row_data[col[0]] = col[1](value)
        except ValueError as e:
          # Re-raise with row number and column name
          raise ValueError("In %s:%d.%s, %s" %
                           (csv_file, row_number, col[0], e))

      row_id = row_data.get(id_column_name)
      if row_id in data:
        raise ValueError("In %s:%d, duplicate ID %r" %
                         (csv_file, row_number, row_id))
      data[row_id] = row_data

  return data
