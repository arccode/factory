#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import subprocess

import factory_common  # pylint: disable=W0611
from cros.factory.test.env import paths
from cros.factory.utils import process_utils
from cros.factory.utils.type_utils import LazyProperty


class FactoryPythonArchive(object):
  """ Deploy and invoke the Factory Python Archive (.par) file.

  Some factory programs may need to run on restricted environments without full
  Goofy configuration (for example, gooftool and hwid both highly depends on
  running locally within a ChromeOS system). Instead of porting these programs
  to support remote DUT API, we want to push the executable factory archive to
  remote system and simply invoke the commands.
  """

  # since path to local factory.par and remote factory.par might be different,
  # we just redirect the factory.par as md5sum(1)'s stdin, so that the filename
  # column will always be '-'
  CHECKSUM_COMMAND = 'md5sum <{0}'

  def __init__(self, dut, local_factory_par=None, remote_factory_par=None):
    """Constructor of FactoryPythonArchive.

    Args:
      :type dut: cros.factory.device.board.DeviceBoard
      local_factory_par: local path to factory.par, If this is None (default
          value), the object will try to find factory.par at default location.
          (see self.local_factory_par)
      remote_factory_par: remote path to save factory.par. If this is None
          (default value), the object will try to save it at default location.
          (see self.remote_factory_par)
    """
    self._dut = dut

    if local_factory_par:
      LazyProperty.Override(self, 'local_factory_par', local_factory_par)

    if remote_factory_par:
      LazyProperty.Override(self, 'remote_factory_par', remote_factory_par)

  @LazyProperty
  def local_factory_par(self):
    return paths.GetFactoryPythonArchivePath()

  @LazyProperty
  def remote_factory_par(self):
    if self._dut.link.IsLocal():
      return self.local_factory_par

    return self._dut.path.join(
        self._dut.storage.GetFactoryRoot(), 'factory.par')

  @LazyProperty
  def checksum(self):
    if not os.path.exists(self.local_factory_par):
      raise IOError('No such file: %s' % self.local_factory_par)
    return process_utils.CheckOutput(
        self.CHECKSUM_COMMAND.format(self.local_factory_par), shell=True)

  def PushFactoryPar(self):
    """Push factory.par to DUT if DUT is not local machine.

    First checks if DUT already has the same factory.par as us.
    If not, pushs our factory.par to DUT, otherwise, does nothing.
    """
    if self._dut.link.IsLocal():
      return
    try:
      if self.checksum == self._dut.CheckOutput(
          self.CHECKSUM_COMMAND.format(self.remote_factory_par)):
        return
    except subprocess.CalledProcessError:
      # DUT does not have the factory par file, continue.
      pass
    self._dut.link.Push(self.local_factory_par, self.remote_factory_par)

  def DryRun(self, command):
    """Returns the command that will be executed."""
    if isinstance(command, basestring):
      command = 'sh ' + self.remote_factory_par + ' ' + command
    else:
      command = ['sh', self.remote_factory_par] + command
    return command

  def _Preprocess(self, command):
    self.PushFactoryPar()
    return self.DryRun(command)

  # Delegate to dut API
  def Call(self, command, **kargs):
    command = self._Preprocess(command)
    return self._dut.Call(command, **kargs)

  def CheckCall(self, command, **kargs):
    command = self._Preprocess(command)
    return self._dut.CheckCall(command, **kargs)

  def CheckOutput(self, command, **kargs):
    command = self._Preprocess(command)
    return self._dut.CheckOutput(command, **kargs)

  def CallOutput(self, command, **kargs):
    command = self._Preprocess(command)
    return self._dut.CallOutput(command, **kargs)
