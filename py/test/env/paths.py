# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import getpass
import os
import tempfile

from cros.factory.utils import sys_utils


SCRIPT_PATH = os.path.realpath(__file__)
# Path to factory environment (code and resources)
FACTORY_DIR = os.path.realpath(
    os.path.join(SCRIPT_PATH, '..', '..', '..', '..'))
FACTORY_PYTHON_PACKAGE_DIR = os.path.join(
    FACTORY_DIR, 'py_pkg', 'cros', 'factory')
FACTORY_TOOLKIT_VERSION_PATH = os.path.join(FACTORY_DIR, 'TOOLKIT_VERSION')
FACTORY_FIRMWARE_UPDATER_PATH = os.path.join(
    FACTORY_DIR, 'board', 'chromeos-firmwareupdate')

# Path to factory log on a "real" device.
FACTORY_LOG_PATH_ON_DEVICE = '/var/factory/log/factory.log'

# The root directory for logging and state.
DATA_DIR = os.environ.get(
    'CROS_FACTORY_DATA_DIR',
    (os.path.join(tempfile.gettempdir(), 'factory.%s' % getpass.getuser()))
    if sys_utils.InChroot() else '/var/factory')
# The directory for logs.
DATA_LOG_DIR = os.path.join(DATA_DIR, 'log')
# The directory for testlog data (pytest-related data only).
DATA_TESTLOG_DIR = os.path.join(DATA_DIR, 'testlog')
# The directory for all factory state.
DATA_STATE_DIR = os.path.join(DATA_DIR, 'state')
# The directory for all test logs/state.
DATA_TESTS_DIR = os.path.join(DATA_DIR, 'tests')

CONSOLE_LOG_PATH = os.path.join(DATA_LOG_DIR, 'console.log')
FACTORY_LOG_PATH = os.path.join(DATA_LOG_DIR, 'factory.log')

RUNTIME_VARIABLE_DATA_DIR = os.environ.get('CROS_FACTORY_RUN_PATH',
                                           os.path.join(DATA_DIR, 'run')
                                           if sys_utils.InChroot() else '/run')


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

  factory_par = os.path.join(FACTORY_DIR, 'factory.par')
  if os.path.exists(factory_par):
    return factory_par

  factory_par = os.path.join(FACTORY_DIR, 'factory-mini.par')
  if os.path.exists(factory_par):
    return factory_par

  test_image_factory_mini_par = '/usr/local/factory-mini/factory-mini.par'
  if os.path.exists(test_image_factory_mini_par):
    return test_image_factory_mini_par

  raise EnvironmentError('cannot find factory python archive')
