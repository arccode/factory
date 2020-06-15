# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import pipes
import subprocess
import tempfile

from cros.factory.test.env import paths
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


class FactoryTools:
  """An abstract class for factory tools.

  For some standalone factory tools such as gooftool and hwid, we can either
  execute them using scripts under factory/bin, or using factory python archive.
  This class is an abstract class that unifies the interface of these two
  approaches.
  """
  def Call(self, command, **kargs):
    raise NotImplementedError

  def CheckCall(self, command, **kargs):
    raise NotImplementedError

  def CallOutput(self, command, **kargs):
    raise NotImplementedError

  def CheckOutput(self, command, **kargs):
    raise NotImplementedError

  def Run(self, command):
    """Run a factory tool command.

    Args:
      command: command to execute, e.g. ['hwid', 'generate'] or 'hwid generate'.

    Returns:
      (stdout, stderr, return_code) of the execution results
    """
    with tempfile.TemporaryFile('w+') as stdout:
      with tempfile.TemporaryFile('w+') as stderr:
        return_code = self.Call(command, stdout=stdout, stderr=stderr)
        stdout.seek(0)
        stderr.seek(0)
        return (stdout.read(), stderr.read(), return_code)


class FactoryPythonArchive(FactoryTools):
  """Deploy and invoke the Factory Python Archive (.par) file.

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
      :type dut: cros.factory.device.device_types.DeviceInterface
      local_factory_par: local path to factory.par, If this is None (default
          value), the object will try to find factory.par at default location.
          (see self.local_factory_par)
      remote_factory_par: remote path to save factory.par. If this is None
          (default value), the object will try to save it at default location.
          (see self.remote_factory_par)
    """
    self._dut = dut

    if local_factory_par:
      type_utils.LazyProperty.Override(
          self, 'local_factory_par', local_factory_par)

    if remote_factory_par:
      type_utils.LazyProperty.Override(
          self, 'remote_factory_par', remote_factory_par)

  @type_utils.LazyProperty
  def local_factory_par(self):
    return paths.GetFactoryPythonArchivePath()

  @type_utils.LazyProperty
  def remote_factory_par(self):
    if self._dut.link.IsLocal():
      return self.local_factory_par

    return self._dut.path.join(
        self._dut.storage.GetFactoryRoot(), 'factory.par')

  @type_utils.LazyProperty
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
    if isinstance(command, str):
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


class FactoryBin(FactoryTools):
  """An implementation of FactoryTools which uses scripts under factory/bin."""

  def __init__(self, dut):
    """Constructor of FactoryBin.

    Args:
      :type dut: cros.factory.device.device_types.DeviceInterface
    """
    assert dut.link.IsLocal()
    self._dut = dut

  def DryRun(self, command):
    """Returns the command that will be executed."""
    if not isinstance(command, str):
      command = ' '.join(map(pipes.quote, command))

    command = 'PATH=%s:$PATH %s' % (os.path.join(paths.FACTORY_DIR, 'bin'),
                                    command)
    return command

  def _Preprocess(self, command):
    return self.DryRun(command)

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


def CreateFactoryTools(dut, factory_par_path=None):
  """Get an implementation of FactoryTools depends on arguments.

  If factory/bin exists on DUT, we assume that they are available and working,
  so just returns a FactoryBin instance.

  Otherwise, an instance of FactoryPythonArchive will be returned, and the path
  to factory.par can be specified by `factory_par_path`.

  Args:
    :type dut: cros.factory.device.device_types.DeviceInterface
    factory_par_path: path to factory python archive (on station), or None to
        use the default one.

  Returns:
    an implementation of FactoryTools.
    :rtype: FactoryTools
  """
  if dut.path.exists(dut.path.join(paths.FACTORY_DIR, 'bin')):
    # factory/bin exists, let's use factory/bin
    return FactoryBin(dut)
  return FactoryPythonArchive(dut, local_factory_par=factory_par_path)
