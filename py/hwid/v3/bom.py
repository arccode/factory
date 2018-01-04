# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""BOM class for the HWID v3 framework.

A BOM object mainly records what exact components are installed on the
Chromebook, while a HWID database records what components are allowed to be
installed on the Chromebook and their corresponding index.

There are two use cases of the BOM class:
  1. Generate a BOM object by probing the device, and then we can encode the BOM
     object to a HWID identity according to the HWID database.
  2. Decode a given HWID identity into a BOM object according to the HWID
     database.

The above two use cases can be written to a more simple form (in LaTeX syntax):
  1. identity = Encode_{database}(bom)
  2. bom = Decode_{database}(identity)

Above two formulas are implemented in `transformer.py`.
"""

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import type_utils


class BOM(object):
  """A class that holds all the information regarding a BOM.

  This class is for HWID v3 framework internal use only.  It does not verify
  anything because its properties are not given from external resources.

  Properties:
    encoding_pattern_index: An int indicating the encoding pattern.
    image_id: An int indicating the image id.
    components: A dict that maps component classes to a set of string of
        component name.
  """

  def __init__(self, encoding_pattern_index, image_id, components):
    self.encoding_pattern_index = encoding_pattern_index
    self.image_id = image_id
    self.components = {}

    for comp_cls, comp_names in components.iteritems():
      self.SetComponent(comp_cls, comp_names)

  def SetComponent(self, comp_cls, comp_names):
    self.components[comp_cls] = sorted(type_utils.MakeList(comp_names))

  def RemoveComponent(self, comp_cls):
    del self.components[comp_cls]

  def __eq__(self, op2):
    if not isinstance(op2, BOM):
      return False
    return self.__dict__ == op2.__dict__

  def __ne__(self, op2):
    return not self.__eq__(op2)

  def __repr__(self):
    return 'BOM(encoding_pattern_index=%r, image_id=%r, components=%r)' % (
        self.encoding_pattern_index, self.image_id, self.components)
