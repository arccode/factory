# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
from unittest import mock

from cros.factory.probe_info_service.app_engine import probe_metainfo_connector


class DataStoreProbeMetaInfoConnector(unittest.TestCase):
  def setUp(self):
    self._patcher = mock.patch('google.auth')
    mock_google_auth = self._patcher.start()
    mock_google_auth.default.return_value = (mock.Mock(), None)
    self.addCleanup(self._patcher.stop)
    # pylint: disable=protected-access
    self._connector = (
        probe_metainfo_connector._DataStoreProbeMetaInfoConnector())
    # pylint: enable=protected-access
    self._connector.Clean()

  def testQualProbeMetaInfo(self):
    data = self._connector.GetQualProbeMetaInfo(1)
    # Default value set should be returned.
    self.assertIsNone(data.last_tested_probe_info_fp)
    self.assertIsNone(data.last_probe_info_fp_for_overridden)

    data.last_probe_info_fp_for_overridden = 'bad_fp'
    self._connector.UpdateQualProbeMetaInfo(1, data)
    data = self._connector.GetQualProbeMetaInfo(1)
    self.assertIsNone(data.last_tested_probe_info_fp)
    self.assertEqual(data.last_probe_info_fp_for_overridden, 'bad_fp')

    data.last_tested_probe_info_fp = 'fpfpfp'
    self._connector.UpdateQualProbeMetaInfo(1, data)

    data2 = self._connector.GetQualProbeMetaInfo(2)
    # Default value set should be returned.
    self.assertIsNone(data2.last_tested_probe_info_fp)

    data1 = self._connector.GetQualProbeMetaInfo(1)
    self.assertEqual(data1.last_tested_probe_info_fp, 'fpfpfp')


if __name__ == '__main__':
  unittest.main()
