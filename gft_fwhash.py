#!/usr/bin/env python
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import hashlib
import optparse
import os

import flashrom_util
import fmap
import gft_common

from gft_common import WarningMsg, VerboseMsg, DebugMsg, ErrorMsg, ErrorDie


def GetBIOSReadOnlyHash(file_source=None):
  """
  Returns a hash of main firmware (BIOS) read only parts,
  to confirm we have proper keys / boot code / recovery image installed.

  Args:
      file_source: None to read BIOS from system flash rom, or any string
      value as the file name of firmware image to read.
  """
  # hash_ro_list: RO section to be hashed
  hash_src = ''
  hash_ro_list = ['RO_SECTION']

  flashrom = flashrom_util.FlashromUtility(exception_type=gft_common.GFTError)
  flashrom.initialize(flashrom.TARGET_BIOS, target_file=file_source)

  image = flashrom.get_current_image()
  fmap_obj = fmap.fmap_decode(image)
  if not fmap_obj:
    ErrorDie('GetBIOSReadOnlyHash: No FMAP structure in flashrom.')

  # TODO(hungte) we can check that FMAP must reside in RO section, and the
  # BSTUB must be aligned to bottom of firmware.
  hash_src = hash_src + fmap.fmap_encode(fmap_obj)

  # New firmware spec defined new "RO_SECTION" which includes all sections to
  # be hashed. Legacy firmware uses a list of BSTUB, GBB, and DEV.
  if hash_ro_list[0] not in flashrom.layout:
    WarningMsg("Warning: firmware_hash: working on legacy firmware")
    hash_ro_list = ['BOOT_STUB', 'GBB', 'RECOVERY']

  for section in hash_ro_list:
    src = flashrom.read_section(section)
    if not src:
      ErrorDie('GetBIOSReadOnlyHash: Cannot get section [%s]' % section)
    hash_src = hash_src + src
  if not hash_src:
    ErrorDie('GetBIOSReadOnlyHash: Invalid hash source from flashrom.')

  return hashlib.sha256(hash_src).hexdigest()


def GetECHash(file_source=None):
  """
  Returns a hash of Embedded Controller firmware parts,
  to confirm we have proper updated version of EC firmware.

  Args:
      file_source: None to read BIOS from system flash rom, or any string
      value as the file name of firmware image to read.
  """
  flashrom = flashrom_util.FlashromUtility(exception_type=gft_common.GFTError)
  flashrom.initialize(flashrom.TARGET_EC, target_file=file_source)
  # to bypass the 'skip verification' sections
  image = flashrom.get_current_image()
  if not image:
    ErrorDie('GetECHash: Cannot read EC firmware')
  hash_src = flashrom.get_verification_image(image)
  return hashlib.sha256(hash_src).hexdigest()


def UpdateGBB(old_bios, db_file, in_place=False):
  """
  Updates firmware image GBB data according to given components database file.

  Returns a new bios file that is changed its GBB values from old_bios
  according to the fields in components.

  Args:
      old_bios: BIOS file to be changed its GBB values.
      components: hardware component list to be referred.
  """
  base = gft_common.GetComponentsDatabaseBase(db_file)
  try:
    components = gft_common.LoadComponentsDatabaseFile(db_file)
  except:
    ErrorDie('UpdateGBB: Invalid components list file: %s' % db_file)
  for key in ['part_id_hwqual', 'data_bitmap_fv', 'key_root', 'key_recovery']:
    if len(components[key]) != 1 or components[key][0] == '*':
      ErrorDie('Components list should have a valid value for %s: %s' %
               (key, db_file))
  cmd = 'gbb_utility --set'
  cmd += ' --hwid="%s"' % components['part_id_hwqual'][0]
  cmd += ' --bmpfv="%s"' % os.path.join(base, components['data_bitmap_fv'][0])
  cmd += ' --rootkey="%s"' % os.path.join(base, components['key_root'][0])
  cmd += ' --recoverykey="%s"' % os.path.join(base,
                                              components['key_recovery'][0])
  cmd += ' %s' % old_bios
  new_bios = old_bios
  if not in_place:
    new_bios = gft_common.GetTemporaryFileName()
    cmd += ' %s' % new_bios
  cmd += ' >/dev/null'
  VerboseMsg("WriteGBB: invoke command: " + cmd)
  gft_common.SystemOutput(cmd)
  return new_bios


#############################################################################
# Console main entry
@gft_common.GFTConsole
def _main():
  usage = 'Usage: %prog --target=BIOS|EC --image=IMAGE [--gbb=COMPONENTS]'
  parser = optparse.OptionParser(usage=usage)
  parser.add_option('--target', dest='target', metavar='BIOS|EC',
                    help='hash target, BIOS or EC')
  parser.add_option('--image', dest='image',
                    help='firmware image file, or empty to read from system')
  parser.add_option('--gbb', dest='gbb', metavar='COMPONENTS',
                    help='component db file for replacing GBB data in BIOS')
  (options, args) = parser.parse_args()

  image = options.image
  if image is None:
    parser.error("Please specify --image to a firmware image file or ''")
  if args:
    parser.error("Unknown param(s): " + ' '.join(args))

  target = options.target and options.target.lower()
  if target not in ['bios', 'ec']:
    parser.error("Please specify either BIOS or EC for --target")

  modified_image = None
  if options.gbb:
    if target != 'bios':
      parser.error("Please set --target=BIOS if replace GBB")
    if image == '':
      parser.error("Please specify --image to a file if replace GBB")
    modified_image = UpdateGBB(image, options.gbb, in_place=False)

  if target == 'bios':
    print GetBIOSReadOnlyHash(modified_image or image)
  elif target == 'ec':
    print GetECHash(image)

  # Remove the temporary GBB-modified file.
  if modified_image:
    os.remove(modified_image)


if __name__ == "__main__":
  _main()
