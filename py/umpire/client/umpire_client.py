# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to maintain umpire client information."""

import logging

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.umpire import common


class UmpireClientInfoInterface(object):
  """The interface that provide client info for Umpire server proxy."""

  def Update(self):
    """Updates client info.

    Returns:
      True if client info is changed.
    """
    raise NotImplementedError

  def GetXUmpireDUT(self):
    """Outputs client info for request header X-Umpire-DUT.

    Returns:
      Umpire client info in X-Umpire-DUT format: 'key=value; key=value ...'.
    """
    raise NotImplementedError

  def GetDUTInfoComponents(self):
    """Gets DUT info and components for GetUpdateFromCROSPayload call.

    Returns:
      {'x_umpire_dut': X-Umpire-DUT header in dict form,
       'components': components' version/hash for update lookup.}
    """
    raise NotImplementedError


class UmpireClientInfoException(Exception):
  pass


class UmpireClientInfo(object):
  """This class maintains client side info on DUT that is related to Umpire."""
  __implements__ = (UmpireClientInfoInterface)
  # Translated keys in DUT_INFO_KEYS to attributes used in UmpireClientInfo.
  # DUT_INFO_KEYS are used in GetXUmpireDUT() for X-Umpire-DUT.
  KEY_TRANSLATION = {
      'sn': 'serial_number',
      'mlb_sn': 'mlb_serial_number',
      'firmware': 'firmware_version',
      'ec': 'ec_version',
      'pd': 'pd_version',
      'mac': 'macs',
      'stage': 'stage'
  }

  # uuid and drop_slot are not used in XMLRPC calls but for HTTP webapps only.
  KEY_TRANSLATION_BLACK_LIST = set(['uuid', 'drop_slot'])

  VARIANT_FIELDS = [
      'serial_number', 'mlb_serial_number', 'firmware_version',
      'ec_version', 'pd_version', 'macs', 'stage']

  def __init__(self, _dut=None):
    # serial_number, mlb_serial_number, firmware, ec and wireless mac address
    # are detected in dut.info.SystemInfo module.
    self.serial_number = None
    self.mlb_serial_number = None
    self.firmware_version = None
    self.ec_version = None
    self.pd_version = None
    self.macs = {}
    self.stage = None
    self.dut = _dut
    if not self.dut:
      self.dut = device_utils.CreateDUTInterface()
      if not self.dut.link.IsLocal():
        # In station mode, it's the station who's connecting to Umpire
        self.dut = device_utils.CreateStationInterface()

    self.Update()

  def Update(self):
    """Updates client info.

    Returns:
      True if client info is changed.
    """
    # TODO(cychiang) Set fields from SystemInfo
    system_info = self.dut.info
    new_info = {}
    new_info['serial_number'] = system_info.serial_number
    new_info['mlb_serial_number'] = system_info.mlb_serial_number
    new_info['firmware_version'] = system_info.firmware_version
    new_info['ec_version'] = system_info.ec_version
    new_info['pd_version'] = system_info.pd_version
    new_info['stage'] = system_info.stage
    # new_info['macs'] is a dict like
    # {'eth0': 'xx:xx:xx:xx:xx:xx', 'eth1': 'xx:xx:xx:xx:xx:xx',
    #  'wlan0': 'xx:xx:xx:xx:xx:xx'}
    macs = dict(system_info.eth_macs)
    macs['wlan0'] = system_info.wlan0_mac
    new_info['macs'] = macs

    changed = False
    for key in UmpireClientInfo.VARIANT_FIELDS:
      if getattr(self, key) != new_info[key]:
        changed = True
        setattr(self, key, new_info[key])
    logging.debug('DUT info changed for X-Umpire-DUT = %r', changed)
    return changed

  def _GetComponentsDict(self):
    """Gets information needed for GetUpdateFromCROSPayload call.

    Returns:
      A component dict:
        'rootfs_test': version_string,
        'rootfs_release': version_string,
        'firmware_ec': version_string,
        'firmware_bios': version_string,
        'firmware_pd': version_string,
        'hwid': version_string (checksum in hwid db)
        'device_factory_toolkit': md5sum_hash_string.
    """
    components = {}
    system_info = self.dut.info
    components['rootfs_test'] = system_info.factory_image_version
    components['rootfs_release'] = system_info.release_image_version
    components['firmware_ec'] = system_info.ec_version
    components['firmware_bios'] = system_info.firmware_version
    components['firmware_pd'] = system_info.pd_version
    components['hwid'] = system_info.hwid_database_version
    components['device_factory_toolkit'] = system_info.toolkit_version
    # We don't really care about the version of netboot firmware. A DUT only
    # requests for netboot firmware when it wants to re-image itself.
    components['netboot_firmware'] = None

    return components

  def _GetXUmpireDUTDict(self):
    """Gets X-Umpire-DUT dict by translating keys."""
    info_dict = {}
    try:
      keys = common.DUT_INFO_KEYS - UmpireClientInfo.KEY_TRANSLATION_BLACK_LIST
      for key in keys:
        value = getattr(self, UmpireClientInfo.KEY_TRANSLATION[key])
        info_dict[key] = value
      for key_prefix in common.DUT_INFO_KEY_PREFIX:
        # Dict of {subkey: value} for the prefix key group.
        # E.g. self.macs is a dict {'eth0': 'xxxx', 'wlan0': 'xxxx'}
        # With prefix 'mac', output should be
        # 'mac.eth0='xxxx', 'mac.wlan0=xxxx'.
        values = getattr(self, UmpireClientInfo.KEY_TRANSLATION[key_prefix])
        for subkey, value in values.iteritems():
          info_dict['%s.%s' % (key_prefix, subkey)] = value
    except KeyError as e:
      raise UmpireClientInfoException(
          'DUT info key not found in KEY_TRANSLATION: %s.' % e)
    except AttributeError as e:
      raise UmpireClientInfoException(
          'Property not found in UmpireClientInfo: %s.' % e)

    logging.debug('Client info_dict: %r', info_dict)
    return info_dict

  def GetDUTInfoComponents(self):
    """Gets DUT info and components for GetUpdateFromCROSPayload call.

    Returns:
      {'x_umpire_dut': X-Umpire-DUT header in dict form,
       'components': components' version/hash for update lookup.}
    """
    return {
        'x_umpire_dut': self._GetXUmpireDUTDict(),
        'components': self._GetComponentsDict()}

  def GetXUmpireDUT(self):
    """Outputs client info for request header X-Umpire-DUT.

    Returns:
      Umpire client info in X-Umpire-DUT format: 'key=value; key=value ...'.
    """
    info_dict = self._GetXUmpireDUTDict()
    output = '; '.join(
        '%s=%s' % (key, info_dict[key]) for key in sorted(info_dict))
    logging.debug('Client X-Umpire-DUT : %r', output)
    # This will be directly sent to HTTP header and we don't want to allow new
    # line characters.
    assert '\n' not in output, (
        'UmpireClientInfo may not have multiple-line data.')
    return output
