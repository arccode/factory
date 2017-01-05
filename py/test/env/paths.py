#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import getpass
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import file_utils
from cros.factory.utils import sys_utils


SCRIPT_PATH = os.path.realpath(__file__)
# Path to factory envrionment (code and resources)
FACTORY_PATH = os.path.realpath(
    os.path.join(SCRIPT_PATH, '..', '..', '..', '..'))
FACTORY_PACKAGE_PATH = os.path.join(FACTORY_PATH, 'py_pkg', 'cros', 'factory')
FACTORY_MD5SUM_PATH = os.path.join(FACTORY_PATH, 'MD5SUM')
FIRMWARE_UPDATER_PATH = os.path.join(
    FACTORY_PATH, 'board', 'chromeos-firmwareupdate')


# Path to factory log on a "real" device.
FACTORY_LOG_PATH_ON_DEVICE = '/var/factory/log/factory.log'


def GetFactoryRoot(subdir=None):
  """Returns the root for logging and state.

  This is usually /var/log, or /tmp/factory.$USER if in the chroot, but may be
  overridden by the CROS_FACTORY_ROOT environment variable.

  Creates the directory it doesn't exist.

  Args:
   subdir: If not None, returns that subdirectory.
  """
  ret = (os.environ.get('CROS_FACTORY_ROOT') or
         (('/tmp/factory.%s' % getpass.getuser())
          if sys_utils.InChroot() else '/var/factory'))
  if subdir:
    ret = os.path.join(ret, subdir)
  file_utils.TryMakeDirs(ret)
  return ret


def GetLogRoot():
  """Returns the root for logs"""
  return GetFactoryRoot('log')


def GetStateRoot():
  """Returns the root for all factory state."""
  return GetFactoryRoot('state')


def GetTestDataRoot():
  """Returns the root for all test logs/state."""
  return GetFactoryRoot('tests')


def GetConsoleLogPath():
  """Returns the path to console.log file."""
  return os.path.join(GetLogRoot(), 'console.log')


def GetFactoryLogPath():
  """Returns the path to factory.log file."""
  return os.path.join(GetLogRoot(), 'factory.log')


def GetRuntimeVariableDataPath():
  """Returns the root for logging and state.

  Returns:
    /run, or GetFactoryRoot("run") if in the chroot, may be overridden
    by the CROS_FACTORY_RUN_PATH environment variable.
  """
  return (os.environ.get('CROS_FACTORY_RUN_PATH') or
          (GetFactoryRoot('run') if sys_utils.InChroot() else '/run'))


def GetFactoryPythonArchivePath():
  """Returns path to a factory python archive.

  This function trys to find a factory python archive.
  If factory toolkit is currently run with a python archive, this function will
  return path to that python archive, otherwise, this function will try to find
  factory.par in default paths.

  If we can't find any, an exception will be raised.
  """

  factory_par = sys_utils.GetRunningFactoryPythonArchivePath()
  if factory_par:
    return factory_par

  factory_par = os.path.join(FACTORY_PATH, 'factory.par')
  if os.path.exists(factory_par):
    return factory_par

  factory_par = os.path.join(FACTORY_PATH, 'factory-mini.par')
  if os.path.exists(factory_par):
    return factory_par

  test_image_factory_mini_par = '/usr/local/factory-mini/factory-mini.par'
  if os.path.exists(test_image_factory_mini_par):
    return test_image_factory_mini_par

  raise EnvironmentError('cannot find factory python archive')
