# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

class ParserBase(object):
  '''The base class of parsers.

  An parser is a customized class which analyses event logs and converts
  the knowledge into a database.

  All parser classes should inherit this ParserBase class and implement/reuse
  the following methods:
    setup(self): This method is called on Minijack start-up.
    cleanup(self): This method is called on Minijack shut-down.
    handle_xxx(self, preamble, event): This method is called when an event,
        with event id == 'xxx', is received. The preamble and event arguments
        contain the Python dict of the preamble and the event. A parser class
        contains multiple handle_xxx(). The handle_all() is special, which is
        called on every event.

  Note that all the parser module should be added into __init__.py. Otherwise,
  they are not loaded by default.

  Some naming conversions:
    module file name: xxx_parser.py
    module name: xxx_parser
    class name: XxxParser

  Properties:
    _conn: The connection object of the database.
  '''
  def __init__(self, conn):
    self._conn = conn

  def setup(self):
    '''This method is called on Minijack start-up.'''
    pass

  def cleanup(self):
    '''This method is called on Minijack shut-down.'''
    pass
