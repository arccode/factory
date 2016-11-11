# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of umpire init."""

import grp
import logging
import os
import pwd
import shutil

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common
from cros.factory.utils import file_utils


# Relative path of Umpire CLI / Umpired in toolkit directory.
_UMPIRE_CLI_IN_TOOLKIT_PATH = os.path.join('bin', 'umpire')
_UMPIRED_IN_TOOLKIT_PATH = os.path.join('bin', 'umpired')
_DEFAULT_CONFIG_NAME = 'default_umpire.yaml'


def Init(env, board, make_default, local, user, group,
         root_dir='/', config_template=None):
  """Initializes an Umpire working environment.

  It creates base directory (specified in env.base_dir) and sets up daemon
  running environment.

  Args:
    env: UmpireEnv object.
    board: board name the Umpire to serve.
    make_default: make umpire-<board> as default.
    local: do not set up /usr/local/bin and umpired.
    user: the user to run Umpire daemon.
    group: the group to run Umpire dameon.
    root_dir: Root directory. Used for testing purpose.
    config_template: If specified, use it as UmpireConfig's template.
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

    os.umask(022)
    TryMkdirChown(env.base_dir)
    for sub_dir in env.SUB_DIRS:
      TryMkdirChown(os.path.join(env.base_dir, sub_dir))
    # Create the dummy resource file (empty).
    dummy_resource = os.path.join(env.resources_dir, common.DUMMY_RESOURCE)
    if not os.path.isfile(dummy_resource):
      open(dummy_resource, 'w')

  def SymlinkBinary():
    """Creates symlink to umpire/umpired executable and resources.

    If 'local' is False, it symlinks /usr/local/bin/umpire-$board to
    $toolkit_base/bin/umpire.

    For tftpboot, it creates a symlink /tftpboot/vmlinux-<BOARD>.bin to
    /var/db/factory/umpire/<BOARD>/resources/vmlinux.bin.

    For the first time, also creates /usr/local/bin/umpire symlink.
    If --default is set, replaces /usr/local/bin/umpire.

    Note that root '/'  can be overridden by arg 'root_dir' for testing.
    """
    def _TrySymlink(target, link_name):
      file_utils.TryUnlink(link_name)
      os.symlink(target, link_name)
      logging.info('Symlink %r -> %r', link_name, target)

    umpire_binary = os.path.join(
        env.server_toolkit_dir, _UMPIRE_CLI_IN_TOOLKIT_PATH)

    if not local:
      global_board_symlink = os.path.join(root_dir, 'usr', 'local', 'bin',
                                          'umpire-%s' % board)
      _TrySymlink(umpire_binary, global_board_symlink)

      default_symlink = os.path.join(root_dir, 'usr', 'local', 'bin', 'umpire')
      if not os.path.exists(default_symlink) or make_default:
        _TrySymlink(global_board_symlink, default_symlink)

      tftpboot_path = os.path.join(root_dir, 'tftpboot')
      vmlinux_symlink = os.path.join(tftpboot_path, 'vmlinux-%s.bin' % board)
      resources_vmlinux_bin = os.path.join(env.resources_dir, 'vmlinux.bin')

      # Installation shouldn't fail even if /tftpboot doesn't exist
      file_utils.TryMakeDirs(tftpboot_path)
      _TrySymlink(resources_vmlinux_bin, vmlinux_symlink)

  def InitUmpireConfig():
    """Prepares the very first UmpireConfig and marks it as active.

    An active config is necessary for the second step, import-bundle.
    """
    # Do not override existing active config.
    if os.path.exists(env.active_config_file):
      return

    template_path = config_template or (
        os.path.join(env.server_toolkit_dir, _DEFAULT_CONFIG_NAME))
    with file_utils.TempDirectory() as temp_dir:
      config_path = os.path.join(temp_dir, 'umpire.yaml')
      shutil.copyfile(template_path, config_path)
      config_in_resource = env.AddResource(config_path)
      os.chown(config_in_resource, uid, gid)

      file_utils.ForceSymlink(config_in_resource, env.active_config_file)
      os.lchown(env.active_config_file, uid, gid)
      logging.info('Init UmpireConfig %r and set it as active.',
                   config_in_resource)

  (uid, gid) = GetUidGid(user, group)
  logging.info('Init umpire to %r for board %r with user.group: %s.%s',
               env.base_dir, board, user, group)

  SetUpDir(uid, gid)
  InitUmpireConfig()
  SymlinkBinary()

def GetUidGid(user, group):
  """Gets user ID and group ID.

  Args:
    user: user name.
    group: group name.

  Returns:
    (uid, gid)

  Raises:
    KeyError if user or group is not found.
  """
  try:
    uid = pwd.getpwnam(user).pw_uid
  except KeyError:
    raise KeyError('User %r not found. Please create it.' % user)
  try:
    gid = grp.getgrnam(group).gr_gid
  except KeyError:
    raise KeyError('Group %r not found. Please create it.' % group)
  return (uid, gid)
