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
import shutil
import sys
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.test import event_log
from cros.factory.test import factory
from cros.factory.test import utils
from cros.factory.tools import install_symlinks
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.sys_utils import MountPartition


INSTALLER_PATH = 'usr/local/factory/py/toolkit/installer.py'
MAKESELF_SHELL = '/bin/sh'
TOOLKIT_NAME = 'install_factory_toolkit.run'

# Short and sweet help header for the executable generated by makeself.
HELP_HEADER = """
Installs the factory toolkit, transforming a test image into a factory test
image. You can:

- Install the factory toolkit on a CrOS device that is running a test
  image.  To do this, copy install_factory_toolkit.run to the device and
  run it.  The factory tests will then come up on the next boot.

    rsync -a install_factory_toolkit.run crosdevice:/tmp
    ssh crosdevice '/tmp/install_factory_toolkit.run && sync && reboot'

- Modify a test image, turning it into a factory test image.  When you
  use the image on a device, the factory tests will come up.

    install_factory_toolkit.run chromiumos_test_image.bin
"""

HELP_HEADER_ADVANCED = """
- (advanced) Modify a mounted stateful partition, turning it into a factory
  test image.  This is equivalent to the previous command:

    mount_partition -rw chromiumos_test_image.bin 1 /mnt/stateful
    install_factory_toolkit.run /mnt/stateful
    umount /mnt/stateful

- (advanced) Unpack the factory toolkit, modify a file, and then repack it.

    # Unpack but don't actually install
    install_factory_toolkit.run --target /tmp/toolkit --noexec
    # Edit some files in /tmp/toolkit
    emacs /tmp/toolkit/whatever
    # Repack
    install_factory_toolkit.run -- --repack /tmp/toolkit \\
        --pack-into /path/to/new/install_factory_toolkit.run
"""

# The makeself-generated header comes next.  This is a little confusing,
# so explain.
HELP_HEADER_MAKESELF = """
For complete usage information and advanced operations, run
"install_factory_toolkit.run -- --help" (note the extra "--").

Following is the help message from makeself, which was used to create
this self-extracting archive.

-----
"""

# The method to determine whether running on Chrome OS device or not.
# Override this for unit testing.
_in_cros_device = utils.in_cros_device

SERVER_FILE_MASK = [
    # Exclude Umpire server but keep Umpire client
    '--include', 'py/umpire/__init__.*',
    '--include', 'py/umpire/common.*',
    '--include', 'py/umpire/client',
    '--include', 'py/umpire/client/**',
    '--exclude', 'py/umpire/**',

    # Lumberjack is only used on Umpire server
    '--exclude', 'py/lumberjack'
]


