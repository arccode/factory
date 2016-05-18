#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for Init."""

import mock
import posixpath
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.device import board
from cros.factory.device import link
from cros.factory.device.init import FactoryInit
from cros.factory.device.storage import Storage
from cros.factory.test.env import paths


class FactoryInitTest(unittest.TestCase):

  def setUp(self):
    self._factory_root = '/usr/local/factory'
    self._dut = mock.create_autospec(board.DeviceBoard)
    self._dut.storage = mock.create_autospec(Storage)
    self._dut.storage.GetFactoryRoot.return_value = self._factory_root
    self._dut.link = mock.create_autospec(link.DeviceLink)
    self._dut.path = posixpath
    self._init = FactoryInit(self._dut)

  def tearDown(self):
    pass

  def testAddFactoryStartUpApp(self):
    name = 'offline-test'
    script = '/usr/local/factory/sh/offline-test.sh'
    job_path = self._factory_root + '/init/main.d/' + name + '.sh'
    dut_startup_script = self._factory_root + '/init/startup'
    station_startup_script = posixpath.join(paths.FACTORY_PATH, 'sh',
                                            'stub_startup.sh')

    self._dut.path.exists = mock.Mock(spec=posixpath.exists,
                                      return_value=False)

    self._init.AddFactoryStartUpApp(name, script)

    calls = []
    calls.append(mock.call(['touch', self._factory_root + '/enabled']))
    calls.append(
        mock.call(['mkdir', '-p', self._factory_root + '/init/main.d']))
    calls.append(mock.call(['ln', '-sf', script, job_path]))
    calls.append(mock.call(['chmod', '+x', job_path]))
    calls.append(mock.call(['chmod', '+x', dut_startup_script]))

    self._dut.CheckCall.assert_has_calls(calls)
    self._dut.path.exists.assert_called_with(dut_startup_script)
    self._dut.link.Push.assert_called_with(
        station_startup_script, dut_startup_script)

  def testRemoveFactoryStartUpApp(self):
    name = 'offline-test'
    job_path = self._factory_root + '/init/main.d/' + name + '.sh'

    self._init.RemoveFactoryStartUpApp(name)

    self._dut.CheckCall.assert_called_with(['rm', '-f', job_path])


if __name__ == '__main__':
  unittest.main()
