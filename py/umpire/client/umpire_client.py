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


class UmpireClientInfoException(Exception):
  pass


class UmpireClientInfo(object):
  """Class to maintain client side info that is related to Umpire.

  For each DUT, an UmpireClientInfo object is maintained by UmpireServerProxy.
  """
  # Translated keys in DUT_INFO_KEYS to attributes used in UmpireClientInfo.
  # DUT_INFO_KEYS are used in Output() for X-Umpire-DUT.
  KEY_TRANSLATION = {
      'sn': 'serial_number',
      'mlb_sn': 'mlb_serial_number',
      'board': 'board',
      'firmware': 'firmwave_version',
      'ec': 'ec_version',
      'mac': 'macs'
  }

  VARIANT_FIELDS = [
      'serial_number', 'mlb_serial_number', 'firmware_version',
      'ec_version', 'macs']

  def __init__(self):
    # serial_number, mlb_serial_number, firmware, ec and wireless mac address
    # are detected in system.SystemInfo module.
    self.serial_number = None
    self.mlb_serial_number = None
    self.board = build_board.BuildBoard().full_name
    self.firmware_version = None
    self.ec_version = None
    self.macs = dict()

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
    return changed

  def GetInfoDictForGetUpdate(self):
    """Gets infomation for Umpire XMLRPC GetUpdate call."""
    # TODO(cychiang)
    raise NotImplementedError

  def Output(self):
    """Outputs client info for request header X-Umpire-DUT.

    Returns:
      Umpire client info in X-Umpire-DUT format: 'key=value; key=value ...'.
    """
    info = []
    try:
      for key in DUT_INFO_KEYS:
        value = getattr(self, UmpireClientInfo.KEY_TRANSLATION[key])
        info.append('%s=%s' % (key, value))
      for key_prefix in DUT_INFO_KEY_PREFIX:
        # Dict of {subkey: value} for the prefix key group.
        # E.g. self.macs is a dict {'eth0': 'xxxx', 'wlan0': 'xxxx'}
        # With prefix 'mac', output should be
        # 'mac.eth0='xxxx', 'mac.wlan0=xxxx'.
        values = getattr(self, UmpireClientInfo.KEY_TRANSLATION[key_prefix])
        for subkey, value in values.iteritems():
          info.append('%s.%s=%s' % (key_prefix, subkey, value))
    except KeyError as e:
      raise UmpireClientInfoException(
          'DUT info key not found in KEY_TRANSLATION: %s.' % e)
    except AttributeError as e:
      raise UmpireClientInfoException(
          'Property not found in UmpireClientInfo: %s.' % e)

    logging.debug('Client info : %s', info)
    output = '; '.join(info)
    return output
