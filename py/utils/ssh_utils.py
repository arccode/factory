# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for ssh and rsync.

This module is intended to work with Chrome OS DUTs only as it uses Chrome OS
testing_rsa identity.
"""

import logging
import os

try:
  from chromite.lib import remote_access
  _HAS_REMOTE_ACCESS = True
except ImportError:
  _HAS_REMOTE_ACCESS = False

from . import file_utils
from . import net_utils
from . import process_utils


# The path to the testing_rsa identity file.
testing_rsa = None


def _Init():
  """Initializes ssh identity.

  The identity file is created per user in /tmp as testing_rsa.${USER}.  We
  first create a temp identity file from the reference testing_rsa identity and
  change file mode to 0400 so it is only readable by the user.  We then move the
  temp file to our target /tmp/testing_rsa.${USER}.  We do not have race
  condition here since the move operation is atomic.

  We do not use generated temp files because we do not want to leave dangling
  temp files around.
  """
  # TODO(hungte) Use testing keys from factory repo.
  global testing_rsa    # pylint: disable=global-statement
  if not _HAS_REMOTE_ACCESS:
    raise RuntimeError('chromite.lib.remote_access does not exist.')
  if not testing_rsa:
    target_name = '/tmp/testing_rsa.%s' % os.environ.get('USER', 'default')
    if not os.path.exists(target_name):
      file_utils.AtomicCopy(remote_access.TEST_PRIVATE_KEY, target_name, 0o400)
    testing_rsa = target_name


def BuildSSHCommand(identity_file=None):
  """Builds SSH command that can be used to connect to a DUT.

  Args:
    identity_file: if specified, use it as identity file. Otherwise, use
        private_key provided by chromite.lib.remote_access (only avaliable
        in chroot).
  """
  if not identity_file:
    _Init()
    identity_file = testing_rsa
  return ['ssh',
          '-o', 'IdentityFile=%s' % identity_file,
          '-o', 'UserKnownHostsFile=/dev/null',
          '-o', 'LogLevel=ERROR',
          '-o', 'User=root',
          '-o', 'StrictHostKeyChecking=no',
          '-o', 'Protocol=2',
          '-o', 'BatchMode=yes',
          '-o', 'ConnectTimeout=30',
          '-o', 'ServerAliveInterval=180',
          '-o', 'ServerAliveCountMax=3',
          '-o', 'ConnectionAttempts=4']


def BuildRsyncCommand(identity_file=None):
  """Build rsync command that can be used to rsync to a DUT.

  Args:
    identity_file: if specified, use it as identity file. Otherwise, use
        private_key provided by chromite.lib.remote_access (only avaliable
        in chroot).
  """
  return ['rsync', '-e', ' '.join(BuildSSHCommand(identity_file=identity_file))]


def SpawnSSHToDUT(args, **kwargs):
  """Spawns a process to issue ssh command to a DUT.

  Args:
    args: Args appended to the ssh command.
    kwargs: See docstring of Spawn.
  """
  return process_utils.Spawn(BuildSSHCommand() + args, **kwargs)


def SpawnRsyncToDUT(args, **kwargs):
  """Spawns a process to issue rsync command to a DUT.

  Args:
    args: Arguments appended to the rsync command.
    kwargs: See docstring of Spawn.
  """
  return process_utils.Spawn(BuildRsyncCommand() + args, **kwargs)


class SSHTunnelToDUT:
  """A class to establish and close SSH tunnel to a DUT.

  Usage:
    >> # Create a SSH tunnel from localhost:8888 on 10.3.0.23 to localhost:9999
    >> # on current machine.
    >> with SSHTunnel('10.3.0.23', 9999, 8888):
    >>   [do something while the tunnel is established]

    or

    >> tunnel = SSHTunnel('10.3.0.23', 9999, 8888)
    >> tunnel.Establish()
    >> [do something while the tunnel is established]
    >> tunnel.Close()

  Args:
    remote: The hostname or IP address of the remote host.
    bind_port: The local port to bind to.
    host_port: The remote port to bind to.
    bind_address: The local address to bind to; default to '127.0.0.1'.
    host: The remote address to bind to; default to '127.0.0.1'.
  """

  def __init__(self, remote, bind_port, host_port,
               bind_address=net_utils.LOCALHOST, host=net_utils.LOCALHOST):
    self._remote = remote
    self._bind_address = bind_address
    self._bind_port = bind_port
    self._host = host
    self._host_port = host_port
    self._ssh_process = None

  def Establish(self):
    logging.debug('Establishing SSH tunnel to %s with spec %s:%s:%s:%s',
                  self._remote, self._bind_address, self._bind_port, self._host,
                  self._host_port)
    if self._ssh_process:
      self.Close()
    self._ssh_process = SpawnSSHToDUT([
        self._remote, '-N', '-f', '-L',
        '%s:%s:%s:%s' %
        (self._bind_address, self._bind_port, self._host, self._host_port)
    ], stderr=process_utils.DEVNULL, check_call=True)

  def Close(self):
    logging.debug('Closing SSH tunnel to %s', self._remote)
    if self._ssh_process:
      try:
        self._ssh_process.terminate()
      except OSError as e:
        if e.errno == 3:
          # The process has already been terminated.
          pass
      self._ssh_process = None

  def __enter__(self):
    self.Establish()

  def __exit__(self, *args, **kwargs):
    self.Close()
