# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.minijack import model
from cros.factory.minijack.exporters import exporter_base

class DeviceExporter(exporter_base.ExporterBase):
  '''The exporter to create the Device table.

  TODO(waihong): Unit tests.
  '''
  def __init__(self, database):
    super(DeviceExporter, self).__init__(database)
    self._table = None

  def Setup(self):
    '''This method is called on Minijack start-up.'''
    super(DeviceExporter, self).Setup()
    self._table = self._database.GetOrCreateTable(model.Device)

  def Handle_goofy_init(self, packet):
    '''A handler for a goofy_init event.'''
    if self._DoesFieldExist(packet, 'goofy_init_time', newer=False):
      # Skip updating if the goofy_init_time is already in the table and the
      # goofy_init_time is older then this one.
      return
    row = model.Device(
      device_id       = packet.preamble.get('device_id'),
      goofy_init_time = packet.event.get('TIME'),
    )
    self._table.UpdateOrInsertRow(row)

  def Handle_update_device_data(self, packet):
    '''A handler for a update_device_data event.'''
    if self._DoesFieldExist(packet, 'serial_time'):
      return
    row = model.Device(
      device_id   = packet.preamble.get('device_id'),
      serial      = packet.event.get('data').get('serial_number'),
      serial_time = packet.event.get('TIME'),
    )
    self._table.UpdateOrInsertRow(row)

  def Handle_scan(self, packet):
    '''A handler for a scan event.'''
    # If not a barcode scan of the MLB serial number, skip it.
    if packet.event.get('key') != 'mlb_serial_number':
      return
    if self._DoesFieldExist(packet, 'mlb_serial_time'):
      return
    row = model.Device(
      device_id       = packet.preamble.get('device_id'),
      mlb_serial      = packet.event.get('value'),
      mlb_serial_time = packet.event.get('TIME'),
    )
    self._table.UpdateOrInsertRow(row)

  def Handle_hwid(self, packet):
    '''A handler for a hwid event.'''
    if self._DoesFieldExist(packet, 'hwid_time'):
      return
    row = model.Device(
      device_id = packet.preamble.get('device_id'),
      hwid      = packet.event.get('hwid'),
      hwid_time = packet.event.get('TIME'),
    )
    self._table.UpdateOrInsertRow(row)

  def Handle_verified_hwid(self, packet):
    '''A handler for a verified_hwid event.'''
    self.Handle_hwid(packet)

  # TODO(waihong): Fill the ip field.

  def _DoesFieldExist(self, packet, field, newer=True):
    '''Checks if a given field already in the table and it is newer (older).

    Args:
      packet: An EventPacket object.
      field: A string of field name. The field contains timestamps.
      newer: True to check for newer; otherwise, check for older.

    Returns:
      True if the field exists and is newer (older); otherwise, False.
    '''
    time = packet.event.get('TIME')
    condition = model.Device(device_id=packet.preamble.get('device_id'))
    row = self._table.GetOneRow(condition)
    if row:
      return (getattr(row, field) >= time if newer else
              getattr(row, field) <= time)
    else:
      return False
