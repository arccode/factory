# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from parser_base import ParserBase

class EventParser(ParserBase):
  '''The parser to create the Event table.

  TODO(waihong): Unit tests.
  '''
  def setup(self):
    super(EventParser, self).setup()
    schema_dict = {
      'device_id': 'TEXT',
      'time': 'TEXT',
      'preamble_time': 'TEXT',
      'event': 'TEXT',
      'event_seq': 'INTEGER',
      'preamble_seq': 'INTEGER',
      'boot_id': 'TEXT',
      'boot_sequence': 'INTEGER',
      'factory_md5sum': 'TEXT',
      'filename': 'TEXT',
      'image_id': 'TEXT',
      'log_id': 'TEXT',
    }
    self.setup_table('Event', schema_dict, primary_key=['device_id', 'time'])

  def handle_all(self, preamble, event):
    '''A handler for all event types.'''
    update_dict = {
      'device_id': preamble.get('device_id'),
      'time': event.get('TIME'),
      'preamble_time': preamble.get('TIME'),
      'event': event.get('EVENT'),
      'event_seq': int(event.get('SEQ')),
      'preamble_seq': int(preamble.get('SEQ')),
      'boot_id': preamble.get('boot_id'),
      'boot_sequence': int(preamble.get('boot_sequence')),
      'factory_md5sum': preamble.get('factory_md5sum'),
      'filename': preamble.get('filename'),
      'image_id': preamble.get('image_id'),
      'log_id': preamble.get('log_id'),
    }
    self.update_or_insert_row(update_dict)
