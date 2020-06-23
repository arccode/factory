# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import hashlib
import logging
import re
import tempfile

from cros.factory.gooftool import crosfw
from cros.factory.probe.lib import cached_probe_function
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils

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
        'futility gbb -g --%s=%s %s' % (key_name, f.name, fw_file_path),
        shell=True, log=True)
    key_info = process_utils.CheckOutput(
        'futility vbutil_key --unpack %s' % f.name, shell=True)
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
  id_stripped = image.get_section(id_name).decode('utf-8').strip(chr(0))
  if id_stripped:
    return '#%s' % id_stripped
  return ''


def _MainRoHash(image):
  """Algorithm: sha256(fmap, RO_SECTION[-GBB])."""
  hash_src = image.get_fmap_blob()
  gbb = image.get_section('GBB')
  zero_gbb = b'\x00' * len(gbb)
  image.put_section('GBB', zero_gbb)
  hash_src += image.get_section('RO_SECTION')
  image.put_section('GBB', gbb)
  # pylint: disable=no-member
  return {
      'hash': hashlib.sha256(hash_src).hexdigest(),
      'version': _AddFirmwareIdTag(image).lstrip('#')}


def _EcRoHash(image):
  """Algorithm: sha256(fmap, EC_RO)."""
  hash_src = image.get_fmap_blob()
  hash_src += image.get_section('EC_RO')
  # pylint: disable=no-member
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
  except Exception:
    return None

  if image.has_section('EC_RO'):
    return _EcRoHash(image)
  if image.has_section('GBB') and image.has_section('RO_SECTION'):
    return _MainRoHash(image)
  return None


class ChromeosFirmwareFunction(cached_probe_function.LazyCachedProbeFunction):
  # pylint: disable=line-too-long
  """Get firmware information from a flash chip.

  Description
  -----------
  This function mainly runs ``flashrom`` to get the firmware image from the
  specific flash chip and calculates the hash of some of the sections of the
  image.

  - If ``field="firmware_keys"``, this function outputs sha1sum hash of the
    root key and the recovery key recorded in the readonly main firmware.  If
    the keyset is develop keyset, the output will contain a special suffix mark
    ``#devkeys/rootkey`` and ``#devkeys/recoverykey``.  See `Examples`_ for
    detail.

  - If ``field="ro_main_firmware"``, this function outputs the sha256 hash of
    the readonly main firmware and also the version of the firmware.

  - If ``field="ro_ec_firmware"``, this function outputs the sha256 hash of
    the readonly EC firmware and also the version of the firmware.

  - If ``field="ro_pd_firmware"``, this function outputs the sha256 hash of
    the readonly PD firmware and also the version of the firmware.  Since
    not all devices have a PD flash chip, it's possible that the output of this
    function is empty.

  Examples
  --------

  As this function has only one single argument, the ``eval`` part of the
  probe statement can be simplified into a single string instead of a
  dictionary.  For example, the probe statement for probing the key hash is ::

    {
      "eval": "chromeos_firmware:firmware_keys":
    }

  , where ``chromeos_firmware:firmware_keys`` is equivalent to ::

    {
      "chromeos_firmware": {
        "field": "firmware_keys"
      }
    }

  We category below examples into two use cases.

  Probe the Key Hash (``field="firmware_keys"``)
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

  If the firmware is not signed and contains a develop keyset, the probed
  results must be ::

    [
      {
        "rootkey": "kv3#b11d74edd6c14...0bc20cf041f10#devkey/rootkey",
        "recoverykey": "kv3#c14bd0b70d9...d8f43de48d4ed#devkey/recoverykey"
      }
    ]

  Probe the RO Firmware Image Hash (``field="ro_[main|ec|pd]_firmware"``)
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

  The ``values`` of the output must contains two fields: ``hash`` and
  ``version``.  For example::

    [
      {
        "hash": "13497173ba1fb678ab3f...ebd27d00d",
        "version": "supercoolproj_v1.1.2738-3927abcd2"
      }
    ]

  """

  ARGS = [
      Arg('field', type_utils.Enum(FIELDS),
          'The flash chip where this function probes the firmware from.')
  ]

  def GetCategoryFromArgs(self):
    if self.args.field not in FIELDS:
      raise cached_probe_function.InvalidCategoryError(
          '`field` should be one of %r' % FIELDS)

    return self.args.field

  @classmethod
  def ProbeDevices(cls, category):
    if category == FIELDS.firmware_keys:
      fw_file_path = crosfw.LoadMainFirmware().GetFileName(
          sections=['RO_SECTION'])
      return {
          'key_recovery': _FwKeyHash(fw_file_path, 'recoverykey'),
          'key_root': _FwKeyHash(fw_file_path, 'rootkey')}

    if category == FIELDS.ro_main_firmware:
      fw_file_path = crosfw.LoadMainFirmware().GetFileName(
          sections=['RO_SECTION'])
    if category == FIELDS.ro_ec_firmware:
      fw_file_path = crosfw.LoadEcFirmware().GetFileName()
    if category == FIELDS.ro_pd_firmware:
      fw_file_path = crosfw.LoadPDFirmware().GetFileName()
    return CalculateFirmwareHashes(fw_file_path)
