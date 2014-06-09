# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""System helper functions.

Umpire is designed to run on Linux with Upstart event-based init daemon. This
module provides helper functions to install Umpire conf file, register Umpire
user and group.
"""

import errno
import grp
import logging
import os
import pwd
import shutil
import subprocess

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common
from cros.factory.utils import file_utils, process_utils


# Umpire init creates a group with same name as user.
UMPIRE_USER_GROUP = 'umpire'
UMPIRE_UPSTART = 'umpire'
ALLUMPIRE_UPSTART = 'all-umpire'

# Umpire Upstart configuration
_UPSTART_CONF_DST = '/etc/init/'
_UPSTART_CONF_SRC_LIST = [ALLUMPIRE_UPSTART + '.conf',
                          UMPIRE_UPSTART + '.conf']


def NeedRootPermission(func):
  """Decorates the function to log error message on EPERM."""
  def Wrapped(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except IOError as e:
      if e[0] == errno.EPERM:
        logging.error('%s: you will need root permission to call',
                      func.__name__)
      raise
  return Wrapped


class Upstart(object):
  """Simple Upstart control.

  Properties:
    conf_name: Upstart configuration name.
  """
  INITCTL = '/sbin/initctl'

  def __init__(self, conf_name, env=None):
    """Constructs Upstart configuration controller.

    Args:
      conf_name: Upstart configuration name.
      env: list of Upstart job env parameters.

    Raises:
      common.UmpireError: when failed to create Upstart job proxy.
    """
    super(Upstart, self).__init__()
    if not conf_name:
      raise common.UmpireError('Invalid configuration name')

    self.env = env if env else []
    self.conf_name = conf_name

  def _GetCommand(self, initctl_command):
    return [self.INITCTL, initctl_command, self.conf_name] + self.env

  def _CallInitctl(self, command):
    output_string = process_utils.CheckOutput(self._GetCommand(command))
    if ('Unknown job' in output_string or
        'Unknown parameter' in output_string or
        'Rejected send message' in output_string):
      raise common.UmpireError(output_string)
    return output_string

  def GetStatus(self):
    """Gets Upstart job status.

    Return:
      initctl output string.

    Raises:
      common.UmpireError when Upstart job is invalid or parameter unknown.
    """
    return self._CallInitctl('status')

  def IsStartRunning(self):
    return 'start/running' in self.GetStatus()

  def IsStopWaiting(self):
    return 'stop/waiting' in self.GetStatus()

  def Start(self):
    return self._CallInitctl('start')

  def Stop(self):
    return self._CallInitctl('stop')

  def Restart(self):
    return self._CallInitctl('restart')


@NeedRootPermission
def CreateUmpireUser():
  """Creates Umpire user, group and home directory.

  If Umpire user and group already exist, return its (uid, gid) tuple.

  Returns:
    (uid, gid): A tuple contains user id and group id.

  Raises:
    subprocess.CalledProcessError: when called with wrong input args.
    IOError(EPERM): need permissions.
    KeyError: can not fetch Umpire user/group from system.
  """
  with file_utils.TempDirectory() as temp_dir:
    args = [
        'useradd',
        '--system',                     # Umpire is a system account.
        '--user-group',                 # Create a group with same name as user.
        '--shell', '/usr/sbin/nologin', # Umpire will not login.
        '--home', common.DEFAULT_BASE_DIR,
        '--create-home',
        '--skel', temp_dir,             # Create empty home.
        '--comment', 'Umpire',
        UMPIRE_USER_GROUP]
    try:
      os.makedirs(common.DEFAULT_BASE_DIR)
    except OSError as e:
      if e.errno != errno.EEXIST:
        raise
    process = process_utils.Spawn(args, read_stdout=True, read_stderr=True)
    unused_stdout, stderr = process.communicate()
    # Ignore useradd return codes:
    #   9 : username already in use
    if process.returncode not in [0, 9]:
      # Raise on permission errors:
      #   1: can not update passwd
      #   10: can not update group
      #   12: can not create home
      #   13: can not create spool
      if process.returncode in [1, 10, 12, 13]:
        raise IOError(errno.EPERM, stderr)
      raise subprocess.CalledProcessError(process.returncode, args)
  umpire_user = pwd.getpwnam(UMPIRE_USER_GROUP)
  umpire_group = grp.getgrnam(UMPIRE_USER_GROUP)
  os.chown(common.DEFAULT_BASE_DIR, umpire_user.pw_uid, umpire_group.gr_gid)
  return (umpire_user.pw_uid, umpire_group.gr_gid)


@NeedRootPermission
def CreateUmpireUpstart():
  """Creates Umpire Upstart script."""
  for src in _UPSTART_CONF_SRC_LIST:
    shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), src),
                _UPSTART_CONF_DST)


@NeedRootPermission
def StartUmpire(board):
  """Starts Umpire Upstart script.

  Args:
    board: DUT board name.
  """
  umpire_upstart = Upstart(UMPIRE_UPSTART, env=['BOARD=%s' % board])
  umpire_upstart.Start()
  logging.debug('Umpire Upstart configuration started: %r',
                umpire_upstart.GetStatus())


@NeedRootPermission
def StopUmpire(board):
  """Stops Umpire.

  Args:
    board: DUT board name.
  """
  umpire_upstart = Upstart(UMPIRE_UPSTART, env=['BOARD=%s' % board])
  umpire_upstart.Stop()
  logging.debug('Umpire Upstart configuration stopped: %r',
                umpire_upstart.GetStatus())


@NeedRootPermission
def RestartUmpire(board):
  """Restarts Umpire Upstart script.

  Args:
    board: DUT board name.
  """
  umpire_upstart = Upstart(UMPIRE_UPSTART, env=['BOARD=%s' % board])
  umpire_upstart.Restart()
  logging.debug('Umpire Upstart configuration restarted: %r',
                umpire_upstart.GetStatus())
