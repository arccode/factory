# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Utility functions that help processing hwid and BOM's."""

from collections import defaultdict
from collections import OrderedDict
import logging
import re


class HWIDUtilException(Exception):
  pass


class _RamSize(object):
  """Handle memory size labels."""
  _UNITS = OrderedDict([
      ('', 1), ('K', 1 << 10), ('M', 1 << 20), ('G', 1 << 30)])
  # Possible ram strings:
  # dram_micron_1g_dimm2, hynix_2gb_dimm0, 2x2GB_DDR3_1600,
  # K4EBE304EB_EGCF_8gb, H9HCNNN8KUMLHR_1gb_slot2
  _RE = re.compile(r'(^|_)(\d+X)?(\d+)([KMG])B?($|_)')

  def __init__(self, ram_size_str=None, byte_count=None):
    super(_RamSize, self).__init__()
    if byte_count is not None:
      self.byte_count = byte_count
      return
    size_re = _RamSize._RE.search(ram_size_str.upper())
    if not size_re:
      logging.exception('Unable to process dram format %s', ram_size_str)
      raise HWIDUtilException('Invalid DRAM: %s' % ram_size_str)
    multiplier = int(size_re.group(2)[:-1]) if size_re.group(2) else 1
    self.byte_count = multiplier * int(
        size_re.group(3)) * _RamSize._UNITS[size_re.group(4)]

  def __add__(self, rhs):
    assert isinstance(rhs, _RamSize)
    return _RamSize(byte_count=self.byte_count + rhs.byte_count)

  def __iadd__(self, rhs):
    assert isinstance(rhs, _RamSize)
    self.byte_count += rhs.byte_count
    return self

  def __mul__(self, rhs):
    assert isinstance(rhs, int)
    return _RamSize(byte_count=self.byte_count * rhs)

  def __rmul__(self, lhs):
    return _RamSize.__mul__(self, lhs)

  def __str__(self):
    if self.byte_count == 0:
      return '0b'
    for key, value in reversed(_RamSize._UNITS.items()):
      if self.byte_count % value == 0:
        return str(int(self.byte_count / value)) + key + 'b'
    raise ValueError('Cannot represent byte_count %s.', self.byte_count)


def GetTotalRamFromHwidData(drams):
  """Convert a list of DRAM string into a total number of bytes integer."""
  total_ram = _RamSize(byte_count=0)
  for dram in drams:
    total_ram += _RamSize(dram)
  return str(total_ram), total_ram.byte_count


def GetSkuFromBom(bom):
  """From a BOM construct a string that represents the hardware."""
  components = defaultdict(list)
  for component in bom.GetComponents():
    components[component.cls].append(component.name)

  cpu = None
  cpus = GetComponentValueFromBom(bom, 'cpu')
  if cpus:
    cpus.sort()
    cpu = '_'.join(cpus)
  memory_str, total_bytes = GetTotalRamFromHwidData(components['dram'])
  board = bom.board.lower()
  sku = '%s_%s_%s' % (board, cpu, memory_str)

  return {
      'sku': sku,
      'board': board,
      'cpu': cpu,
      'memory_str': memory_str,
      'total_bytes': total_bytes
  }


def GetComponentValueFromBom(bom, component_name):
  components = defaultdict(list)
  for component in bom.GetComponents():
    components[component.cls].append(component.name)

  if components[component_name]:
    return components[component_name]

  return None
