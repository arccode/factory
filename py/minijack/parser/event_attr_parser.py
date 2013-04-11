# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

from parser_base import ParserBase

class EventAttrParser(ParserBase):
  '''The parser to create the Event and Attr table.

  TODO(waihong): Unit tests.
  '''
  def setup(self):
    super(EventAttrParser, self).setup()
    # TODO(waihong): Create the Event and Attr talbes if not exist.
    logging.debug('EventAttrParser is setup')

  def handle_all(self, preamble, event):
    '''A handler for all event types.'''
    # TODO(waihong): Parse the event and insert them to the database.
    logging.debug('EventAttrParser is invoked')
