# -*- mode: python; coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""A test_list for TSAB (TouchScreen calibration on AB panel) station."""


import factory_common  # pylint: disable=W0611
from cros.factory.test.test_lists.test_lists import OperatorTest, TestList


def CreateTestLists():
  """Creates test list.

  This is the external interface to test list creation (called by the
  test list builder).  This function is required and its name cannot
  be changed.
  """
  with TestList('tsab_station', 'Touchscreen calibration on AB panel'):
    OperatorTest(
        id='Touchscreen_Calibration',
        label_zh=u'触控面板',
        pytest_name='touchscreen_calibration')
