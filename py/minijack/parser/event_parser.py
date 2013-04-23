# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.minijack import model
from cros.factory.minijack.parser import parser_base

class EventParser(parser_base.ParserBase):
  '''The parser to create the Event table.

  TODO(waihong): Unit tests.
  '''
  def Setup(self):
    super(EventParser, self).Setup()
    self._table = self._database.GetOrCreateTable(model.Event)

  def Handle_all(self, preamble, event):
    '''A handler for all event types.'''
    row = model.Event(
      device_id      = preamble.get('device_id'),
      time           = event.get('TIME'),
      preamble_time  = preamble.get('TIME'),
      event          = event.get('EVENT'),
      event_seq      = int(event.get('SEQ')),
      preamble_seq   = int(preamble.get('SEQ')),
      boot_id        = preamble.get('boot_id'),
      boot_sequence  = int(preamble.get('boot_sequence')),
      factory_md5sum = preamble.get('factory_md5sum'),
      filename       = preamble.get('filename'),
      image_id       = preamble.get('image_id'),
      log_id         = preamble.get('log_id'),
    )
    self._table.UpdateOrInsertRow(row)
