#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611

from cros.factory.test.test_lists.test_lists import (OperatorTest, TestList)
from cros.factory.test.dut import utils

def StartFixtureTest(test_list_id, label_en, label_zh):
  OperatorTest(
      id='StartFixtureTest_%s' % test_list_id,
      label_en=u'Start %s' % label_en,
      label_zh=u'开始 %s' % label_zh,
      pytest_name='fixture_entry')


def EndFixtureTest(test_list_id, label_en, label_zh):
  OperatorTest(
      id='EndFixtureTest_%s' % test_list_id,
      label_en=u'End %s' % label_en,
      label_zh=u'结束 %s' % label_zh,
      pytest_name='fixture_entry',
      dargs={'start_fixture_tests': False})


def FixtureBased(test_list_id, label_en, label_zh, dut_options=None):
  """ A decorator to add common test items for fixture based tests

      Example:

      dut_options = {'dut_class': 'SSHTarget', 'host': 'dynamic'}
      @FixtureBased('main', 'CoolProduct EVT', dut_options)
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
    def CreateFixtureTestList():
      utils.PrepareLink(**dut_options)
      with TestList(test_list_id, label_en) as test_list:
        test_list.dut_options = dut_options
        StartFixtureTest(test_list_id, label_en, label_zh)
        CreateTestLists(test_list)
        EndFixtureTest(test_list_id, label_en, label_zh)
    return CreateFixtureTestList
  return Wrap
