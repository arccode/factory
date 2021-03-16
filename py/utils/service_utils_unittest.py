#!/usr/bin/env python3
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
from unittest import mock

from cros.factory.utils import service_utils
from cros.factory.utils.service_utils import Status


class ServiceManagerTest(unittest.TestCase):

  def setUp(self):
    self.dut = mock.MagicMock()

  def testParseServiceStatus(self):
    self.assertEqual(
        service_utils.ParseServiceStatus('service start/running, process 99'),
        Status.START)
    self.assertEqual(service_utils.ParseServiceStatus('service stop/waiting'),
                     Status.STOP)
    self.assertEqual(
        service_utils.ParseServiceStatus('service: Unknown instance:'),
        Status.UNKNOWN)

  @mock.patch('cros.factory.utils.service_utils.SetServiceStatus')
  def testGetService(self, set_status_mock):
    set_status_mock.return_value = Status.START
    self.assertEqual(service_utils.GetServiceStatus('started', dut=self.dut),
                     Status.START)
    set_status_mock.assert_called_once_with('started', None, self.dut)

    set_status_mock.reset_mock()
    set_status_mock.side_effect = Exception('message')
    with self.assertRaises(Exception):
      service_utils.GetServiceStatus('raise_exception', dut=self.dut)
    set_status_mock.assert_called_once_with('raise_exception', None, self.dut)

  @mock.patch('cros.factory.utils.service_utils.SetServiceStatus')
  def testGetServiceIgnoreFailure(self, set_status_mock):
    set_status_mock.side_effect = Exception('message')
    self.assertEqual(
        service_utils.GetServiceStatus('raise_exception', True, dut=self.dut),
        None)
    set_status_mock.assert_called_once_with('raise_exception', None, self.dut)

  @mock.patch('cros.factory.utils.process_utils.CheckOutput')
  @mock.patch('cros.factory.utils.service_utils.ParseServiceStatus')
  def testSetServiceStatusWithoutDUT(self, parse_status_mock,
                                     check_output_mock):
    commands = {
        None: 'status',
        Status.START: 'start',
        Status.STOP: 'stop'}

    for status, cmd in commands.items():
      check_output_mock.reset_mock()
      parse_status_mock.reset_mock()

      output = cmd + '_result'
      check_output_mock.return_value = output
      parse_status_mock.return_value = status

      self.assertEqual(service_utils.SetServiceStatus('service', status),
                       status)
      check_output_mock.assert_called_once_with([cmd, 'service'])
      parse_status_mock.assert_called_once_with(output)

  @mock.patch('cros.factory.utils.service_utils.ParseServiceStatus')
  def testSetServiceStatusWithDUT(self, parse_status_mock):
    commands = {
        None: 'status',
        Status.START: 'start',
        Status.STOP: 'stop'}

    for status, cmd in commands.items():
      self.dut.CheckOutput.reset_mock()
      parse_status_mock.reset_mock()

      output = cmd + '_result'
      self.dut.CheckOutput.return_value = output
      parse_status_mock.return_value = status

      self.assertEqual(
          service_utils.SetServiceStatus('service', status, self.dut), status)
      self.dut.CheckOutput.assert_called_once_with([cmd, 'service'])
      parse_status_mock.assert_called_once_with(output)

  @mock.patch('cros.factory.utils.service_utils.SetServiceStatus')
  @mock.patch('cros.factory.utils.service_utils.GetServiceStatus')
  def testServiceManager(self, get_status_mock, set_status_mock):
    get_status_return_mapping = {
        'started_and_disable': Status.START,
        'started_and_enable': Status.START,
        'stopped_and_disable': Status.STOP,
        'stopped_and_enable': Status.STOP,
    }
    set_status_return_mapping = [
        (service, status)
        for service in ('started_and_disable', 'stopped_and_enable')
        for status in (Status.START, Status.STOP)
    ]

    def GetStatusSideEffect(*args, **unused_kwargs):
      return get_status_return_mapping[args[0]]

    def SetStatusSideEffect(*args, **unused_kwargs):
      return args[1]

    get_status_mock.side_effect = GetStatusSideEffect
    set_status_mock.side_effect = SetStatusSideEffect

    sm = service_utils.ServiceManager(dut=self.dut)
    sm.SetupServices(
        enable_services=['stopped_and_enable', 'started_and_enable'],
        disable_services=['stopped_and_disable', 'started_and_disable'])
    sm.RestoreServices()

    for service in get_status_return_mapping:
      get_status_mock.assert_any_call(service, dut=self.dut)

    for service, status in set_status_return_mapping:
      set_status_mock.assert_any_call(service, status, self.dut)


if __name__ == '__main__':
  unittest.main()
