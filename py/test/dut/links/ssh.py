#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of cros.factory.test.dut.DUTLink using SSH."""

import logging
import pipes
import subprocess
import threading

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test.args import Arg
from cros.factory.test.dut import link
from cros.factory.utils import file_utils
from cros.factory.utils.dhcp_utils import DHCPManager


_DEVICE_DATA_KEY = 'DYNAMIC_SSH_TARGET_IP'


class ClientNotExistError(Exception):
  def __str__(self):
    return 'There is no DHCP client registered.'


class SSHLink(link.DUTLink):
  """A DUT target that is connected via SSH interface."""

  LINK_ARGS = [
      Arg('host', str, 'A string for SSH host', optional=False),
      Arg('user', str, 'A string for the usr account to login', default='root'),
      Arg('port', int, 'An integer for SSH port on remote host', default=22),
      Arg('identity', str, 'An identity file to specify credential')]

  DYNAMIC_HOST = 'dynamic'

  def __init__(self, args):
    self._host = args.host
    self.user = args.user
    self.port = args.port
    self.identity = args.identity

  @property
  def host(self):
    if self._host == SSHLink.DYNAMIC_HOST:
      if not factory.has_shared_data(_DEVICE_DATA_KEY):
        raise ClientNotExistError()
      return factory.get_shared_data(_DEVICE_DATA_KEY)
    else:
      return self._host

  @host.setter
  def host(self, value):
    self._host = value

  def _signature(self, is_scp=False):
    """Generates the ssh command signature.

    Args:
      is_scp: A boolean flag indicating if the signature is made for scp.

    Returns:
      A pair of signature in (sig, options). The 'sig' is a string representing
      remote ssh user and host. 'options' is a list of required command line
      parameters.
    """
    if self.user:
      sig = '%s@%s' % (self.user, self.host)
    else:
      sig = self.host

    options = ['-o', 'UserKnownHostsFile=/dev/null',
               '-o', 'StrictHostKeyChecking=no']
    if self.port:
      options += ['-P' if is_scp else '-p', str(self.port)]
    if self.identity:
      options += ['-i', self.identity]
    return sig, options

  def Push(self, local, remote):
    """See DUTLink.Push"""
    remote_sig, options = self._signature(True)
    return subprocess.check_call(['scp'] + options +
                                 [local, '%s:%s' % (remote_sig, remote)])

  def Pull(self, remote, local=None):
    """See DUTLink.Pull"""
    if local is None:
      with file_utils.UnopenedTemporaryFile() as path:
        self.Pull(remote, path)
        with open(path) as f:
          return f.read()

    remote_sig, options = self._signature(True)
    subprocess.check_call(['scp'] + options +
                          ['%s:%s' % (remote_sig, remote), local])

  def Shell(self, command, stdin=None, stdout=None, stderr=None):
    """See DUTLink.Shell"""
    remote_sig, options = self._signature(False)

    if isinstance(command, basestring):
      command = 'ssh %s %s %s' % (' '.join(options), remote_sig,
                                  pipes.quote(command))
      shell = True
    else:
      command = ['ssh'] + options + [remote_sig] + map(pipes.quote, command)
      shell = False

    logging.debug('SSHLink: Run [%r]', command)
    return subprocess.call(command, stdin=stdin, stdout=stdout, stderr=stderr,
                           shell=shell)

  def IsReady(self):
    """See DUTLink.IsReady"""
    try:
      return subprocess.call(['ping', '-w', '1', '-c', '1', self.host]) == 0
    except ClientNotExistError:
      return False

  _dhcp_manager = None
  _dhcp_manager_lock = threading.Lock()

  @classmethod
  def DHCPConnected(cls, dut_ip, unused_mac):
    """Event handler for adding new client or lease renewal

    Save the IP address in device data.
    """
    factory.set_shared_data(_DEVICE_DATA_KEY, dut_ip)

  @classmethod
  def DHCPDisconnected(cls, unused_ip, unused_mac):
    """Event handler for lease expired

    Remove the IP address from device data.
    """
    if factory.has_shared_data(_DEVICE_DATA_KEY):
      factory.del_shared_data(_DEVICE_DATA_KEY)

  PREPARE_LINK_ARGS = LINK_ARGS

  @classmethod
  def PrepareLink(cls, args):
    if args.host == SSHLink.DYNAMIC_HOST:
      with cls._dhcp_manager_lock:
        if cls._dhcp_manager:
          return
        # TODO(stimim): automatically find out which network interface should be
        #               used.
        cls._dhcp_manager = DHCPManager(
            'eth1',
            lease_time=5,
            on_add=cls.DHCPConnected,
            on_old=cls.DHCPConnected,
            on_del=cls.DHCPDisconnected)
        cls._dhcp_manager.StartDHCP()
