#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import subprocess

import factory_common  # pylint: disable=W0611
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

  FACTORY_PAR_PATH = '/usr/local/factory/factory.par'
  CHECKSUM_COMMAND = ['md5sum', FACTORY_PAR_PATH]

  def __init__(self, dut):
    self._dut = dut

  @LazyProperty
  def checksum(self):
    if not os.path.exists(self.FACTORY_PAR_PATH):
      raise IOError('No such file: %s' % self.FACTORY_PAR_PATH)
    return process_utils.CheckOutput(self.CHECKSUM_COMMAND)

  def PushFactoryPar(self):
    """Push factory.par to DUT if DUT is not local machine.

    First checks if DUT already has the same factory.par as us.
    If not, pushs our factory.par to DUT, otherwise, does nothing.
    """

    if self._dut.link.IsLocal():
      return
    try:
      if self.checksum == self._dut.CheckOutput(self.CHECKSUM_COMMAND):
        return
    except subprocess.CalledProcessError:
      # DUT does not have the factory par file, continue.
      pass
    self._dut.link.Push(self.FACTORY_PAR_PATH, self.FACTORY_PAR_PATH)

  def DryRun(self, command):
    """Returns the command that will be executed."""
    if isinstance(command, basestring):
      command = self.FACTORY_PAR_PATH + ' ' + command
    else:
      command = [self.FACTORY_PAR_PATH] + command
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
