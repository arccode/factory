#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611

from cros.factory.test.test_lists.test_lists import AutomatedSequence
from cros.factory.test.test_lists.test_lists import OperatorTest
from cros.factory.test.test_lists.test_lists import TestGroup
from cros.factory.test.test_lists.test_lists import TestList

def StartStationTest(test_list_id, label_en, label_zh, prompt_start):
  OperatorTest(
      id='StartStationTest_%s' % test_list_id,
      label_en=u'Start %s' % label_en,
      label_zh=u'开始 %s' % label_zh,
      pytest_name='station_entry',
      dargs={'prompt_start': prompt_start})


def EndStationTest(test_list_id, label_en, label_zh):
  OperatorTest(
      id='EndStationTest_%s' % test_list_id,
      label_en=u'End %s' % label_en,
      label_zh=u'结束 %s' % label_zh,
      pytest_name='station_entry',
      dargs={'start_station_tests': False})


def StationBased(test_list_id, label_en, label_zh,
                 dut_options=None,
                 automated_sequence=True,
                 prompt_start=True):
  """A decorator to add common test items for station-based tests.

  Args:
    automated_sequence: Wrap the test list in an AutomatedSequence test group,
      preventing any test inside from being run individually.
    prompt_start: Prompt the operator to press the spacebar before the test
      sequence actually begins.  Default is True.

  Example:

  ::

    dut_options = {'link_class': SSHLink, 'host': None}
    @StationBased('main', 'CoolProduct EVT', dut_options)
    def CreateTestLists(test_list):
      # dut_options is automatically set to test_list,
      # you can set other options for test_list here
      with TestGroup(...):
        ...
      OperatorTest(...)

  Then CreateTestLists() will create a test list named 'main', with
  label 'CoolProduct EVT'.
  """
  if not dut_options:
    dut_options = {}

  def Wrap(CreateTestLists):
    def CreateStationTestList():
      with TestList(test_list_id, label_en) as test_list:
        test_list.dut_options = dut_options

        if automated_sequence:
          group = AutomatedSequence(
              id=test_list_id, label_en=label_en, label_zh=label_zh)
        else:
          group = TestGroup(
              id=test_list_id, label_en=label_en, label_zh=label_zh)

        with group:
          StartStationTest(test_list_id, label_en, label_zh, prompt_start)
          CreateTestLists(test_list)
          EndStationTest(test_list_id, label_en, label_zh)
    return CreateStationTestList
  return Wrap
