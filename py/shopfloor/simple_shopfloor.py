# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""ChromeOS factory shop floor system implementation, using CSV input.

This module provides an easy way to setup and use shop floor system. Use Google
Docs or Excel to create a spreadsheet and export as CSV (comma separated
values), with following fields:

  serial_number: The serial number of each device.
  hwid: The HWID string assigned for each serial number.
  ro_vpd_*: Read-only VPD values. Example: ro_vpd_test_data will be converted to
            "test_data" in RO_VPD section.
  rw_vpd_*: Read-writeable VPD values, using same syntax described in ro_vpd_*.

To use this module, run following command in factory_setup folder:
  shopfloor_server.py -m shopfloor.simple.ShopFloor -c PATH_TO_CSV_FILE.csv

You can find a sample CSV file in in:
  factory_setup/test_data/shopfloor/simple.csv
"""

import csv
import logging
import os
import re
import time

from xmlrpclib import Binary

import factory_common
from cros.factory import shopfloor


class ShopFloor(shopfloor.ShopFloorBase):
  """Sample shop floor system, using CSV file as input.

  Device data is read from a 'devices.csv' file in the data directory.
  """
  NAME = "CSV-file based shop floor system"
  VERSION = 4

  def Init(self):
    devices_csv = os.path.join(self.data_dir, 'devices.csv')
    logging.info("Parsing %s...", devices_csv)
    self.data_store = LoadCsvData(devices_csv)
    logging.info("Loaded %d entries from %s.",
                 len(self.data_store), devices_csv)

    # Put uploaded reports in a "reports" folder inside data_dir.
    self.reports_dir = os.path.join(self.data_dir, 'reports')
    if not os.path.isdir(self.reports_dir):
      os.mkdir(self.reports_dir)

    # Try to touch some files inside directory, to make sure the directory is
    # writable, and everything I/O system is working fine.
    stamp_file = os.path.join(self.reports_dir, ".touch")
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

  def GetHWID(self, serial):
    self._CheckSerialNumber(serial)
    return self.data_store[serial]['hwid']

  def GetVPD(self, serial):
    self._CheckSerialNumber(serial)
    return self.data_store[serial]['vpd']

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
    report_path = os.path.join(self.reports_dir, report_name)
    with open(report_path, "wb") as report_obj:
      report_obj.write(report_blob)

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