class FactoryToolkitInstaller(object):
  """Factory toolkit installer.

  Args:
    src: Source path containing usr/ and var/.
    dest: Installation destination path. Set this to the mount point of the
          stateful partition if patching a test image.
    no_enable: True to not install the tag file.
    system_root: The path to the root of the file system. This must be left
                 as its default value except for unit testing.
  """

  # Whether to sudo when rsyncing; set to False for testing.
  _sudo = True

  def __init__(self, src, dest, no_enable, enable_presenter,
               enable_device, non_cros=False, device_id=None, system_root='/'):
    self._src = src
    self._system_root = system_root
    if dest == self._system_root:
      self._usr_local_dest = os.path.join(dest, 'usr', 'local')
      self._var_dest = os.path.join(dest, 'var')

      # Make sure we're on a CrOS device.
      if not non_cros and not _in_cros_device():
        sys.stderr.write(
            "ERROR: You're not on a CrOS device (for more details, please\n"
            'check utils.py:in_cros_device), so you must specify a test\n'
            'image or a mounted stateful partition on which to install the\n'
            'factory toolkit.  Please run\n'
            '\n'
            '  install_factory_toolkit.run -- --help\n'
            '\n'
            'for help.\n'
            '\n'
            'If you want to install the presenter on a non-CrOS host,\n'
            'please run\n'
            '\n'
            '  install_factory_toolkit.run -- \\\n'
            '      --non-cros --no-enable-device --enable-presenter\n'
            '\n')
        sys.exit(1)
      if os.getuid() != 0:
        raise Exception('You must be root to install the factory toolkit on a '
                        'CrOS device.')
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

    self._enable_presenter = enable_presenter
    self._presenter_tag_file = os.path.join(self._usr_local_dest, 'factory',
                                            'init', 'run_goofy_presenter')

    self._enable_device = enable_device
    self._device_tag_file = os.path.join(self._usr_local_dest, 'factory',
                                         'init', 'run_goofy_device')
    self._device_id = device_id

    if (not os.path.exists(self._usr_local_src) or
        not os.path.exists(self._var_src)):
      raise Exception(
          'This installer must be run from within the factory toolkit!')

  def WarningMessage(self, target_test_image=None):
    with open(os.path.join(self._src, 'VERSION')) as f:
      ret = f.read()
    if target_test_image:
      ret += (
          '\n'
          '\n'
          '*** You are about to patch the factory toolkit into:\n'
          '***   %s\n'
          '***' % target_test_image)
    else:
      ret += (
          '\n'
          '\n'
          '*** You are about to install the factory toolkit to:\n'
          '***   %s\n'
          '***' % self._dest)
    if self._dest == self._system_root:
      if self._no_enable:
        ret += ('\n*** Factory tests will be disabled after this process is '
                'done, but\n*** you can enable them by creating the factory '
                'enabled tag:\n***   %s\n***' % self._tag_file)
      else:
        ret += ('\n*** After this process is done, your device will start '
                'factory\n*** tests on the next reboot.\n***\n*** Factory '
                'tests can be disabled by deleting the factory enabled\n*** '
                'tag:\n***   %s\n***' % self._tag_file)
    return ret

  def _SetTagFile(self, name, path, enabled):
    """Install or remove a tag file."""
    if enabled:
      print '*** Installing %s enabled tag...' % name
      Spawn(['touch', path], sudo=True, log=True, check_call=True)
      Spawn(['chmod', 'go+r', path], sudo=True, log=True, check_call=True)
    else:
      print '*** Removing %s enabled tag...' % name
      Spawn(['rm', '-f', path], sudo=True, log=True, check_call=True)

  def _SetDeviceID(self):
    if self._device_id is not None:
      with open(os.path.join(event_log.DEVICE_ID_PATH), 'w') as f:
        f.write(self._device_id)

  def Install(self):
    print '*** Installing factory toolkit...'
    for src, dest in ((self._usr_local_src, self._usr_local_dest),
                      (self._var_src, self._var_dest)):
      # Change the source directory to root, and add group/world read
      # permissions.  This is necessary because when the toolkit was
      # unpacked, the user may not have been root so the permessions
      # may be hosed.  This is skipped for testing.
      # --force is necessary to allow goofy directory from prior
      # toolkit installations to be overwritten by the goofy symlink.
      try:
        if self._sudo:
          Spawn(['chown', '-R', 'root', src],
                sudo=True, log=True, check_call=True)
          Spawn(['chmod', '-R', 'go+rX', src],
                sudo=True, log=True, check_call=True)
        print '***   %s -> %s' % (src, dest)
        Spawn(['rsync', '-a', '--force'] + SERVER_FILE_MASK +
              [src + '/', dest], sudo=self._sudo, log=True,
              check_output=True, cwd=src)
      finally:
        # Need to change the source directory back to the original user, or the
        # script in makeself will fail to remove the temporary source directory.
        if self._sudo:
          myuser = os.environ.get('USER')
          Spawn(['chown', '-R', myuser, src],
                sudo=True, log=True, check_call=True)

    print '*** Installing symlinks...'
    install_symlinks.InstallSymlinks(
        '../factory/bin',
        os.path.join(self._usr_local_dest, 'bin'),
        install_symlinks.MODE_FULL,
        sudo=self._sudo)

    print '*** Removing factory-mini...'
    Spawn(['rm', '-rf', os.path.join(self._usr_local_dest, 'factory-mini')],
          sudo=self._sudo, log=True, check_call=True)

    self._SetTagFile('factory', self._tag_file, not self._no_enable)
    self._SetTagFile('presenter', self._presenter_tag_file,
                     self._enable_presenter)
    self._SetTagFile('device', self._device_tag_file, self._enable_device)

    self._SetDeviceID()

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


