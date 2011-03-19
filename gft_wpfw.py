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


def EnableWriteProtect(target, verbose=False):
  """ Enables and verifies firmware write protection status.
  ARGS
      target: the flashrom_util target code, 'bios' or 'ec'.
      verbose: verbosity for flashrom_util.
  """

  flashrom = flashrom_util.flashrom_util(verbose=verbose)

  # The EEPROM should be programmed as:
  #     (BIOS)  LSB [ RW | RO ] MSB
  #     (EC)    LSB [ RO | RW ] MSB
  # Each part of RW/RO section occupies half of the EEPROM.

  eeprom_sets = ({  # BIOS
    'name': 'BIOS',
    'layout': 'rw|ro',
    'target': 'bios',
    'trust_fmap': False,
    }, {  # Embedded Controller
    'name': 'EC',
    'layout': 'ro|rw',
    'target': 'ec',
    'trust_fmap': True,
    'fmap_conversion': {'EC_RO': 'ro', 'EC_RW': 'rw'},
    })

  # TODO(hungte) BIOS on ARM is using different layout,
  # so we must also trust fmap for BIOS in the future.
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
  if conf['trust_fmap']:
    DebugMsg(' - Trying to use FMAP layout for %s' % name)
    image = flashrom.read_whole()
    assert eeprom_size == len(image)
    layout = flashrom_util.decode_fmap_layout(conf['fmap_conversion'], image)
    if 'ro' not in layout:
      layout = None
    else:
      VerboseMsg(' - Using layout by FMAP in %s' % name)

  if not layout:
    # do not trust current image when detecting layout.
    layout = flashrom.detect_layout(conf['layout'], eeprom_size, None)
    VerboseMsg(' - Using hard-coded layout for %s' % name)
  if not layout:
    ErrorDie('wpfw: cannot detect %s layout' % name)

  # verify if the layout is half of firmware.
  if layout['ro'][1] - layout['ro'][0] + 1 != eeprom_size / 2:
    ErrorDie('Invalid RO section in flash rom layout.')

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
  EnableWriteProtect(sys.argv[1], verbose=True)


if __name__ == '__main__':
  _main()
