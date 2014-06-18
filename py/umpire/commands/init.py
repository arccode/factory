# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of umpire init."""

import logging
import os

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.common import BUNDLE_FACTORY_TOOLKIT_PATH
from cros.factory.umpire.utils import UnpackFactoryToolkit
from cros.factory.utils import file_utils
from cros.factory.utils import sys_utils


_SUB_DIRS = ['bin', 'dashboard', 'log', 'resources', 'run', 'toolkits',
             'updates', 'conf']

# Relative path of Umpire CLI in toolkit directory.
_UMPIRE_CLI_IN_TOOLKIT_PATH = os.path.join('usr', 'local', 'factory', 'bin',
                                           'umpire')


def Init(env, bundle_dir, board, make_default, local, user, group,
         root_dir='/'):
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
  """
  def SetUpDir(base_dir, uid, gid):
    """Sets up Umpire directory structure.

    It figures out Umpire base dir, creates it and its sub directories,
    and chown to user.group assigned in args.
    """
    def TryMkdir(path):
      if not os.path.isdir(path):
        os.makedirs(path)

    TryMkdir(base_dir)
    os.chown(base_dir, uid, gid)

    for sub_dir in _SUB_DIRS:
      TryMkdir(os.path.join(base_dir, sub_dir))

  def InstallUmpireExecutable():
    """Extracts factory toolkit to toolkit directory.

    Returns:
      path to server toolkit directory (for bin symlink).
    """
    toolkit_path = os.path.join(bundle_dir, BUNDLE_FACTORY_TOOLKIT_PATH)
    file_utils.CheckPath(toolkit_path, description='factory toolkit')

    # If it fails to add resource, it raises an exception and not
    # going forward.
    toolkit_resource = env.AddResource(toolkit_path)
    unpack_dir = UnpackFactoryToolkit(env, toolkit_resource,
                                      device_toolkit=False)
    logging.info('Factory toolkit extracted to %s', unpack_dir)
    return unpack_dir

  def SymlinkBinary(toolkit_base):
    """Creates /usr/local/bin/umpire-board symlink.

    For the first time, also creates /usr/local/bin/umpire symlink.
    If --default is set, replaces /usr/local/bin/umpire.

    Note that root '/'  can be overridden by arg 'root_dir' for testing.
    """
    umpire_binary = os.path.join(toolkit_base, _UMPIRE_CLI_IN_TOOLKIT_PATH)
    board_symlink = os.path.join(root_dir, 'usr', 'local', 'bin',
                                 'umpire-%s' % board)
    file_utils.CheckPath(umpire_binary, description='Umpire CLI')
    file_utils.ForceSymlink(umpire_binary, board_symlink)
    logging.info('Symlink %r -> %r', board_symlink, umpire_binary)

    default_symlink = os.path.join(root_dir, 'usr', 'local', 'bin', 'umpire')
    if not os.path.exists(default_symlink) or make_default:
      file_utils.ForceSymlink(umpire_binary, default_symlink)
      logging.info('Symlink %r -> %r', default_symlink, umpire_binary)

  (uid, gid) = sys_utils.GetUidGid(user, group)
  logging.info('Init umpire to %r for board %r with user.group: %s.%s',
               env.base_dir, board, user, group)

  SetUpDir(env.base_dir, uid, gid)
  toolkit_base = InstallUmpireExecutable()
  if not local:
    SymlinkBinary(toolkit_base)
  # TODO(deanliao): set up daemon running environment.
