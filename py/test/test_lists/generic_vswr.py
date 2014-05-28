# -*- mode: python; coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""A test_list for VSWR (Voltage Standing Wave Ratio) station.

Test item is executed manually based on the input configuration. There are two
main groups:
  Production: used for test station on the factory line.
  OfflineDebug: used for offline debugging. Outputs verbose information and
      does not connect to shop floor server.
"""


import factory_common  # pylint: disable=W0611
from cros.factory.test.test_lists.test_lists import AutomatedSequence
from cros.factory.test.test_lists.test_lists import OperatorTest
from cros.factory.test.test_lists.test_lists import TestGroup
from cros.factory.test.test_lists.test_lists import TestList


_SHOPFLOOR_IP = '10.3.0.11'
_SHOPFLOOR_PORT = 8082
_PARAMETER_BASE_NAME = 'vswr.%s.%s.params'
_DEFAULT_TIMEZONE = 'Asia/Taipei'


def _SyncShopfloor():
  OperatorTest(
      id='SyncShopfloor',
      pytest_name='flush_event_logs',
      dargs={'disable_update': True},
      label_zh=u'同步事件记录')


def CreateTestLists():
  '''Creates test list.

  This is the external interface to test list creation (called by the
  test list builder).  This function is required and its name cannot
  be changed.
  '''
  with TestList('vswr_station', 'VSWR Station') as test_list:
    test_list.options.auto_run_on_start = False
    # Override some shopfloor settings.
    test_list.options.sync_event_log_period_secs = 30
    test_list.options.sync_time_period_secs = 300
    test_list.options.update_period_secs = None
    test_list.options.shopfloor_server_url = 'http://%s:%s/' % (
        _SHOPFLOOR_IP, _SHOPFLOOR_PORT)

    with TestGroup(id='Production', label_zh='生产线端测试'):
      with AutomatedSequence(id='WiFi', label_zh='WiFi 天线'):
        OperatorTest(
            id='VSWR',
            label_en='VSWR WiFi Antenna Test',
            label_zh=u'VSWR WiFi 天线测试',
            pytest_name='vswr',
            dargs={
                'config_path': (
                    'rf/vswr/' + _PARAMETER_BASE_NAME % ('prod', 'wifi')),
                'timezone': _DEFAULT_TIMEZONE,
                'load_from_shopfloor': True})
        _SyncShopfloor()

      with AutomatedSequence(id='Cellular', label_zh='Cellular 天线'):
        OperatorTest(
            id='VSWR',
            label_en='VSWR Cellular Antenna Test',
            label_zh=u'VSWR Cellular 天线测试',
            pytest_name='vswr',
            dargs={
                'config_path': (
                    'rf/vswr/' + _PARAMETER_BASE_NAME % ('prod', 'cellular')),
                'timezone': _DEFAULT_TIMEZONE,
                'load_from_shopfloor': True})
        _SyncShopfloor()

      with AutomatedSequence(id='LTE', label_zh='LTE 天线'):
        OperatorTest(
            id='VSWR',
            label_en='VSWR LTE Antenna Test',
            label_zh=u'VSWR LTE 天线测试',
            pytest_name='vswr',
            dargs={
                'config_path': (
                    'rf/vswr/' + _PARAMETER_BASE_NAME % ('prod', 'lte')),
                'timezone': _DEFAULT_TIMEZONE,
                'load_from_shopfloor': True})
        _SyncShopfloor()

    with TestGroup(id='OfflineDebug', label_zh='非产线除错用'):
      OperatorTest(
          id='VSWRDebugWiFi',
          label_en='VSWR WiFi Antenna Debug',
          label_zh=u'VSWR WiFi 天线非产线除错用',
          pytest_name='vswr',
          dargs={'config_path': _PARAMETER_BASE_NAME % ('debug', 'wifi'),
                 'timezone': _DEFAULT_TIMEZONE,
                 'load_from_shopfloor': False})
      OperatorTest(
          id='VSWRDebugCellular',
          label_en='VSWR Cellular Antenna Debug',
          label_zh=u'VSWR Cellular 天线非产线除错用',
          pytest_name='vswr',
          dargs={'config_path': _PARAMETER_BASE_NAME % ('debug', 'cellular'),
                 'timezone': _DEFAULT_TIMEZONE,
                 'load_from_shopfloor': False})
      OperatorTest(
          id='VSWRDebugLTE',
          label_en='VSWR LTE Antenna Debug',
          label_zh=u'VSWR LTE 天线非产线除错用',
          pytest_name='vswr',
          dargs={'config_path': _PARAMETER_BASE_NAME % ('debug', 'lte'),
                 'timezone': _DEFAULT_TIMEZONE,
                 'load_from_shopfloor': False})
