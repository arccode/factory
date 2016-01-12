#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of cros.factory.test.dut.DUTLink using SSH."""

import logging
import pipes
import subprocess
import threading
import types

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test.dut import link
from cros.factory.test.utils import dhcp_utils
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


_DEVICE_DATA_KEY = 'DYNAMIC_SSH_TARGET_IP'


class ClientNotExistError(Exception):
  def __str__(self):
    return 'There is no DHCP client registered.'


class SSHLink(link.DUTLink):
  """A DUT target that is connected via SSH interface.

  Properties:
    host: A string for SSH host, if it's None, will get from shared data.
    user: A string for the user accont to login. Defaults to 'root'.
    port: An integer for the SSH port on remote host.
    identify: An identity file to specify credential.

  dut_options example:
    dut_options for fixed-IP:
      {
        'board_class': 'CoolBoard',
        'link_class': 'SSHLink',
        'host': '1.2.3.4',
        'identity': '/path/to/identity/file'
        'start_dhcp_server': False
      }
    dut_options for DHCP:
      {
        'board_class': 'CoolBoard',
        'link_class': 'SSHLink',
        'host': None,
        'identity': '/path/to/identity/file',
        'start_dhcp_server': True,
        'dhcp_server_args': {
          'lease_time': 3600,
          'interface_blacklist_file': '/path/to/blacklist/file',
          'exclude_ip_prefix': [('10.0.0.0', 24), ...],
          # the following three properties can oly be set in python script,
          # not in environment variable (CROS_FACTORY_DUT_OPTIONS)
          'on_add': None,
          'on_old': None,
          'on_del': None,
        }
      }
  """

  def __init__(self, host=None, user='root', port=22, identity=None):
    self._host = host
    self.user = user
    self.port = port
    self.identity = identity

  @property
  def host(self):
    if self._host == None:
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
  def SetLinkIP(cls, ip):
    factory.set_shared_data(_DEVICE_DATA_KEY, ip)

  @classmethod
  def ResetLinkIP(cls):
    if factory.has_shared_data(_DEVICE_DATA_KEY):
      factory.del_shared_data(_DEVICE_DATA_KEY)

  @classmethod
  def PrepareLink(cls, start_dhcp_server=True, dhcp_server_args=None):
    """Prepare for SSHLink connection

    Arguments:
      start_dhcp_server (default: False):
        Start the default DHCP server or not
      dhcp_server_args (default: None):
        If ``start_dhcp_server`` is True, this will be passed to the default
        DHCP server (ssh.LinkManager)
    """
    if not start_dhcp_server:
      return
    with cls._dhcp_manager_lock:
      if cls._dhcp_manager:
        return
      options = dict(lease_time=5)
      options.update(dhcp_server_args or {})

      cls._dhcp_manager = cls.LinkManager(**options)
      cls._dhcp_manager.Start()

  class LinkManager(object):
    def __init__(self,
                 lease_time=3600,
                 interface_blacklist_file=None,
                 exclude_ip_prefix=None,
                 on_add=None,
                 on_old=None,
                 on_del=None):
      """
        A LinkManager will automatically start a DHCP server for each availiable
        network interfaces, if the interface is not default gateway or in the
        blacklist.

        This LinkManager will automatically save IP of the latest client in
        system-wise shared data, make it availible to SSHLinks whose host is set
        to None.

        Options:
          lease_time:
            lease time of DHCP servers
          interface_blacklist_file:
            a path to the file of blacklist, each line represents an interface
            (e.g. eth0, wlan1, ...)
          exclude_ip_prefix:
            some IP range cannot be used becase of system settings, this argument
            should be a list of tuple of (ip, prefix_bits).
          on_add, on_old, on_del:
            callback functions for DHCP servers.
      """
      self._lease_time = lease_time
      self._blacklist_file = interface_blacklist_file
      self._on_add = on_add
      self._on_old = on_old
      self._on_del = on_del
      self._dhcp_server = None
      self._exclude_ip_prefix = exclude_ip_prefix

      self._duts = type_utils.UniqueStack()

    def _SetLastDUT(self):
      last_dut = self._duts.Get()
      if last_dut:
        SSHLink.SetLinkIP(last_dut[0])
      else:
        SSHLink.ResetLinkIP()

    def _OnDHCPAdd(self, ip, mac_address):
      # update last device
      self._duts.Add((ip, mac_address))
      self._SetLastDUT()

      # invoke callback function
      if isinstance(self._on_add, types.FunctionType):
        self._on_add(ip, mac_address)

    def _OnDHCPOld(self, ip, mac_address):
      # update last device
      self._duts.Add((ip, mac_address))
      self._SetLastDUT()

      # invoke callback function
      if isinstance(self._on_old, types.FunctionType):
        self._on_old(ip, mac_address)

    def _OnDHCPDel(self, ip, mac_address):
      # remove the device
      self._duts.Del((ip, mac_address))
      self._SetLastDUT()

      # invoke callback function
      if isinstance(self._on_del, types.FunctionType):
        self._on_del(ip, mac_address)

    def _StartHDCPServer(self):
      self._dhcp_server = dhcp_utils.StartDHCPManager(
          blacklist_file=self._blacklist_file,
          exclude_ip_prefix=self._exclude_ip_prefix,
          lease_time=self._lease_time,
          on_add=self._OnDHCPAdd,
          on_old=self._OnDHCPOld,
          on_del=self._OnDHCPDel)

    def Start(self):
      self._SetLastDUT()
      self._StartHDCPServer()

    def Stop(self):
      if self._dhcp_server:
        self._dhcp_server.StopDHCP()
