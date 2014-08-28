# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of umpire init."""

import logging
import os
import shutil
import subprocess

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.commands import system
from cros.factory.umpire import common
from cros.factory.umpire.utils import UnpackFactoryToolkit
from cros.factory.utils import file_utils


_SUB_DIRS = ['bin', 'dashboard', 'log', 'resources', 'run', 'toolkits',
             'updates', 'conf']

# Relative path of Umpire CLI / Umpired in toolkit directory.
_UMPIRE_CLI_IN_TOOLKIT_PATH = os.path.join('usr', 'local', 'factory', 'bin',
                                           'umpire')
_UMPIRED_IN_TOOLKIT_PATH = os.path.join('usr', 'local', 'factory', 'bin',
                                        'umpired')

# Relative path of UmpireConfig template in toolkit directory.
# Note that it shall be defined in board spedific overlay.
_UMPIRE_CONFIG_TEMPLATE_IN_TOOLKIT_PATH = os.path.join(
    'usr', 'local', 'factory', 'py', 'umpire', 'umpired_template.yaml')

_ACTIVE_SERVER_TOOLKIT = 'active'


def Init(env, bundle_dir, board, make_default, local, user, group,
         root_dir='/', config_template=None, restart=True):
  """Initializes/updates an Umpire working environment.

  It creates base directory (specified in env.base_dir, installs Umpire
  executables and sets up daemon running environment.

  If an Umpire environment is already set, running it again will only update
  Umpire executables.

  Args:
    env: UmpireEnv object.
    bundle_dir: factory bundle's base directory.
    board: board name the Umpire to serve.
    make_default: make umpire-<board> as default.
    local: do not set up /usr/local/bin and umpired.
    user: the user to run Umpire daemon.
    group: the group to run Umpire dameon.
    root_dir: Root directory. Used for testing purpose.
    config_template: If specified, use it as UmpireConfig's template.
    restart: When true, Init() restarts Umpire daemon.
  """
  def SetUpDir(uid, gid):
    """Sets up Umpire directory structure.

    It figures out Umpire base dir, creates it and its sub directories,
    and chown to user.group assigned in args.
    """
    def TryMkdirChown(path):
      if not os.path.isdir(path):
        os.makedirs(path)
      os.chown(path, uid, gid)
      os.chmod(path, env.UMPIRE_DIR_MODE)

    TryMkdirChown(env.base_dir)
    for sub_dir in _SUB_DIRS:
      TryMkdirChown(os.path.join(env.base_dir, sub_dir))
    # Create the dummy resource file (empty).
    open(os.path.join(env.resources_dir, common.DUMMY_RESOURCE), 'w')

  def InstallUmpireExecutable(uid, gid):
    """Extracts factory toolkit to toolkit directory.

    Returns:
      path to server toolkit directory (for bin symlink).
    """
    toolkit_path = os.path.join(bundle_dir, common.BUNDLE_FACTORY_TOOLKIT_PATH)
    file_utils.CheckPath(toolkit_path, description='factory toolkit')

    # If it fails to add resource, it raises an exception and not
    # going forward.
    toolkit_resource = env.AddResource(toolkit_path)
    # Note that "umpire init" runs as root, so we need to chown the newly added
    # resource.
    os.chown(toolkit_resource, uid, gid)
    unpack_dir = UnpackFactoryToolkit(
        env, toolkit_resource, device_toolkit=False, run_as=(uid, gid),
        mode=env.UMPIRE_DIR_MODE)
    symlink_source = os.path.basename(unpack_dir)
    symlink = os.path.join(os.path.dirname(unpack_dir), _ACTIVE_SERVER_TOOLKIT)
    file_utils.TryUnlink(symlink)
    os.symlink(symlink_source, symlink)
    os.lchown(symlink, uid, gid)
    logging.info('Factory toolkit extracted to %s', unpack_dir)
    return unpack_dir

  def SymlinkBinary(toolkit_base):
    """Creates symlink to umpire/umpired executable.

    It first creates a symlink $base_dir/bin/umpire to umpire executable in
    extracted toolkit '$toolkit_base/usr/local/factory/bin/umpire'.
    And if 'local' is True, symlinks /usr/local/bin/umpire-$board to
    $base_dir/bin/umpire.

    For umpired, it only creates a symlink $base_dir/bin/umpired to umpired
    executable in extracted toolkit. (No symlink in /usr/local/bin)

    For the first time, also creates /usr/local/bin/umpire symlink.
    If --default is set, replaces /usr/local/bin/umpire.

    Note that root '/'  can be overridden by arg 'root_dir' for testing.
    """
    umpire_binary = os.path.join(toolkit_base, _UMPIRE_CLI_IN_TOOLKIT_PATH)
    umpire_bin_symlink = os.path.join(env.bin_dir, 'umpire')
    file_utils.CheckPath(umpire_binary, description='Umpire CLI')
    file_utils.ForceSymlink(umpire_binary, umpire_bin_symlink)
    logging.info('Symlink %r -> %r', umpire_bin_symlink, umpire_binary)

    umpired_binary = os.path.join(toolkit_base, _UMPIRED_IN_TOOLKIT_PATH)
    umpired_bin_symlink = os.path.join(env.bin_dir, 'umpired')
    file_utils.CheckPath(umpire_binary, description='Umpire daemon')
    file_utils.ForceSymlink(umpired_binary, umpired_bin_symlink)
    logging.info('Symlink %r -> %r', umpired_bin_symlink, umpired_binary)

    if not local:
      global_board_symlink = os.path.join(root_dir, 'usr', 'local', 'bin',
                                          'umpire-%s' % board)
      file_utils.ForceSymlink(umpire_bin_symlink, global_board_symlink)
      logging.info('Symlink %r -> %r', global_board_symlink, umpire_bin_symlink)

      default_symlink = os.path.join(root_dir, 'usr', 'local', 'bin', 'umpire')
      if not os.path.exists(default_symlink) or make_default:
        file_utils.ForceSymlink(global_board_symlink, default_symlink)
        logging.info('Symlink %r -> %r', default_symlink, global_board_symlink)

  def InitUmpireConfig(toolkit_base):
    """Prepares the very first UmpireConfig and marks it as active.

    An active config is necessary for the second step, import-bundle.
    It must be run after InstallUmpireExecutable as the template is from
    the toolkit.
    """
    template_path = config_template if config_template else (
        os.path.join(toolkit_base, _UMPIRE_CONFIG_TEMPLATE_IN_TOOLKIT_PATH))
    with file_utils.TempDirectory() as temp_dir:
      config_path = os.path.join(temp_dir, 'umpire.yaml')
      shutil.copyfile(template_path, config_path)
      config_in_resource = env.AddResource(config_path)
      os.chown(config_in_resource, uid, gid)

      file_utils.ForceSymlink(config_in_resource, env.active_config_file)
      os.lchown(env.active_config_file, uid, gid)
      logging.info('Init UmpireConfig %r and set it as active.',
                   config_in_resource)

  (uid, gid) = system.SetupDaemon(user, group)
  logging.info('Init umpire to %r for board %r with user.group: %s.%s',
               env.base_dir, board, user, group)

  SetUpDir(uid, gid)
  toolkit_base = InstallUmpireExecutable(uid, gid)
  InitUmpireConfig(toolkit_base)
  SymlinkBinary(toolkit_base)
  if restart:
    try:
      system.StopUmpire(board)
    except subprocess.CalledProcessError:
      pass
    system.StartUmpire(board)
