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

import flashrom_util
import gft_common

from gft_common import DebugMsg, VerboseMsg, ErrorDie


def EnableWriteProtect(target, image=None):
  """ Enables and verifies firmware write protection status.
  ARGS
      target: the flashrom_util target code, 'bios' or 'ec'.
      image: a reference image for layout detection.
  """

  flashrom = flashrom_util.flashrom_util(verbose_msg=VerboseMsg,
                                         exception_type=gft_common.GFTError,
                                         system_output=gft_common.SystemOutput)

  # The EEPROM should be programmed as:
  #   x86:
  #     (BIOS)  LSB [ RW | RO ] MSB
  #     (EC)    LSB [ RO | RW ] MSB
  #   arm:
  #     (BIOS)  LSB [ RO | RW ] MSB
  # Each part of RW/RO section occupies half of the EEPROM.
  # To simplify the arch detection, we trust the FMAP.

  layout_rw_ro = 'rw|ro'
  layout_ro_rw = 'ro|rw'

  eeprom_sets = ({  # BIOS
    'name': 'BIOS',
    'layout': layout_rw_ro,
    'target': 'bios',
    'fmap_conversion': {'RO_SECTION': 'ro'},
    }, {  # Embedded Controller
    'name': 'EC',
    'layout': layout_ro_rw,
    'target': 'ec',
    'fmap_conversion': {'EC_RO': 'ro'},
    })

  matched = [eeprom for eeprom in eeprom_sets
             if eeprom['target'] == target]
  if not matched:
    ErrorDie('enable_write_protect: unknown target: ' + target)
  conf = matched[0]
  name = conf['name']

  # select target
  if not flashrom.select_target(target):
    ErrorDie('wpfw: Cannot select target ' + name)
  eeprom_size = flashrom.get_size()

  # build layout
  if not eeprom_size:
    ErrorDie('wpfw: cannot get size for ' + name)
  layout = None
  layout_desc = conf['layout']
  DebugMsg(' - Trying to use FMAP layout for %s' % name)
  if not image:
    image = flashrom.read_whole()
  assert eeprom_size == len(image)
  fmap_layout = flashrom_util.decode_fmap_layout(conf['fmap_conversion'], image)

  if 'ro' in fmap_layout:
    # Verify if the layout is in valid size.  Most chips support only setting
    # write protection on half of the total size, so we always devide the
    # flashrom into 2 slots.
    slot_size = int(eeprom_size / 2)
    # fmap_layout is a (offset, offset) structure, not (offset, size)
    (ro_begin_offset, ro_end_offset) = fmap_layout['ro']
    ro_begin_slot = int(ro_begin_offset / slot_size)
    ro_end_slot = int(ro_end_offset / slot_size)
    error_reason = None
    if ro_begin_slot != ro_end_slot:
      error_reason = 'section accross valid slot range'
    # flashrom layout does not really support a section of '1 byte in size'.
    # Both 0/1 sized sections are invalid.
    if ro_begin_offset >= ro_end_offset:
      error_reason = 'invalid section size'
    if error_reason:
      ErrorDie('Invalid RO section in layout: %s (%s,%s)' %
               (error_reason, ro_begin_offset, ro_end_offset))
    assert ro_begin_slot == 0 or ro_begin_slot == 1

    # decide ro, rw according to the offset of 'ro'.
    if ro_begin_slot == 0:
      layout_desc = layout_ro_rw
    else:
      layout_desc = layout_rw_ro
    VerboseMsg(' - Using layout by FMAP in %s: %s' % (name, layout_desc))
  else:
    VerboseMsg(' - Using hard-coded layout for %s: %s' % name, layout_desc)

  layout = flashrom.detect_layout(layout_desc, eeprom_size, None)
  if not layout:
    ErrorDie('wpfw: cannot detect %s layout' % name)

  VerboseMsg(' - Enable Write Protection for ' + name)
  # only configure (enable) write protection if current status is not
  # correct, because sometimes the factory test is executed several
  # times without resetting WP status.
  if not flashrom.verify_write_protect(layout, 'ro'):
    if not (flashrom.enable_write_protect(layout, 'ro')
            and flashrom.verify_write_protect(layout, 'ro')):
      ErrorDie('wpfw: cannot enable write protection for ' + name)
  VerboseMsg(' - Check Write Protection for ' + name)
  flashrom.disable_write_protect()
  if not flashrom.verify_write_protect(layout, 'ro'):
    ErrorDie('wpfw: not write-protected (modifiable status): ' + name)

  # Always restore the target to BIOS(spi). Some platforms may fail to reboot if
  # target is EC(lpc).
  if target != flashrom.TARGET_BIOS:
    flashrom.select_target(flashrom.TARGET_BIOS)
  return True


#############################################################################
# Console main entry
@gft_common.GFTConsole
def _main():
  """ Main entry for console mode """
  if len(sys.argv) != 2:
    print 'Usage: %s target_code(bios/ec)\n' % sys.argv[0]
    sys.exit(1)

  gft_common.SetDebugLevel(True)
  gft_common.SetVerboseLevel(True)
  EnableWriteProtect(sys.argv[1])


if __name__ == '__main__':
  _main()
