# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from parser_base import ParserBase

class TestParser(ParserBase):
  '''The parser to create the Test table.

  TODO(waihong): Unit tests.
  '''
  def setup(self):
    '''This method is called on Minijack start-up.'''
    super(TestParser, self).setup()
    schema_dict = {
      'invocation': 'TEXT',
      'device_id': 'TEXT',
      'factory_md5sum': 'TEXT',
      'image_id': 'TEXT',
      'path': 'TEXT',
      'pytest_name': 'TEXT',
      'status': 'TEXT',
      # We store time in TEXT as sqlite3 does not support milliseconds.
      # Without milliseconds, we can't use time as key when joinning tables.
      'start_time': 'TEXT',
      'end_time': 'TEXT',
      'duration': 'REAL',
      'dargs': 'TEXT',
    }
    self.setup_table('Test', schema_dict, primary_key='invocation')

  def handle_start_test(self, preamble, event):
    '''A handler for a start_test event.'''
    update_dict = {
      'invocation': event.get('invocation'),
      'device_id': preamble.get('device_id'),
      'factory_md5sum': preamble.get('factory_md5sum'),
      'image_id': preamble.get('image_id'),
      'path': event.get('path'),
      'pytest_name': event.get('pytest_name'),
      'start_time': event.get('TIME'),
    }
    self.update_or_insert_row(update_dict)

  def handle_end_test(self, preamble, event):
    '''A handler for an end_test event.'''
    update_dict = {
      'invocation': event.get('invocation'),
      'device_id': preamble.get('device_id'),
      'factory_md5sum': preamble.get('factory_md5sum'),
      'image_id': preamble.get('image_id'),
      'path': event.get('path'),
      'pytest_name': event.get('pytest_name'),
      'status': event.get('status'),
      'end_time': event.get('TIME'),
      'duration': event.get('duration'),
      'dargs': event.get('dargs'),
    }
    self.update_or_insert_row(update_dict)
