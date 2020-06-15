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

import collections
import logging
import re

from cros.factory.utils import type_utils


class BOM:
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

    for comp_cls, comp_names in components.items():
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


class RamSize:
  """Handle memory size labels."""
  _UNITS = collections.OrderedDict([
      ('', 1), ('K', 1 << 10), ('M', 1 << 20), ('G', 1 << 30)])
  # Possible ram strings:
  # dram_micron_1g_dimm2, hynix_2gb_dimm0, 2x2GB_DDR3_1600,
  # K4EBE304EB_EGCF_8gb, H9HCNNN8KUMLHR_1gb_slot2
  _RE = re.compile(r'(^|_)(\d+X)?(\d+)([KMG])B?($|_)')

  def __init__(self, ram_size_str=None, byte_count=None):
    super(RamSize, self).__init__()
    if byte_count is not None:
      self.byte_count = byte_count
      return
    matches = RamSize._RE.findall(ram_size_str.upper())
    if not matches:
      logging.error('Unable to process dram format %s', ram_size_str)
      raise ValueError('Invalid DRAM: %s' % ram_size_str)
    # Use the latest match as the ram size, since most ram strings
    # put the ram size at the end.
    # For example: Samsung_4G_M471A5644EB0-CRC_2048mb_1
    size_re = matches[-1]
    multiplier = int(size_re[1][:-1]) if size_re[1] else 1
    self.byte_count = multiplier * int(
        size_re[2]) * RamSize._UNITS[size_re[3]]

  def __add__(self, rhs):
    assert isinstance(rhs, RamSize)
    return RamSize(byte_count=self.byte_count + rhs.byte_count)

  def __iadd__(self, rhs):
    assert isinstance(rhs, RamSize)
    self.byte_count += rhs.byte_count
    return self

  def __mul__(self, rhs):
    assert isinstance(rhs, int)
    return RamSize(byte_count=self.byte_count * rhs)

  def __rmul__(self, lhs):
    return RamSize.__mul__(self, lhs)

  def __str__(self):
    if self.byte_count == 0:
      return '0B'
    for key, value in reversed(list(RamSize._UNITS.items())):
      if self.byte_count % value == 0:
        return str(int(self.byte_count // value)) + key + 'B'
    raise ValueError('Cannot represent byte_count %s.' % self.byte_count)
