# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

class ExporterBase(object):
  '''The base class of exporters.

  An exporter is a customized class which analyses event logs and dumps their
  knowledge into a database.

  All exporter classes should inherit this ExporterBase class and implement/reuse
  the following methods:
    Setup(self): This method is called on Minijack start-up.
    Handle_xxx(self, packet): This method is called when an event packet, with
        event id == 'xxx', is received. The argument packet is an EventPacket
        object which contains the dicts of the event preamble and the event
        content. An exporter class contains multiple Handle_xxx(). The
        Handle_all() is special, which is called on every event packet.
        This method doesn't follow the naming conversion as we want to keep
        xxx the same as the event name.

  Note that all the exporter module should be added into __init__.py. Otherwise,
  they are not loaded by default.

  Some naming conversions:
    module file name: xxx_exporter.py
    module name: xxx_exporter
    class name: XxxExporter

  TODO(waihong): Unit tests.

  Properties:
    _database: The database object of the database.
    _table: The table object.
  '''
  def __init__(self, database):
    self._database = database

  def Setup(self):
    '''This method is called on Minijack start-up.'''
    pass
