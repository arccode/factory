#!/usr/bin/python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO(pihsun): Remove this file when all test lists are in JSON format.

import factory_common  # pylint: disable=unused-import

from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test.test_lists.test_lists import AutomatedSequence
from cros.factory.test.test_lists.test_lists import OperatorTest
from cros.factory.test.test_lists.test_lists import TestGroup
from cros.factory.test.test_lists.test_lists import TestList

def StartStationTest(label, prompt_start):
  OperatorTest(
      label=i18n.StringFormat(_('Start {label}'), label=label),
      pytest_name='station_entry',
      dargs={'prompt_start': prompt_start})


def EndStationTest(label, disconnect_dut):
  OperatorTest(
      label=i18n.StringFormat(_('End {label}'), label=label),
      pytest_name='station_entry',
      dargs={'start_station_tests': False,
             'disconnect_dut': disconnect_dut})


def StationBased(test_list_id, label,
                 dut_options=None,
                 automated_sequence=True,
                 prompt_start=True,
                 prestart_steps=None,
                 disconnect_dut=True):
  """A decorator to add common test items for station-based tests.

  Args:
    dut_options: Override default (e.g. environment variable) DUT options.
    automated_sequence: Wrap the test list in an AutomatedSequence test group,
      preventing any test inside from being run individually.
    prompt_start: Prompt the operator to press the spacebar before the test
      sequence actually begins.  Default is True.
    prestart_steps: A list of callable object that will be called before
      adding StartStationTest.

  Example:

  ::

    dut_options = {'link_class': SSHLink, 'host': None}
    @StationBased('main', 'CoolProduct EVT', dut_options=dut_options,
                  prestart_steps=ScanBarcode)
    def CreateTestLists(test_list):
      # dut_options is automatically set to test_list,
      # you can set other options for test_list here
      with TestGroup(label=_('TestGroupA'), ...):
        ...
      OperatorTest(...)

  Then CreateTestLists() will create a test list named 'main', with
  label 'CoolProduct EVT'.

  And the test list will be::
    main  # (test group)
      ScanBarcode  # (test created by prestart_steps)
      StartStationTest  # (added by this wrapper)
      TestGroupA
        ...
      ...
      Test1
      EndStationTest  # (added by this wrapper)
  """
  if not dut_options:
    dut_options = {}

  def Wrap(CreateTestLists):
    def CreateStationTestList():
      with TestList(test_list_id, label=label) as test_list:
        test_list.options.dut_options = dut_options

        if automated_sequence:
          group = AutomatedSequence(label=label)
        else:
          group = TestGroup(label=label)

        with group:
          if prestart_steps:
            for step in prestart_steps:
              step()
          StartStationTest(label, prompt_start)
          CreateTestLists(test_list)
          EndStationTest(label, disconnect_dut)
    return CreateStationTestList
  return Wrap
