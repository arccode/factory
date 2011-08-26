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


# Global Variable
_HashAlgorithms = {}


# Utility Function
def HashAlgorithm(func):
  """Decorator for algorithm definition. """
  def _wrapped(*arg, **kargs):
    result = func(*arg, **kargs)
    (target, version) = _wrapped.__name__.split('_')
    code = target.lower()[0]
    return '%c%s#%s' % (code, version, result)
  name = func.__name__
  assert name not in _HashAlgorithms
  _wrapped.__name__ = name
  _HashAlgorithms[name] = _wrapped
  return _wrapped


def DefaultHashAlgorithm(func):
  """Decorator of default algorithm. """
  name = func.__name__
  (target, code) = name.split('_')
  new_func = HashAlgorithm(func)
  assert target not in _HashAlgorithms
  _HashAlgorithms[target] = new_func
  return new_func


def FindAlgorithm(target, version):
  """Returns a registered algorithm"""
  if version:
    name = '%s_%s' % (target, version)
  else:
    name = target
  if name not in _HashAlgorithms:
    ErrorDie('Unknown algorithm: %s' % name)
  return _HashAlgorithms[name]


def GetGbbKey(image_file, name):
  """
  Reads GBB key property from a firmware image.

  Args:
    image_file: the file name of main firmware image.
    name: name of the key to retrieve (see gbb_utility).
  """
  filename = gft_common.GetTemporaryFileName('gbb%s' % name)
  try:
    gft_common.System('gbb_utility -g --%s=%s %s' %
                      (name, filename, image_file))
    return gft_common.ReadBinaryFile(filename)
  finally:
    os.remove(filename)


# Hash Algorithms
@HashAlgorithm
def Main_v1(image_source):
  """ Algorithm: sha256(fmap, RO_SECTION) """
  image = flashrom_util.FirmwareImage(image_source)
  hash_src = image.get_fmap_blob()
  if image.has_section('RO_SECTION'):
    hash_src += image.get_section('RO_SECTION')
  else:
    # legacy section
    hash_src += image.get_section('BOOT_STUB')
    hash_src += image.get_section('GBB')
    hash_src += image.get_section('RECOVERY')
  return hashlib.sha256(hash_src).hexdigest()


@DefaultHashAlgorithm
def Main_v2(image_source):
  """ Algorithm: sha256(fmap, RO_SECTION[-GBB]) """
  image = flashrom_util.FirmwareImage(image_source)
  hash_src = image.get_fmap_blob()
  gbb = image.get_section('GBB')
  zero_gbb = chr(0) * len(gbb)
  image.put_section('GBB', zero_gbb)
  hash_src += image.get_section('RO_SECTION')
  return hashlib.sha256(hash_src).hexdigest()


@HashAlgorithm
def Ec_v1(image_source):
  """ Algorithm: sha256(whole_image) """
  hash_src = image_source
  return hashlib.sha256(hash_src).hexdigest()


@DefaultHashAlgorithm
def Ec_v2(image_source):
  """ Algorithm: sha256(fmap, EC_RO) """
  image = flashrom_util.FirmwareImage(image_source)
  hash_src = image.get_fmap_blob()
  hash_src += image.get_section('EC_RO')
  return hashlib.sha256(hash_src).hexdigest()


@HashAlgorithm
def Gbb_v1(image_source):
  """ Algorithm: sha256(GBB) """
  image = flashrom_util.FirmwareImage(image_source)
  hash_src = image.get_section('GBB')
  return hashlib.sha256(hash_src).hexdigest()


@DefaultHashAlgorithm
def Gbb_v2(image_source):
  """ Algorithm: sha256(GBB-HWID) """
  image = flashrom_util.FirmwareImage(image_source)
  temp_file = gft_common.GetTemporaryFileName()
  try:
    # HWID can be checked explicitly, so we temporarily overwrite the HWID with
    # a fixed string for computing the hash, so the hash doesn't depend on the
    # final HWID.
    reference_hwid = 'ChromeOS'
    gft_common.WriteBinaryFile(temp_file, image.get_section('GBB'))
    gft_common.System('gbb_utility -s --hwid="%s" "%s"' %
                      (reference_hwid, temp_file))
    hash_src = gft_common.ReadBinaryFile(temp_file)
  finally:
    os.remove(temp_file)
  return hashlib.sha256(hash_src).hexdigest()


@HashAlgorithm
def Key_v1(key_blob):
  """ Algorithm: sha256(key) """
  hash_src = key_blob
  return hashlib.sha256(hash_src).hexdigest()


@DefaultHashAlgorithm
def Key_v2(key_blob):
  """ Algorithm: sha256(key%%[00|FF])) """
  # keys may be padded with 0x00 or 0xFF.
  hash_src = key_blob
  hash_src = hash_src.strip(chr(0)).strip(chr(0xFF))
  return hashlib.sha256(hash_src).hexdigest()


# Public API
def GetMainFirmwareReadOnlyHash(file_source=None, algorithm=None):
  """
  Returns a hash of main firmware (BIOS) read only parts,
  to confirm we have proper keys / boot code / recovery image installed.

  Args:
      file_source: None to read firmware from system flash chip, otherwise
                   a file name of firmware image to read.
      algorithm: The algorithm to generate hash value
  """
  flashrom = flashrom_util.FlashromUtility(exception_type=gft_common.GFTError)
  flashrom.initialize(flashrom.TARGET_BIOS, target_file=file_source)
  image = flashrom.get_current_image()
  algorithm = FindAlgorithm('Main', algorithm)
  return algorithm(image)


