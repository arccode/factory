# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import re
import hashlib
import tempfile

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils
from cros.factory.gooftool import crosfw

FIELDS = type_utils.Enum(
    ['firmware_keys', 'ro_main_firmware', 'ro_ec_firmware', 'ro_pd_firmware'])


def _FwKeyHash(fw_file_path, key_name):
  """Hash specified GBB key, extracted by vbutil_key."""
  known_hashes = {
      'b11d74edd286c144e1135b49e7f0bc20cf041f10': 'devkeys/rootkey',
      'c14bd720b70d97394257e3e826bd8f43de48d4ed': 'devkeys/recovery',
  }
  with tempfile.NamedTemporaryFile(prefix='gbb_%s_' % key_name) as f:
    process_utils.CheckOutput(
        'gbb_utility -g --%s=%s %s' % (key_name, f.name, fw_file_path),
        shell=True, log=True)
    key_info = process_utils.CheckOutput(
        'vbutil_key --unpack %s' % f.name, shell=True)
    sha1sum = re.findall(r'Key sha1sum:[\s]+([\w]+)', key_info)
    if len(sha1sum) != 1:
      logging.error('Failed calling vbutil_key for firmware key hash.')
      return None
    sha1 = sha1sum[0]
    if sha1 in known_hashes:
      sha1 += '#' + known_hashes[sha1]
    return 'kv3#' + sha1


def _AddFirmwareIdTag(image, id_name='RO_FRID'):
  """Returns firmware ID in '#NAME' format if available."""
  if not image.has_section(id_name):
    return ''
  id_stripped = image.get_section(id_name).strip(chr(0))
  if id_stripped:
    return '#%s' % id_stripped
  return ''


def _MainRoHash(image):
  """Algorithm: sha256(fmap, RO_SECTION[-GBB])."""
  hash_src = image.get_fmap_blob()
  gbb = image.get_section('GBB')
  zero_gbb = chr(0) * len(gbb)
  image.put_section('GBB', zero_gbb)
  hash_src += image.get_section('RO_SECTION')
  image.put_section('GBB', gbb)
  # pylint: disable=E1101
  return {
      'hash': hashlib.sha256(hash_src).hexdigest(),
      'version': _AddFirmwareIdTag(image).lstrip('#')}


def _EcRoHash(image):
  """Algorithm: sha256(fmap, EC_RO)."""
  hash_src = image.get_fmap_blob()
  hash_src += image.get_section('EC_RO')
  # pylint: disable=E1101
  return {
      'hash': hashlib.sha256(hash_src).hexdigest(),
      'version': _AddFirmwareIdTag(image).lstrip('#')}


def CalculateFirmwareHashes(fw_file_path):
  """Calculate the volatile hashes corresponding to a firmware blob.

  Given a firmware blob, determine what kind of firmware it is based
  on what sections are present.  Then generate a dict containing the
  corresponding hash values.
  """
  raw_image = open(fw_file_path, 'rb').read()
  try:
    image = crosfw.FirmwareImage(raw_image)
  except:  # pylint: disable=W0702
    return None

  if image.has_section('EC_RO'):
    return _EcRoHash(image)
  elif image.has_section('GBB') and image.has_section('RO_SECTION'):
    return _MainRoHash(image)


class ChromeosFirmwareFunction(function.ProbeFunction):
  """Get information of flash chip."""

  ARGS = [
      Arg('field', str,
          'The flash chip. It should be one of {%s}' %
          ', '.join(FIELDS)),
  ]

  def Probe(self):
    if self.args.field not in FIELDS:
      return function.NOTHING

    if self.args.field == FIELDS.firmware_keys:
      fw_file_path = crosfw.LoadMainFirmware().GetFileName()
      return {
          'key_recovery': _FwKeyHash(fw_file_path, 'recoverykey'),
          'key_root': _FwKeyHash(fw_file_path, 'rootkey')}

    if self.args.field == FIELDS.ro_main_firmware:
      fw_file_path = crosfw.LoadMainFirmware().GetFileName()
    if self.args.field == FIELDS.ro_ec_firmware:
      fw_file_path = crosfw.LoadEcFirmware().GetFileName()
    if self.args.field == FIELDS.ro_pd_firmware:
      fw_file_path = crosfw.LoadPDFirmware().GetFileName()
    return CalculateFirmwareHashes(fw_file_path)
