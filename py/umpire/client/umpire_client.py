# -*- coding: utf-8 -*-
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Module to maintain umpire client information."""


import logging

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.common import DUT_INFO_KEYS, DUT_INFO_KEY_PREFIX
from cros.factory import system
from cros.factory.tools import build_board

# The component keys in the return value of GetUpdate RPC call.
COMPONENT_KEYS = {
  'rootfs_test',
  'rootfs_release',
  'firmware_ec',
  'firmware_bios',
  'firmware_pd',
  'hwid',
  'device_factory_toolkit'
}


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
    """Gets DUT info and components for Umpire GetUpdate call.

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
      'board': 'board',
      'firmware': 'firmware_version',
      'ec': 'ec_version',
      'pd': 'pd_version',
      'mac': 'macs',
      'stage': 'stage'
  }

  VARIANT_FIELDS = [
      'serial_number', 'mlb_serial_number', 'firmware_version',
      'ec_version', 'pd_version', 'macs', 'stage']

  def __init__(self):
    super(UmpireClientInfo, self).__init__()
    # serial_number, mlb_serial_number, firmware, ec and wireless mac address
    # are detected in system.SystemInfo module.
    self.serial_number = None
    self.mlb_serial_number = None
    self.board = build_board.BuildBoard().full_name
    self.firmware_version = None
    self.ec_version = None
    self.pd_version = None
    self.macs = dict()
    self.stage = None

    self.Update()

  def Update(self):
    """Updates client info.

    Returns:
      True if client info is changed.
    """
    # TODO(cychiang) Set fields from SystemInfo
    system_info = system.SystemInfo()
    new_info = dict()
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
    """Gets infomation needed for Umpire GetUpdate call.

    Returns:
      A component dict:
        ‘rootfs_test’: version_string,
        ‘rootfs_release’: version_string,
        ‘firmware_ec’: version_string,
        ‘firmware_bios’: version_string,
        ‘firmware_pd’: version_string,
        ‘hwid’: version_string (checksum in hwid db)
        ‘device_factory_toolkit’: md5sum_hash_string.
    """
    components = dict()
    system_info = system.SystemInfo()
    components['rootfs_test'] = system_info.factory_image_version
    components['rootfs_release'] = system_info.release_image_version
    components['firmware_ec'] = system_info.ec_version
    components['firmware_bios'] = system_info.firmware_version
    components['firmware_pd'] = system_info.pd_version
    components['hwid'] = system_info.hwid_database_version
    components['device_factory_toolkit'] = system_info.factory_md5sum

    return components

  def _GetXUmpireDUTDict(self):
    """Gets X-Umpire-DUT dict by translating keys."""
    info_dict = dict()
    try:
      for key in DUT_INFO_KEYS:
        value = getattr(self, UmpireClientInfo.KEY_TRANSLATION[key])
        info_dict[key] = value
      for key_prefix in DUT_INFO_KEY_PREFIX:
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
    """Gets DUT info and components for Umpire GetUpdate call.

    Returns:
      {'x_umpire_dut': X-Umpire-DUT header in dict form,
       'components': components' version/hash for update lookup.}
    """
    dut_info = dict()
    dut_info['x_umpire_dut'] = self._GetXUmpireDUTDict()
    dut_info['components'] = self._GetComponentsDict()
    return dut_info

  def GetXUmpireDUT(self):
    """Outputs client info for request header X-Umpire-DUT.

    Returns:
      Umpire client info in X-Umpire-DUT format: 'key=value; key=value ...'.
    """
    info_dict = self._GetXUmpireDUTDict()
    output = '; '.join(
        ['%s=%s' % (key, info_dict[key]) for key in sorted(info_dict)])
    logging.debug('Client X-Umpire-DUT : %r', output)
    return output
