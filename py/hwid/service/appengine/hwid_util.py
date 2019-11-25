# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Utility functions that help processing hwid and BOM's."""

from collections import defaultdict
import logging

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import bom as v3_bom


class HWIDUtilException(Exception):
  pass


def GetTotalRamFromHwidData(drams):
  """Convert a list of DRAM string into a total number of bytes integer."""
  # v3_bom.RamSize is compatible with HWIDv2
  total_ram = v3_bom.RamSize(byte_count=0)
  for dram in drams:
    try:
      ram_size = v3_bom.RamSize(dram)
    except ValueError as ex:
      raise HWIDUtilException(str(ex))
    total_ram += ram_size
  return str(total_ram), total_ram.byte_count


def GetSkuFromBom(bom, configless=None):
  """From a BOM construct a string that represents the hardware."""
  components = defaultdict(list)
  for component in bom.GetComponents():
    components[component.cls].append(component.name)
    logging.debug(component)

  cpu = None
  cpus = GetComponentValueFromBom(bom, 'cpu')
  if cpus:
    cpus.sort()
    cpu = '_'.join(cpus)

  if configless and 'memory' in configless:
    memory_str = str(configless['memory']) + 'GB'
    total_bytes = configless['memory'] * 1024 * 1024 * 1024
  else:
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
