#!/usr/bin/python -Bu
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory toolkit installer.

The factory toolkit is a self-extracting shellball containing factory test
related files and this installer. This installer is invoked when the toolkit
is deployed and is responsible for installing files.
"""


import argparse
from contextlib import contextmanager
import os
import sys

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.tools.mount_partition import MountPartition
from cros.factory.utils.process_utils import Spawn


class FactoryToolkitInstaller():
  """Factory toolkit installer.

  Args:
    src: Source path containing usr/ and var/.
    dest: Installation destination path. Set this to the mount point of the
          stateful partition if patching a test image.
    no_enable: True to not install the tag file.
    system_root: The path to the root of the file system. This must be left
                 as its default value except for unit testing.
  """

  def __init__(self, src, dest, no_enable, system_root='/'):
    self._system_root = system_root
    if dest == self._system_root:
      self._usr_local_dest = os.path.join(dest, 'usr', 'local')
      self._var_dest = os.path.join(dest, 'var')
      if os.getuid() != 0:
        raise Exception('Must be root to install on live machine!')
      if not os.path.exists('/etc/lsb-release'):
        raise Exception('/etc/lsb-release is missing. '
                        'Are you running this in chroot?')
    else:
      self._usr_local_dest = os.path.join(dest, 'dev_image')
      self._var_dest = os.path.join(dest, 'var_overlay')
      if (not os.path.exists(self._usr_local_dest) or
          not os.path.exists(self._var_dest)):
        raise Exception(
            'The destination path %s is not a stateful partition!' % dest)

    self._dest = dest
    self._usr_local_src = os.path.join(src, 'usr', 'local')
    self._var_src = os.path.join(src, 'var')
    self._no_enable = no_enable
    self._tag_file = os.path.join(self._usr_local_dest, 'factory', 'enabled')

    if (not os.path.exists(self._usr_local_src) or
        not os.path.exists(self._var_src)):
      raise Exception(
          'This installer must be run from within the factory toolkit!')

  def WarningMessage(self, target_test_image=None):
    if target_test_image:
      ret = (
          '\n'
          '\n'
          '*** You are about to patch factory toolkit into:\n'
          '***   %s\n'
          '***' % target_test_image)
    else:
      ret = (
          '\n'
          '\n'
          '*** You are about to install factory toolkit to:\n'
          '***   %s\n'
          '***' % self._dest)
    if self._dest == self._system_root:
      if self._no_enable:
        ret += ('\n'
          '*** Factory tests will be disabled after this process is done, but\n'
          '*** you can enable them by creating factory enabled tag:\n'
          '***   %s\n'
          '***' % self._tag_file)
      else:
        ret += ('\n'
          '*** After this process is done, your device will start factory\n'
          '*** tests on the next reboot.\n'
          '***\n'
          '*** Factory tests can be disabled by deleting factory enabled tag:\n'
          '***   %s\n'
          '***' % self._tag_file)
    return ret

  def _Rsync(self, src, dest):
    print '***   %s -> %s' % (src, dest)
    Spawn(['rsync', '-a', src + '/', dest],
          sudo=True, log=True, check_output=True)

  def Install(self):
    print '*** Installing factory toolkit...'
    self._Rsync(self._usr_local_src, self._usr_local_dest)
    self._Rsync(self._var_src, self._var_dest)

    if self._no_enable:
      print '*** Removing factory enabled tag...'
      try:
        os.unlink(self._tag_file)
      except OSError:
        pass
    else:
      print '*** Installing factory enabled tag...'
      open(self._tag_file, 'w').close()

    print '*** Installation completed.'


@contextmanager
def DummyContext(arg):
  """A context manager that simply yields its argument."""
  yield arg


def PrintBuildInfo(src_root):
  """Print build information."""
  info_file = os.path.join(src_root, 'REPO_STATUS')
  if not os.path.exists(info_file):
    raise OSError('Build info file not found!')
  with open(info_file, 'r') as f:
    print f.read()


def main():
  parser = argparse.ArgumentParser(
      description='Factory toolkit installer.')
  parser.add_argument('dest', nargs='?', default='/',
      help='A test image or the mount point of the stateful partition. '
           "If omitted, install to live system, i.e. '/'.")
  parser.add_argument('--no-enable', '-n', action='store_true',
      help="Don't enable factory tests after installing")
  parser.add_argument('--yes', '-y', action='store_true',
      help="Don't ask for confirmation")
  parser.add_argument('--build-info', action='store_true',
      help="Print build information and exit")
  args = parser.parse_args()

  src_root = factory.FACTORY_PATH
  for _ in xrange(3):
    src_root = os.path.dirname(src_root)

  if args.build_info:
    PrintBuildInfo(src_root)
    return

  # Change to original working directory in case the user specifies
  # a relative path.
  # TODO: Use USER_PWD instead when makeself is upgraded
  os.chdir(os.environ['OLDPWD'])

  if not os.path.exists(args.dest):
    parser.error('Destination %s does not exist!' % args.dest)

  patch_test_image = os.path.isfile(args.dest)

  with (MountPartition(args.dest, 1, rw=True) if patch_test_image
        else DummyContext(args.dest)) as dest:
    installer = FactoryToolkitInstaller(src_root, dest, args.no_enable)

    print installer.WarningMessage(args.dest if patch_test_image else None)

    if not args.yes:
      answer = raw_input('*** Continue? [y/N] ')
      if not answer or answer[0] not in 'yY':
        sys.exit('Aborting.')

    installer.Install()

if __name__ == '__main__':
  main()
