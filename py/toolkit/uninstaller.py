#!/usr/bin/env python3
#
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory toolkit uninstaller.

Remove all factory toolkit related files on CrOS device.
"""

import argparse
import os
import sys

from cros.factory.test.env import paths
from cros.factory.tools import install_symlinks
from cros.factory.utils import file_utils
from cros.factory.utils import log_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils

HELP_HEADER = """
Uninstall the factory toolkit on a CrOS device.
"""

FACTORY_PATHS = [
    '/var/factory', '/run/factory', paths.FACTORY_DIR,
    '/var/log/factory-init.log', '/var/log/factory-session.log',
    '/var/log/factory.log'
]


def AssertEnvironment():
  if not sys_utils.InCrOSDevice():
    raise Exception(
        "ERROR: You're not on a CrOS device (for more details, please "
        'check sys_utils.py:InCrOSDevice). The uninstaller only works on '
        'CrOS device.')
  if os.getuid() != 0:
    raise Exception('You must be root to uninstall the factory toolkit on a '
                    'CrOS device.')


def MakeWarningMessage():
  ret = file_utils.ReadFile(paths.FACTORY_TOOLKIT_VERSION_PATH)
  ret += (
      '\n'
      '\n'
      '*** You are about to uninstall the factory toolkit at:\n')

  for p in FACTORY_PATHS:
    ret += '***   %s\n' % p

  ret += '***'

  return ret


def Main():
  log_utils.InitLogging()

  parser = argparse.ArgumentParser(
      description=HELP_HEADER,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('--yes', '-y', action='store_true',
                      help="Don't ask for confirmation")

  args = parser.parse_args()

  AssertEnvironment()

  print(MakeWarningMessage())
  if not args.yes:
    answer = input('*** Continue? [y/N] ')
    if not answer or answer[0] not in 'yY':
      sys.exit('Aborting.')

  # To recover the symlinks under /usr/local/bin. We need to re-create the links
  # to factory-mini.par.
  install_symlinks.UninstallSymlinks('/usr/local/bin',
                                     install_symlinks.MODE_FULL)
  install_symlinks.InstallSymlinks('../factory-mini/factory-mini.par',
                                   '/usr/local/bin', install_symlinks.MODE_MINI)

  # Delete all factory related files.
  for p in FACTORY_PATHS:
    process_utils.Spawn(['rm', '-rf', p], check_call=True, log=True)


if __name__ == '__main__':
  Main()
