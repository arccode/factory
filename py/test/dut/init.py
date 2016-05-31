#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A system module providing method to add start up jobs."""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component
from cros.factory.test.env import paths


class FactoryInit(component.DUTComponent):
  """Provides method to add start up jobs using the factory framework.

  The design is to apply the goofy startup flow used in most Chrome OS board.
  In most Chrome OS board, ${FACTORY_ROOT}/init/startup is the entry point to
  run all factory software after device boot. The script execs all executable
  scripts under ${FACTORY_ROOT}/init/main.d and starts goofy.

  Therefore, to add a start up job, we link scripts into the main.d directory,
  and check if we have the startup script installed. If no, a stub startup
  script is pushed to achive our goal.

  For other boards, one can try to make a factory image that runs
  ${FACTORY_ROOT}/init/startup at booting, so the following code can be reused.
  """

  def __init__(self, _dut=None):
    super(FactoryInit, self).__init__(_dut)
    self._factory_root = self._dut.storage.GetFactoryRoot()
    self._init_dir = self._dut.path.join(self._factory_root, 'init')
    self._init_script_dir = self._dut.path.join(self._init_dir, 'main.d')

  def AddFactoryStartUpApp(self, name, script_path):
    """Add a start up application to the board.

    Args:
      name: the name of the job, which can be used when we want to remove it.
      script_path: the actual path of the script to be execute on the board.
          Note that the path is a path on the DUT.
    """
    # Chrome OS test image executes '${FACTORY_ROOT}/init/startup' if
    # file '${FACTORY_ROOT}/enabled' exists.
    self._dut.CheckCall(
        ['touch', self._dut.path.join(self._factory_root, 'enabled')])

    # we first assume that factory toolkit exists, so we can use its startup
    # mechanism. (see init/main.d/README for more detail)
    job_path = self._dut.path.join(self._init_script_dir, name + '.sh')
    self._dut.CheckCall(['mkdir', '-p', self._init_script_dir])
    self._dut.CheckCall(['ln', '-sf', script_path, job_path])
    self._dut.CheckCall(['chmod', '+x', job_path])

    dut_startup_script = self._dut.path.join(self._init_dir, 'startup')
    if not self._dut.path.exists(dut_startup_script):
      # however, if the default startup script doesn't exists (e.g. factory
      # toolkit is not installed), we will create a stub startup script.
      station_startup_script = os.path.join(paths.FACTORY_PATH, 'sh',
                                            'stub_startup.sh')
      self._dut.link.Push(station_startup_script, dut_startup_script)
      self._dut.CheckCall(['chmod', '+x', dut_startup_script])

  def RemoveFactoryStartUpApp(self, name):
    """Remove a start up application on the board.

    Args:
      name: the name of the job used when creating the job.
    """
    job_path = self._dut.path.join(self._init_script_dir, name + '.sh')
    self._dut.CheckCall(['rm', '-f', job_path])
