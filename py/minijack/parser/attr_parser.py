# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.minijack import model
from cros.factory.minijack.parser import parser_base

class AttrParser(parser_base.ParserBase):
  '''The parser to create the Attr table.

  TODO(waihong): Unit tests.
  '''
  def Setup(self):
    super(AttrParser, self).Setup()
    self._table = self._database.GetOrCreateTable(model.Attr)

  def Handle_all(self, preamble, event):
    '''A handler for all event types.'''
    RESERVED_PATH = ('EVENT', 'SEQ', 'TIME')
    # As the event is a tree struct which contains dicts or lists,
    # we flatten it first. The hierarchy is recorded in the Attr column.
    for path, val in parser_base.FlattenAttr(event):
      if path not in RESERVED_PATH:
        row = model.Attr(
          device_id = preamble.get('device_id'),
          time      = event.get('TIME'),
          attr      = path,
          value     = str(val),
        )
        self._table.UpdateOrInsertRow(row)
