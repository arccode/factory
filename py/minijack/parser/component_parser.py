# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from parser_base import ParserBase
from parser_base import FindContainingDictForKey, FlattenAttr

class ComponentParser(ParserBase):
  '''The parser to create the Component table.

  TODO(waihong): Unit tests.
  '''
  def Setup(self):
    '''This method is called on Minijack start-up.'''
    super(ComponentParser, self).Setup()
    schema_dict = {
      'device_id': 'TEXT',
      'time': 'TEXT',
      'class': 'TEXT',
      'symbolic': 'TEXT',
    }
    self.SetupTable('Component', schema_dict,
                     primary_key=['device_id', 'time', 'class'])

  def Handle_probe(self, preamble, event):
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
    parent = FindContainingDictForKey(event, keyword)
    for comp_class, comp_symbolic in FlattenAttr(parent):
      update_dict = {
        'device_id': preamble.get('device_id'),
        'time': event.get('TIME'),
        'class': comp_class,
        'symbolic': comp_symbolic,
      }
      self.UpdateOrInsertRow(update_dict)
