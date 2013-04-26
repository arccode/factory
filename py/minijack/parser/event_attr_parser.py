# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

import factory_common  # pylint: disable=W0611
from cros.factory.minijack import db
from cros.factory.minijack import model
from cros.factory.minijack.parser import parser_base

class EventAttrParser(parser_base.ParserBase):
  '''The parser to create the Event and Attr tables.

  TODO(waihong): Unit tests.
  '''
  def __init__(self, database):
    super(EventAttrParser, self).__init__(database)
    self._event_table = None
    self._attr_table = None

  def Setup(self):
    super(EventAttrParser, self).Setup()
    self._event_table = self._database.GetOrCreateTable(model.Event)
    self._attr_table = self._database.GetOrCreateTable(model.Attr)

  def Handle_all(self, preamble, event):
    '''A handler for all event types.'''
    # Just insert the row for speed-up. May raises an exception if the row
    # already exists.
    try:
      # Insert to Event first. If it finds duplication, skips Attr insertion.
      self._InsertEvent(preamble, event)
      self._InsertAttr(preamble, event)
    except db.IntegrityError:
      logging.warn('The Event/Attr (%s, %s) already exists in the table',
                   preamble.get('device_id'), event.get('TIME'))

  def _InsertEvent(self, preamble, event):
    '''Retrieves event information and inserts to Event table'''
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
    self._event_table.InsertRow(row)

  def _InsertAttr(self, preamble, event):
    '''Retrieves attr information and inserts to Attr table'''
    RESERVED_PATH = ('EVENT', 'SEQ', 'TIME')
    rows = []
    # As the event is a tree struct which contains dicts or lists,
    # we flatten it first. The hierarchy is recorded in the Attr column.
    for attr, value in parser_base.FlattenAttr(event):
      if attr not in RESERVED_PATH:
        row = model.Attr(
          device_id = preamble.get('device_id'),
          time      = event.get('TIME'),
          attr      = attr,
          value     = str(value),
        )
        rows.append(row)
    if rows:
      self._attr_table.InsertRows(rows)