def PackFactoryToolkit(src_root, output_path, enable_device, enable_presenter):
  """Packs the files containing this script into a factory toolkit."""
  with open(os.path.join(src_root, 'VERSION'), 'r') as f:
    version = f.read().strip()
  with tempfile.NamedTemporaryFile() as help_header:
    help_header.write(version + '\n' + HELP_HEADER + HELP_HEADER_MAKESELF)
    help_header.flush()
    cmd = [os.path.join(src_root, 'makeself.sh'), '--bzip2', '--nox11',
           '--help-header', help_header.name,
           src_root, output_path, version, INSTALLER_PATH, '--in-exe']
    if not enable_device:
      cmd.append('--no-enable-device')
    if not enable_presenter:
      cmd.append('--no-enable-presenter')
    Spawn(cmd, check_call=True, log=True)
  print ('\n'
         '  Factory toolkit generated at %s.\n'
         '\n'
         '  To install factory toolkit on a live device running a test image,\n'
         '  copy this to the device and execute it as root.\n'
         '\n'
         '  Alternatively, the factory toolkit can be used to patch a test\n'
         '  image. For more information, run:\n'
         '    %s --help\n'
         '\n' % (output_path, output_path))


def InitUmpire(exe_path, src_root, target_board):
  """Inits Umpire server environment."""
  if exe_path is None:
    parent_cmdline = open('/proc/%s/cmdline' % os.getppid(),
                          'r').read().rstrip('\0').split('\0')

    if parent_cmdline > 1 and parent_cmdline[0] == MAKESELF_SHELL:
      # Get parent script name from parent process.
      exe_path = parent_cmdline[1]
    else:
      # Set to default.
      exe_path = TOOLKIT_NAME

  if not exe_path.startswith('/'):
    exe_path = os.path.join(os.environ.get('OLDPWD'), exe_path)

  with file_utils.TempDirectory() as nano_bundle:
    bundle_toolkit_dir = os.path.join(nano_bundle, 'factory_toolkit')
    os.mkdir(bundle_toolkit_dir)
    os.symlink(exe_path, os.path.join(bundle_toolkit_dir,
                                      os.path.basename(exe_path)))
    umpire_bin = os.path.join(src_root, 'usr', 'local', 'factory', 'bin',
                              'umpire')
    Spawn([umpire_bin, 'init', '--board', target_board, nano_bundle],
          check_call=True, log=True)
    print ('\n'
           '  Umpire initialized successfully. Upstart service is running:\n'
           '    umpire BOARD=%(board)s.\n'
           '  For more information, please check umpire command line:\n'
           '\n'
           '    umpire-%(board)s --help  (if your id is in umpire group)\n'
           '    or sudo umpire-%(board)s --help\n'
           '\n' % {'board': target_board})


def ExtractOverlord(src_root, output_dir):
  output_dir = os.path.join(output_dir, 'overlord')
  try:
    os.makedirs(output_dir)
  except OSError as e:
    print str(e)
    return

  # Copy overlord binary and resource files
  shutil.copyfile(os.path.join(src_root, 'usr/bin/overlordd'),
                  os.path.join(output_dir, 'overlordd'))
  shutil.copytree(os.path.join(src_root, 'usr/share/overlord/app'),
                  os.path.join(output_dir, 'app'))

  # Give overlordd execution permission
  os.chmod(os.path.join(output_dir, 'overlordd'), 0755)
  print "Extarcted overlord under '%s'" % output_dir