def GetMainFirmwareGbbHash(file_source=None, algorithm=None):
  """
  Returns a hash of main firmware (BIOS) GBB section,
  to confirm we have proper keys / images / HWID.

  Args:
      file_source: None to read firmware from system flash chip, otherwise
                   a file name of firmware image to read.
      algorithm: The algorithm to generate hash value
  """
  flashrom = flashrom_util.FlashromUtility(exception_type=gft_common.GFTError)
  flashrom.initialize(flashrom.TARGET_BIOS, target_file=file_source)
  image = flashrom.get_current_image()
  algorithm = FindAlgorithm('Gbb', algorithm)
  return algorithm(image)


def GetEcFirmwareReadOnlyHash(file_source=None, algorithm=None):
  """
  Returns a hash of Embedded Controller firmware read only parts,
  to confirm we have proper updated version of EC firmware.

  Args:
      file_source: None to read firmware from system flash chip, otherwise
                   a file name of firmware image to read.
      algorithm: The algorithm to generate hash value
  """
  flashrom = flashrom_util.FlashromUtility(exception_type=gft_common.GFTError)
  flashrom.initialize(flashrom.TARGET_EC, target_file=file_source)
  image = flashrom.get_current_image()
  algorithm = FindAlgorithm('Ec', algorithm)
  return algorithm(image)


def GetKeyHash(key_blob, algorithm=None):
  """
  Returns a hash of cryptographic key blob

  Args:
    key_blob: Cryptographic key blob, with paddings.
    algorithm: The algorithm to generate hash value
  """
  algorithm = FindAlgorithm('Key', algorithm)
  return algorithm(key_blob)


def UpdateGBB(old_image, db_file, in_place=False, clear_flags=False):
  """
  Updates main firmware image GBB data by given components database file.

  Returns a new image with updated GBB data.

  Args:
      old_image: Firmware image file to be updated.
      components: Hardware component list to be referred.
  """
  base = gft_common.GetComponentsDatabaseBase(db_file)
  try:
    components = gft_common.LoadComponentsDatabaseFile(db_file)
  except Exception, e:
    ErrorDie('UpdateGBB: Invalid components list file: %s (%s)' % (db_file, e))

  # The are 2 fields in component list related to gbb:
  # - part_id_hwqual (HWID, mandatory)
  # - data_bitmap_fv (optional because we have universal bitmap now)
  # TODO(hungte) check if the keys match "hash_key_*" in components
  hwid = components.get('part_id_hwqual', [])
  bmpfv = components.get('data_bitmap_fv', [])
  if len(hwid) != 1:
    ErrorDie('HWID (part_id_hwqual) must be one valid value.')
  if len(bmpfv) != 1:
    ErrorDie('bitmap')

  hwid = hwid[0]
  bmpfv = bmpfv[0]

  cmd = 'gbb_utility --set --hwid="%s"' % hwid
  if bmpfv:
    cmd += ' --bmpfv="%s"' % os.path.join(base, bmpfv)
  if clear_flags:
    cmd += ' --flags=0'
  cmd += ' "%s"' % old_image
  new_image = old_image
  if not in_place:
    new_image = gft_common.GetTemporaryFileName()
    cmd += ' "%s"' % new_image
  VerboseMsg("WriteGBB: invoke command: " + cmd)
  gft_common.System(cmd)
  return new_image


#############################################################################
# Console main entry
@gft_common.GFTConsole
def _main():
  valid_targets = ['main', 'ec', 'gbb', 'gbbkeys']
  usage = 'Usage: %prog --target=TARGET --image=IMAGE [--gbb=COMPONENTS]'
  parser = optparse.OptionParser(usage=usage)
  parser.add_option('--target', dest='target', metavar='|'.join(valid_targets),
                    help=('type of target: %s' % ', '.join(valid_targets)))
  parser.add_option('--image', dest='image',
                    help='firmware image file, or empty to read from system')
  parser.add_option('--algorithm', dest='algorithm',
                    help='algorithm to generate hash')
  parser.add_option('--gbb', dest='gbb', metavar='COMPONENTS',
                    help='component db file for replacing GBB data in BIOS')
  (options, args) = parser.parse_args()

  image = options.image
  if image is None:
    parser.error("Please specify --image to a firmware image file or ''")
  if args:
    parser.error("Unknown param(s): " + ' '.join(args))

  target = options.target and options.target.lower()
  # legacy support
  if target == 'bios':
    target = 'main'
  if target not in valid_targets:
    #TODO(hungte) Detect type by FMAP section names
    parser.error("Please specify --target from: %s" %
                 (', ').join(valid_targets))
  modified_image = None
  if options.gbb:
    if target != 'main' and target != 'gbb':
      parser.error("Please set --target='main' or 'gbb' to update GBB")
    if image == '':
      parser.error("Please specify --image to a file to update GBB")
    modified_image = UpdateGBB(image, options.gbb, in_place=False,
                               clear_flags=True)

  algorithm = options.algorithm
  if target == 'main':
    print "Main Firmware: %s" % GetMainFirmwareReadOnlyHash(
        modified_image or image, algorithm=algorithm)
  elif target == 'gbb':
    print "GBB Hash: %s" % GetMainFirmwareGbbHash(
        modified_image or image, algorithm=algorithm)
  elif target == 'gbbkeys':
    print "Recovery Key: %s" % GetKeyHash(
        GetGbbKey(image, "recoverykey"), algorithm=algorithm)
    print "Root Key: %s" % GetKeyHash(
        GetGbbKey(image, "rootkey"), algorithm=algorithm)
  elif target == 'ec':
    print "EC Firmware: %s" % GetEcFirmwareReadOnlyHash(
        image, algorithm=algorithm)

  # Remove the temporary GBB-modified file.
  if modified_image:
    os.remove(modified_image)


if __name__ == "__main__":
  _main()
