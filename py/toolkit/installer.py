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
import factory_common  # pylint: disable=W0611
import os
import subprocess
import sys

from cros.factory.test import factory


class FactoryToolkitInstaller():
  """Factory toolkit installer.

  Args:
    src: Source path containing usr/ and var/.
    args: Arguments including
      dest: Installation destination path. Set this to the mount point of the
            stateful partition if patching a test image.
      patch_test_image: True if patching a test image.
  """
  def __init__(self, src, args):
    if args.patch_test_image:
      self._usr_local_dest = os.path.join(args.dest, 'dev_image', 'local')
      self._var_dest = os.path.join(args.dest, 'var_overlay')
      if (not os.path.exists(self._usr_local_dest) or
          not os.path.exists(self._var_dest)):
        raise Exception(
            'The destination path %s is not a stateful partition!' % args.dest)
    else:
      self._usr_local_dest = os.path.join(args.dest, 'usr', 'local')
      self._var_dest = os.path.join(args.dest, 'var')
      if os.getuid() != 0:
        raise Exception('Must be root to install on live machine!')
      if not os.path.exists('/etc/lsb-release'):
        raise Exception('/etc/lsb-release is missing. '
                        'Are you running this in chroot?')

    self._patch_test_image = args.patch_test_image
    self._dest = args.dest
    self._usr_local_src = os.path.join(src, 'usr', 'local')
    self._var_src = os.path.join(src, 'var')
    self._no_enable = args.no_enable
    self._tag_file = os.path.join(self._usr_local_dest, 'factory', 'enabled')

    if (not os.path.exists(self._usr_local_src) or
        not os.path.exists(self._var_src)):
      raise Exception(
          'This installer must be run from within the factory toolkit!')

  def WarningMessage(self):
    ret = (
        '\n'
        '\n'
        '*** You are about to install factory toolkit to:\n'
        '***   %s\n'
        '***' % self._dest)
    if self._dest == '/':
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
    subprocess.check_call(['rsync', '-a', src + '/', dest])

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


def main():
  parser = argparse.ArgumentParser(
      description='Factory toolkit installer.')
  parser.add_argument('--dest', '-d', default='/',
      help='Destination path. Mount point of stateful partition if patching '
           'a test image.')
  parser.add_argument('--patch-test-image', '-p', action='store_true',
      help='Patching a test image instead of installing to live system.')
  parser.add_argument('--no-enable', '-n', action='store_true',
      help="Don't enable factory tests after installing")
  parser.add_argument('--yes', '-y', action='store_true',
      help="Don't ask for confirmation")
  args = parser.parse_args()

  try:
    src_root = factory.FACTORY_PATH
    for _ in xrange(3):
      src_root = os.path.dirname(src_root)
    installer = FactoryToolkitInstaller(src_root, args)
  except Exception as e:
    parser.error(e.message)

  print installer.WarningMessage()

  if not args.yes:
    answer = raw_input('*** Continue? [y/N] ')
    if not answer or answer[0] not in 'yY':
      sys.exit('Aborting.')

  installer.Install()

if __name__ == '__main__':
  main()