def main():
  import logging
  logging.basicConfig(level=logging.INFO)

  # In order to determine which usage message to show, first determine
  # whether we're in the self-extracting archive.  Do this first
  # because we need it to even parse the arguments.
  if '--in-exe' in sys.argv:
    sys.argv = [x for x in sys.argv if x != '--in-exe']
    in_archive = True
  else:
    in_archive = False

  parser = argparse.ArgumentParser(
      description=HELP_HEADER + HELP_HEADER_ADVANCED,
      usage=('install_factory_toolkit.run -- [options]' if in_archive
             else None),
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
      'dest', nargs='?', default='/',
      help='A test image or the mount point of the stateful partition. '
           "If omitted, install to live system, i.e. '/'.")
  parser.add_argument('--no-enable', '-n', action='store_true',
                      help="Don't enable factory tests after installing")
  parser.add_argument('--yes', '-y', action='store_true',
                      help="Don't ask for confirmation")
  parser.add_argument('--build-info', action='store_true',
                      help='Print build information and exit')
  parser.add_argument('--pack-into', metavar='NEW_TOOLKIT',
                      help='Pack the files into a new factory toolkit')
  parser.add_argument('--repack', metavar='UNPACKED_TOOLKIT',
                      help='Repack from previously unpacked toolkit')

  parser.add_argument('--enable-presenter', dest='enable_presenter',
                      action='store_true',
                      help='Run goofy in presenter mode on startup')
  parser.add_argument('--no-enable-presenter', dest='enable_presenter',
                      action='store_false', help=argparse.SUPPRESS)
  parser.set_defaults(enable_presenter=True)

  parser.add_argument('--non-cros', dest='non_cros',
                      action='store_true',
                      help='Install on non-ChromeOS host.')

  parser.add_argument('--enable-device', dest='enable_device',
                      action='store_true',
                      help='Run goofy in device mode on startup')
  parser.add_argument('--no-enable-device', dest='enable_device',
                      action='store_false', help=argparse.SUPPRESS)
  parser.set_defaults(enable_device=True)

  parser.add_argument('--device-id', dest='device_id', type=str, default=None,
                      help='Set device ID for this device')

  parser.add_argument('--init-umpire-board', dest='umpire_board',
                      nargs='?', default=None,
                      help='Locally install Umpire server for specific board')
  parser.add_argument('--exe-path', dest='exe_path',
                      nargs='?', default=None,
                      help='Current self-extracting archive pathname')
  parser.add_argument('--extract-overlord', dest='extract_overlord',
                      metavar='OUTPUT_DIR', type=str, default=None,
                      help='Extract overlord from the toolkit')

  args = parser.parse_args()

  src_root = factory.FACTORY_PATH
  for _ in xrange(3):
    src_root = os.path.dirname(src_root)

  # --init-umpire-board creates a nano bundle, then calls umpire command
  # line utility to install the server code and upstart configurations.
  if args.umpire_board:
    InitUmpire(args.exe_path, src_root, args.umpire_board)
    return

  if args.extract_overlord is not None:
    ExtractOverlord(src_root, args.extract_overlord)
    return

  # --pack-into may be called directly so this must be done before changing
  # working directory to OLDPWD.
  if args.pack_into and args.repack is None:
    PackFactoryToolkit(src_root, args.pack_into, args.enable_device,
                       args.enable_presenter)
    return

  if not in_archive:
    # If you're not in the self-extracting archive, you're not allowed to
    # do anything except the above --pack-into call.
    parser.error('Not running from install_factory_toolkit.run; '
                 'only --pack-into (without --repack) is allowed')

  # Change to original working directory in case the user specifies
  # a relative path.
  # TODO: Use USER_PWD instead when makeself is upgraded
  os.chdir(os.environ['OLDPWD'])

  if args.repack:
    if args.pack_into is None:
      parser.error('Must specify --pack-into when using --repack.')
    Spawn([os.path.join(args.repack, INSTALLER_PATH),
           '--pack-into', args.pack_into], check_call=True, log=True)
    return

  if args.build_info:
    PrintBuildInfo(src_root)
    return

  if not os.path.exists(args.dest):
    parser.error('Destination %s does not exist!' % args.dest)

  patch_test_image = os.path.isfile(args.dest)

  with (MountPartition(args.dest, 1, rw=True) if patch_test_image
        else DummyContext(args.dest)) as dest:
    installer = FactoryToolkitInstaller(
        src=src_root, dest=dest, no_enable=args.no_enable,
        enable_presenter=args.enable_presenter,
        enable_device=args.enable_device, non_cros=args.non_cros,
        device_id=args.device_id)

    print installer.WarningMessage(args.dest if patch_test_image else None)

    if not args.yes:
      answer = raw_input('*** Continue? [y/N] ')
      if not answer or answer[0] not in 'yY':
        sys.exit('Aborting.')

    installer.Install()

if __name__ == '__main__':
  main()
