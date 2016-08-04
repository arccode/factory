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
from cros.factory.test.test_lists.test_lists import TestList


_SHOPFLOOR_IP = '10.3.0.12'
_SHOPFLOOR_PORT = 8082
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
  with TestList('vswr_station', 'Generic VSWR Station') as test_list:
    test_list.options.auto_run_on_start = False

    # Override some shopfloor settings.
    test_list.options.sync_event_log_period_secs = 30
    test_list.options.sync_time_period_secs = 300
    test_list.options.update_period_secs = None

    # If you're using old shopfloor then add a slash at the end of the URL:
    # 'http://%s:%s/'.  If you're using umpire then don't add the slash.
    test_list.options.shopfloor_server_url = 'http://%s:%s' % (
        _SHOPFLOOR_IP, _SHOPFLOOR_PORT)

    # TODO(littlecvr): Should separate prepressed and postpressed in order to
    #                  prevent partners using the wrong one in the factory?
    with AutomatedSequence(id='VSWRPrepressed',
                           label_en='VSWR Prepressed', label_zh='VSWR 组装前'):
      OperatorTest(
          id='VSWR',
          label_en='VSWR Antenna Test',
          label_zh=u'VSWR 天线测试',
          pytest_name='vswr',
          dargs={
              'event_log_name': 'vswr_prepressed',
              'shopfloor_log_dir': 'vswr_prepressed',
              'config_path': 'rf/vswr/vswr_config.prepressed.yaml',
              'timezone': _DEFAULT_TIMEZONE,
              'load_from_shopfloor': True})
      _SyncShopfloor()

    with AutomatedSequence(id='VSWRPostpressed',
                           label_en='VSWR Postpressed', label_zh='VSWR 组装后'):
      OperatorTest(
          id='VSWR',
          label_en='VSWR Antenna Test',
          label_zh=u'VSWR 天线测试',
          pytest_name='vswr',
          dargs={
              'event_log_name': 'vswr_postpressed',
              'shopfloor_log_dir': 'vswr_postpressed',
              'config_path': 'rf/vswr/vswr_config.postpressed.yaml',
              'timezone': _DEFAULT_TIMEZONE,
              'load_from_shopfloor': True})
      _SyncShopfloor()
