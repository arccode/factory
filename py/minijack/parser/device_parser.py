# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from parser_base import ParserBase

class DeviceParser(ParserBase):
  '''The parser to create the Device table.

  TODO(waihong): Unit tests.
  '''
  def setup(self):
    '''This method is called on Minijack start-up.'''
    super(DeviceParser, self).setup()
    schema_dict = {
      'device_id': 'TEXT',
      'goofy_init_time': 'TEXT',  # the first time of getting goofy_init event
      'serial': 'TEXT',
      'serial_time': 'TEXT',
      'mlb_serial': 'TEXT',
      'mlb_serial_time': 'TEXT',
      'hwid': 'TEXT',
      'hwid_time': 'TEXT',
      'ip': 'TEXT',
    }
    self.setup_table('Device', schema_dict, primary_key='device_id')

  def handle_goofy_init(self, preamble, event):
    '''A handler for a goofy_init event.'''
    if self._does_column_exist(preamble, event, 'goofy_init_time', newer=False):
      # Skip updating if the goofy_init_time is already in the table and the
      # goofy_init_time is older then this one.
      return
    update_dict = {
      'device_id': preamble.get('device_id'),
      'goofy_init_time': event.get('TIME'),
    }
    self.update_or_insert_row(update_dict)

  def handle_update_device_data(self, preamble, event):
    '''A handler for a update_device_data event.'''
    if self._does_column_exist(preamble, event, 'serial_time'):
      return
    update_dict = {
      'device_id': preamble.get('device_id'),
      'serial': event['data'].get('serial_number'),
      'serial_time': event.get('TIME'),
    }
    self.update_or_insert_row(update_dict)

  def handle_scan(self, preamble, event):
    '''A handler for a scan event.'''
    # If not a barcode scan of the MLB serial number, skip it.
    if event.get('key') != 'mlb_serial_number':
      return
    if self._does_column_exist(preamble, event, 'mlb_serial_time'):
      return
    update_dict = {
      'device_id': preamble.get('device_id'),
      'mlb_serial': event.get('value'),
      'mlb_serial_time': event.get('TIME'),
    }
    self.update_or_insert_row(update_dict)

  def handle_hwid(self, preamble, event):
    '''A handler for a hwid event.'''
    if self._does_column_exist(preamble, event, 'hwid_time'):
      return
    update_dict = {
      'device_id': preamble.get('device_id'),
      'hwid': event.get('hwid'),
      'hwid_time': event.get('TIME'),
    }
    self.update_or_insert_row(update_dict)

  def handle_verified_hwid(self, preamble, event):
    '''A handler for a verified_hwid event.'''
    self.handle_hwid(preamble, event)

  # TODO(waihong): Fill the ip column.

  def _does_column_exist(self, preamble, event, column, newer=True):
    '''Checks if a given column already in the table and it is newer (older).

    Args:
      preamble: A dict of preamble.
      event: A dict of event.
      column: A string of column name. The column contains timestamps.
      newer: True to check for newer; otherwise, check for older.

    Returns:
      True if the column exists and is newer (older); otherwise, False.
    '''
    time = event.get('TIME')
    cond_dict = {'device_id': preamble.get('device_id')}
    row = self.get_one_row(cond_dict, [column])
    if row:
      return row[0] >= time if newer else row[0] <= time
    else:
      return False
