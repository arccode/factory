# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from parser_base import ParserBase
from parser_base import flatten_attr

class AttrParser(ParserBase):
  '''The parser to create the Attr table.

  TODO(waihong): Unit tests.
  '''
  def setup(self):
    super(AttrParser, self).setup()
    schema_dict = {
      'device_id': 'TEXT',
      'time': 'TEXT',
      'attr': 'TEXT',
      'value': 'BLOB',
    }
    self.setup_table('Attr', schema_dict,
                     primary_key=['device_id', 'time', 'attr'])

  def handle_all(self, preamble, event):
    '''A handler for all event types.'''
    RESERVED_PATH = ('EVENT', 'SEQ', 'TIME')
    # As the event is a tree struct which contains dicts or lists,
    # we flatten it first. The hierarchy is recorded in the Attr column.
    for path, val in flatten_attr(event):
      if path not in RESERVED_PATH:
        update_dict = {
          'device_id': preamble.get('device_id'),
          'time': event.get('TIME'),
          'attr': path,
          'value': val,
        }
        self.update_or_insert_row(update_dict)
