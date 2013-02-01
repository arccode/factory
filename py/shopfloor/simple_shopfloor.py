# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""ChromeOS factory shop floor system implementation, using CSV input.

This module provides an easy way to setup and use shop floor system. Use Google
Docs or Excel to create a spreadsheet and export as CSV (comma separated
values), called devices.csv, with the following fields:

  serial_number: The serial number of each device.
  hwid: The HWID string assigned for each serial number.
  ro_vpd_*: Read-only VPD values. Example: ro_vpd_test_data will be converted to
            "test_data" in RO_VPD section.
  rw_vpd_*: Read-writeable VPD values, using same syntax described in ro_vpd_*.

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

To use this module, run following command in factory_setup folder:
  shopfloor_server.py -m shopfloor.simple.ShopFloor -c PATH_TO_CSV_FILE.csv

You can find sample CSV files in:
  factory_setup/test_data/shopfloor/simple.csv
  factory_setup/test_data/shopfloor/aux_mlb.csv
"""

import csv
import glob
import logging
import os
import re
import time

import factory_common  # pylint: disable=W0611
from cros.factory import shopfloor


class ShopFloor(shopfloor.ShopFloorBase):
  """Sample shop floor system, using CSV file as input.

  Device data is read from a 'devices.csv' file in the data directory.
  """
  NAME = "CSV-file based shop floor system"
  VERSION = 4

  def __init__(self):
    super(ShopFloor, self).__init__()
    self.data_store = None
    self.aux_data = {}

  def Init(self):
    devices_csv = os.path.join(self.data_dir, 'devices.csv')
    logging.info("Parsing %s...", devices_csv)
    self.data_store = LoadCsvData(devices_csv)
    logging.info("Loaded %d entries from %s.",
                 len(self.data_store), devices_csv)

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

    # Try to touch some files inside directory, to make sure the directory is
    # writable, and everything I/O system is working fine.
    stamp_file = os.path.join(self.data_dir, ".touch")
    with open(stamp_file, "w") as stamp_handle:
      stamp_handle.write("%s - VERSION %s" % (self.NAME, self.VERSION))
    os.remove(stamp_file)

  def _CheckSerialNumber(self, serial):
    """Checks if serial number is valid, otherwise raise ValueError."""
    if serial in self.data_store:
      return True
    message = "Unknown serial number: %s" % serial
    logging.error(message)
    raise ValueError(message)

  def CheckSN(self, serial):
    return self._CheckSerialNumber(serial)

  def GetHWID(self, serial):
    self._CheckSerialNumber(serial)
    return self.data_store[serial]['hwid']

  def GetVPD(self, serial):
    self._CheckSerialNumber(serial)
    return self.data_store[serial]['vpd']

  def GetAuxData(self, table_name, id):  # pylint: disable=W0622
    return self.aux_data[table_name][id]

  def GetRegistrationCodeMap(self, serial):
    self._CheckSerialNumber(serial)
    registration_code_map = self.data_store[serial]['registration_code_map']
    self.LogRegistrationCodeMap(self.data_store[serial]['hwid'],
                                registration_code_map)
    return registration_code_map

  def UploadReport(self, serial, report_blob, report_name=None):
    def is_gzip_blob(blob):
      """Check (not 100% accurate) if input blob is gzipped."""
      GZIP_MAGIC = '\x1f\x8b'
      return blob[:len(GZIP_MAGIC)] == GZIP_MAGIC

    self._CheckSerialNumber(serial)
    if isinstance(report_blob, shopfloor.Binary):
      report_blob = report_blob.data
    if not report_name:
      report_name = ('%s-%s.rpt' % (re.sub('[^a-zA-Z0-9]', '', serial),
                                    time.strftime("%Y%m%d-%H%M%S%z")))
      if is_gzip_blob(report_blob):
        report_name += ".gz"
    self.SaveReport(report_name, report_blob)

  def Finalize(self, serial):
    # Finalize is currently not implemented.
    self._CheckSerialNumber(serial)
    logging.info("Finalized: %s", serial)


def LoadCsvData(filename):
  """Loads a CSV file and returns structured shop floor system data."""
  # Required fields.
  KEY_SERIAL_NUMBER = 'serial_number'
  KEY_HWID = 'hwid'
  KEY_REGISTRATION_CODE_USER = 'registration_code_user'
  KEY_REGISTRATION_CODE_GROUP = 'registration_code_group'

  # Optional fields.
  PREFIX_RO_VPD = 'ro_vpd_'
  PREFIX_RW_VPD = 'rw_vpd_'
  VPD_PREFIXES = (PREFIX_RO_VPD, PREFIX_RW_VPD)

  REQUIRED_KEYS = (KEY_SERIAL_NUMBER, KEY_HWID)
  OPTIONAL_KEYS = (KEY_REGISTRATION_CODE_USER, KEY_REGISTRATION_CODE_GROUP)
  OPTIONAL_PREFIXES = VPD_PREFIXES

  def check_field_name(name):
    """Checks if argument is an valid input name."""
    if name in REQUIRED_KEYS or name in OPTIONAL_KEYS:
      return True
    for prefix in OPTIONAL_PREFIXES:
      if name.startswith(prefix):
        return True
    return False

  def build_vpd(source):
    """Builds VPD structure by input source."""
    vpd = {'ro': {}, 'rw': {}}
    for key, value in source.items():
      for prefix in VPD_PREFIXES:
        if not key.startswith(prefix):
          continue
        # Key format: $type_vpd_$name (ex, ro_vpd_serial_number)
        (key_type, _, key_name) = key.split('_', 2)
        if value is None:
          continue
        vpd[key_type][key_name.strip()] = value.strip()
    return vpd

  def build_registration_code_map(source):
    """Builds registration_code_map structure.

    Returns:
      A dict containing 'user' and 'group' keys.
    """
    return {'user': source.get(KEY_REGISTRATION_CODE_USER),
            'group': source.get(KEY_REGISTRATION_CODE_GROUP)}

  data = {}
  with open(filename, 'rb') as source:
    reader = csv.DictReader(source)
    row_number = 0
    for row in reader:
      row_number += 1
      if KEY_SERIAL_NUMBER not in row:
        raise ValueError("Missing %s in row %d" % (KEY_SERIAL_NUMBER,
                                                   row_number))
      serial_number = row[KEY_SERIAL_NUMBER].strip()
      hwid = row[KEY_HWID].strip()

      # Checks data validity.
      if serial_number in data:
        raise ValueError("Duplicated %s in row %d: %s" %
                         (KEY_SERIAL_NUMBER, row_number, serial_number))
      if None in row:
        raise ValueError("Extra fields in row %d: %s" %
                         (row_number, ','.join(row[None])))
      for field in row:
        if not check_field_name(field):
          raise ValueError("Invalid field: %s" % field)

      entry = {'hwid': hwid,
               'vpd': build_vpd(row),
               'registration_code_map': build_registration_code_map(row)}
      data[serial_number] = entry
  return data


def LoadAuxCsvData(csv_file):
  '''Parses an aux_*.csv CSV file.  See file docstring for syntax.

  Args:
    csv_file: Path to the file.

  Returns:
    A map. Each item's key is the ID of a row, and the value is a map
    of all columns in the row.

  Raises:
    ValueError if the CSV is not semantically valid.
    Other exceptions as raised by csv.reader.
  '''
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
