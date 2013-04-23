# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.minijack import model
from cros.factory.minijack.parser import parser_base

class DeviceParser(parser_base.ParserBase):
  '''The parser to create the Device table.

  TODO(waihong): Unit tests.
  '''
  def Setup(self):
    '''This method is called on Minijack start-up.'''
    super(DeviceParser, self).Setup()
    self._table = self._database.GetOrCreateTable(model.Device)

  def Handle_goofy_init(self, preamble, event):
    '''A handler for a goofy_init event.'''
    if self._DoesFieldExist(preamble, event, 'goofy_init_time', newer=False):
      # Skip updating if the goofy_init_time is already in the table and the
      # goofy_init_time is older then this one.
      return
    row = model.Device(
      device_id       = preamble.get('device_id'),
      goofy_init_time = event.get('TIME'),
    )
    self._table.UpdateOrInsertRow(row)

  def Handle_update_device_data(self, preamble, event):
    '''A handler for a update_device_data event.'''
    if self._DoesFieldExist(preamble, event, 'serial_time'):
      return
    row = model.Device(
      device_id   = preamble.get('device_id'),
      serial      = event['data'].get('serial_number'),
      serial_time = event.get('TIME'),
    )
    self._table.UpdateOrInsertRow(row)

  def Handle_scan(self, preamble, event):
    '''A handler for a scan event.'''
    # If not a barcode scan of the MLB serial number, skip it.
    if event.get('key') != 'mlb_serial_number':
      return
    if self._DoesFieldExist(preamble, event, 'mlb_serial_time'):
      return
    row = model.Device(
      device_id       = preamble.get('device_id'),
      mlb_serial      = event.get('value'),
      mlb_serial_time = event.get('TIME'),
    )
    self._table.UpdateOrInsertRow(row)

  def Handle_hwid(self, preamble, event):
    '''A handler for a hwid event.'''
    if self._DoesFieldExist(preamble, event, 'hwid_time'):
      return
    row = model.Device(
      device_id = preamble.get('device_id'),
      hwid      = event.get('hwid'),
      hwid_time = event.get('TIME'),
    )
    self._table.UpdateOrInsertRow(row)

  def Handle_verified_hwid(self, preamble, event):
    '''A handler for a verified_hwid event.'''
    self.Handle_hwid(preamble, event)

  # TODO(waihong): Fill the ip field.

  def _DoesFieldExist(self, preamble, event, field, newer=True):
    '''Checks if a given field already in the table and it is newer (older).

    Args:
      preamble: A dict of preamble.
      event: A dict of event.
      field: A string of field name. The field contains timestamps.
      newer: True to check for newer; otherwise, check for older.

    Returns:
      True if the field exists and is newer (older); otherwise, False.
    '''
    time = event.get('TIME')
    condition = model.Device(device_id=preamble.get('device_id'))
    row = self._table.GetOneRow(condition)
    if row:
      return (getattr(row, field) >= time if newer else
              getattr(row, field) <= time)
    else:
      return False
