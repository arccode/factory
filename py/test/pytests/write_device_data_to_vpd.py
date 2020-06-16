# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Writes device data to VPD (Vital Product Data).

Description
-----------
Device Data (``cros.factory.test.device_data``) maintains the data during
manufacturing flow, and will be wiped when device goes to shipping mode (or
re-flashed for re-run of manufacturing flow).

To keep device data persistent, we may copy the values to VPD area, which is
inside the SPI flashrom where firmware lives on Chromebooks (other platforms
may implement VPD in other locations, for example Android may prefer to use
/persist partition).

By default, this test writes all device data under ``vpd`` category (for
example, ``vpd.ro.region`` to ``ro.region``), all device data under ``serial``
category (for example, ``serials.serial_number`` to ``serial_number``) and all
device data under ``factory`` category (for example, ``factory.end_SMT`` to
``factory.end_SMT``).
To write different values, specify the mapping in ``ro_key_map`` or
``rw_key_map``.

The ``ro_key_map`` is a mapping from RO VPD keys to device data keys. For
example::

  {'foo': 'bar.baz'}

This map indicates we have to read ``bar.baz`` from device data and write to
RO VPD by name ``foo``.

``rw_key_map`` works in similar way, except it's writing values to RW VPD.

Test Procedure
--------------
This is an automated test without user interaction.

Start the test and the specified device data values (or all under ``vpd.*``)
will be written to VPD using Device API.

Dependency
----------
This test relies on ``vpd`` component in Device API to access VPD.

Examples
--------
To write all VPD values from device data to VPD, add this in test list::

  {
    "pytest_name": "write_device_data_to_vpd"
  }

To write a calibration data value to RO VPD::

  {
    "pytest_name": "write_device_data_to_vpd",
    "args": {
      "ro_key_map": {
        "modem_calibration": "component.cellular.calibration_data"
      }
    }
  }
"""

from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg


class WriteDeviceDataToVPD(test_case.TestCase):
  ARGS = [
      Arg('ro_key_map', dict,
          'Mapping of (VPD_NAME, DEVICE_DATA_KEY) to write into RO VPD.',
          default=None),
      Arg('rw_key_map', dict,
          'Mapping of (VPD_NAME, DEVICE_DATA_KEY) to write into RW VPD.',
          default=None),
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    data = {
        'ro': {},
        'rw': {},
    }

    if self.args.ro_key_map is None and self.args.rw_key_map is None:
      data['ro'] = device_data.GetDeviceData(device_data.KEY_VPD_RO, {})
      data['rw'] = device_data.GetDeviceData(device_data.KEY_VPD_RW, {})
      # Device serial number is usually not included in vpd.ro.*.
      data['ro'].update(device_data.GetAllSerialNumbers())

      data['rw'].update(
          device_data.FlattenData({
              'factory': device_data.GetDeviceData(device_data.KEY_FACTORY, {})
          }))
    else:
      data['ro'] = {
          vpd_name: device_data.GetDeviceData(data_key)
          for vpd_name, data_key in (self.args.ro_key_map or {}).items()
      }
      data['rw'] = {
          vpd_name: device_data.GetDeviceData(data_key)
          for vpd_name, data_key in (self.args.rw_key_map or {}).items()
      }

    missing_keys = [k for section in data for k, v in data[section].items()
                    if v is None]
    if missing_keys:
      self.FailTask('Missing device data keys: %r' % sorted(missing_keys))

    for section, entries in data.items():
      self.ui.SetState(
          _('Writing device data to {vpd_section} VPD...',
            vpd_section=section.upper()))
      if not entries:
        continue
      # Normalize boolean and integer types to strings.
      output = {k: str(v) for k, v in entries.items()}
      vpd = getattr(self.dut.vpd, section)
      vpd.Update(output)
