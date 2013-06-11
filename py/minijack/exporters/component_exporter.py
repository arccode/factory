# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.datatypes import EventPacket
from cros.factory.minijack.exporters.base import ExporterBase
from cros.factory.minijack.models import Component, ComponentDetail


COMPONENT_KEYWORD = 'cpu'


class ComponentExporter(ExporterBase):
  """The exporter to create the Component and ComponentDetail table.

  TODO(waihong): Unit tests.
  """
  def Setup(self):
    """This method is called on Minijack start-up."""
    super(ComponentExporter, self).Setup()
    self._database.GetOrCreateTable(Component)
    self._database.GetOrCreateTable(ComponentDetail)

  def Handle_hwid(self, packet):
    """A handler for a hwid event."""
    # Find the dict which contain the COMPONENT_KEYWORD. No matter the tree
    # structure changes, we can still get the component details. For example:
    # components:
    #   antenna:
    #   - foo: null
    #   cpu:
    #   - bar:
    #       cores:
    #         is_re: false
    #         raw_value: '2'
    #       model_name:
    #         is_re: false
    #         raw_value: Bar-123
    components = packet.FindAttrContainingKey(COMPONENT_KEYWORD)
    for comp_class, comps in components.iteritems():
      row = Component(
        device_id       = packet.preamble.get('device_id'),
        component_class = comp_class,
        # Flatten the symbolic names by joining them together.
        # Only one key-value pair in the dict.
        component_name  = ','.join([c.keys()[0] for c in comps]),
      )
      self._database.UpdateOrInsert(row)

  def Handle_probe(self, packet):
    """A handler for a probe event."""
    # Find the dict which contain the COMPONENT_KEYWORD. An event example like:
    #   probe_results:
    #     found_probe_value_map:
    #       battery:
    #         compact_str: Foo-ABC
    #       cpu:
    #         compact_str: Bar-123 [2 cores]
    #         cores: '2'
    #         model: Bar-123
    #       ...
    # We need to find all the components no matter the tree structure is
    # changed or the found_probe_value_map tag is renamed.
    parent = packet.FindAttrContainingKey(COMPONENT_KEYWORD)
    for comp_class, comp_detail in parent.iteritems():
      for field_name, field_value in EventPacket.FlattenAttr(comp_detail):
        row = ComponentDetail(
          device_id = packet.preamble.get('device_id'),
          component_class = comp_class,
          field_name  = field_name,
          field_value  = field_value,
        )
        self._database.UpdateOrInsert(row)
