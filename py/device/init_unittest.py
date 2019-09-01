#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for Init."""

import posixpath
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.device.init import FactoryInit
from cros.factory.device.storage import Storage
from cros.factory.device import types
from cros.factory.test.env import paths


class FactoryInitTest(unittest.TestCase):

  def setUp(self):
    self._factory_root = '/usr/local/factory'
    self._device = mock.create_autospec(types.DeviceInterface)
    self._device.storage = mock.create_autospec(Storage)
    self._device.storage.GetFactoryRoot.return_value = self._factory_root
    self._device.link = mock.create_autospec(types.DeviceLink)
    self._device.path = posixpath
    self._init = FactoryInit(self._device)

  def tearDown(self):
    pass

  def testAddFactoryStartUpApp(self):
    name = 'offline-test'
    script = '/usr/local/factory/sh/offline-test.sh'
    job_path = self._factory_root + '/init/main.d/' + name + '.sh'
    dut_startup_script = self._factory_root + '/init/startup'
    station_startup_script = posixpath.join(
        paths.FACTORY_DIR, 'sh', 'stub_startup.sh')

    self._device.path.exists = mock.Mock(
        spec=posixpath.exists, return_value=False)

    self._init.AddFactoryStartUpApp(name, script)

    calls = []
    calls.append(mock.call(['touch', self._factory_root + '/enabled']))
    calls.append(
        mock.call(['mkdir', '-p', self._factory_root + '/init/main.d']))
    calls.append(mock.call(['ln', '-sf', script, job_path]))
    calls.append(mock.call(['chmod', '+x', job_path]))
    calls.append(mock.call(['chmod', '+x', dut_startup_script]))

    self._device.CheckCall.assert_has_calls(calls)
    self._device.path.exists.assert_called_with(dut_startup_script)
    self._device.link.Push.assert_called_with(
        station_startup_script, dut_startup_script)

  def testRemoveFactoryStartUpApp(self):
    name = 'offline-test'
    job_path = self._factory_root + '/init/main.d/' + name + '.sh'

    self._init.RemoveFactoryStartUpApp(name)

    self._device.CheckCall.assert_called_with(['rm', '-f', job_path])


if __name__ == '__main__':
  unittest.main()
