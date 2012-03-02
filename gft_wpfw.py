#!/usr/bin/env python
#
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Google Factory Tool: Write Protection for Firmware

This module enables or verifies that firmware write protection is properly
activated.

WARNING: THE RO SECTIONS OF YOUR EEPROM WILL BECOME READONLY AFTER RUNNING THIS.
"""

import sys

import crosfw
import gft_common

from gft_common import DebugMsg, VerboseMsg, ErrorDie


def EnableWriteProtect(target, image=None):
  """ Enables and verifies firmware write protection status.
  ARGS
      target: the crosfw target code (crosfw.TARGET_*).
      image: a reference image for layout detection.
  """

  if image is None:
    with open(crosfw.LoadFirmware(target).path, 'rb') as f:
      image = f.read()

  # The EEPROM in FMAP are mapped as:
  #   (MAIN) [RO_SECTION | RW_SECTION_*]
  #   (EC)   [EC_RW | EC_RO]
  # Each part of RW/RO section occupies half of the EEPROM.

  ro_section_names = {
      crosfw.TARGET_MAIN: 'RO_SECTION',
      crosfw.TARGET_EC: 'EC_RO',
  }

  ro_name = ro_section_names[target]
  image_map = crosfw.FirmwareImage(image)
  if not image_map.has_section(ro_name):
    raise IOError, "Failed to find section %s in target %s." % (ro_name, target)
  area = image_map.get_section_area(ro_name)

  flashrom = crosfw.Flashrom(target)
  # Verify layout has valid size.  Most chips support only setting
  # write protection on half of the total size, so we always divide the flash
  # chipset space into 2 slots.
  slot_size = len(image) / 2
  ro_begin = int(area[0] / slot_size)
  ro_end = int((area[0] + area[1] - 1) / slot_size)
  if ro_begin != ro_end:
    raise ValueError, "Section %s exceeds write protection boundary." % ro_name
  ro_offset = ro_begin * slot_size
  ro_size = slot_size

  VerboseMsg(' - Enable Write Protection for ' + target)
  flashrom.EnableWriteProtection(ro_offset, ro_size)
  return True


#############################################################################
# Console main entry
@gft_common.GFTConsole
def _main():
  """ Main entry for console mode """
  if len(sys.argv) != 2:
    sys.stderr.write('Usage: %s %s\n' %
                     (sys.argv[0], '|'.join((crosfw.TARGET_MAIN,
                                             crosfw.TARGET_EC))))
    sys.exit(1)

  gft_common.SetDebugLevel(True)
  gft_common.SetVerboseLevel(True)
  EnableWriteProtect(sys.argv[1])


if __name__ == '__main__':
  _main()
