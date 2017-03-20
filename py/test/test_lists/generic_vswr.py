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


import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import _
from cros.factory.test.test_lists.station_based_test_list import StationBased
from cros.factory.test.test_lists.test_lists import OperatorTest

_SHOPFLOOR_IP = '10.3.0.12'
_SHOPFLOOR_PORT = 8082
_DEFAULT_TIMEZONE = 'Asia/Taipei'
_SERIAL_NUMBER_KEY = 'antenna_serial_number'


@StationBased('vswr_station', _('VSWR Station'))
def CreateTestLists(test_list):
  # If you're using old shopfloor then add a slash at the end of the URL:
  # 'http://%s:%s/'.  If you're using umpire then don't add the slash.
  test_list.options.shopfloor_server_url = 'http://%s:%s' % (
      _SHOPFLOOR_IP, _SHOPFLOOR_PORT)

  OperatorTest(
      id='scan',
      label=_('Scan the serial number'),
      pytest_name='scan',
      dargs={
          'label': _('Scan the serial number'),
          'shared_data_key': _SERIAL_NUMBER_KEY
      })

  OperatorTest(
      id='VSWR',
      label=_('VSWR Antenna Test'),
      pytest_name='vswr',
      dargs={
          'event_log_name': 'vswr_sample',
          'shopfloor_log_dir': 'vswr_sample',
          'config_path': 'vswr_config.sample.yaml',
          'serial_number_key': _SERIAL_NUMBER_KEY,
          'timezone': _DEFAULT_TIMEZONE,
          'load_from_shopfloor': False
      })

  OperatorTest(
      id='SyncShopfloor',
      label=_('Sync Shopfloor'),
      pytest_name='flush_event_logs',
      dargs={'disable_update': True})

  OperatorTest(
      id='Barrier',
      label=_('Barrier'),
      pytest_name='summary',
      never_fails=True,
      disable_abort=True,
      dargs={
          'disable_input_on_fail': False,
          'bft_fixture': None,
          'pass_without_prompt': False,
          'accessibility': False
      })
