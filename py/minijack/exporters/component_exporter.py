# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.minijack import minijack
from cros.factory.minijack import model
from cros.factory.minijack.exporters import exporter_base

class ComponentExporter(exporter_base.ExporterBase):
  '''The exporter to create the Component table.

  TODO(waihong): Unit tests.
  '''
  def __init__(self, database):
    super(ComponentExporter, self).__init__(database)
    self._table = None

  def Setup(self):
    '''This method is called on Minijack start-up.'''
    super(ComponentExporter, self).Setup()
    self._table = self._database.GetOrCreateTable(model.Component)

  def Handle_probe(self, packet):
    '''A handler for a probe event.'''
    # Find the dict which contain the 'cpu' keyword. An event example like:
    #   probe_results:
    #     found_probe_value_map:
    #       battery: Battery
    #       cpu: Processor
    #       bluetooth: 0123:4567
    #       ...
    # We need to find all the components no matter the tree structure is
    # changed or the found_probe_value_map tag is renamed.
    keyword = 'cpu'
    parent = packet.FindAttrContainingKey(keyword)
    for component, symbolic in minijack.EventPacket.FlattenAttr(parent):
      row = model.Component(
        device_id = packet.preamble.get('device_id'),
        time      = packet.event.get('TIME'),
        component = component,
        symbolic  = symbolic,
      )
      self._table.UpdateOrInsertRow(row)
