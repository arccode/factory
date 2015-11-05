#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of cros.factory.test.dut.SshTarget using ssh."""

import logging
import subprocess

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import base
from cros.factory.utils import file_utils


class SshTarget(base.BaseTarget):
  """A DUT target that is connected via SSH interface.

  Properties:
    host: A string for SSH host.
    user: A string for the user accont to login. Defaults to 'root'.
    port: An integer for the SSH port on remote host.
    identify: An identity file to specify credential.
  """

  def __init__(self, host, user='root', port=22, identity=None):
    self.host = host
    self.user = user
    self.port = port
    self.identity = identity

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
    """See BaseTarget.Push"""
    remote_sig, options = self._signature(True)
    return subprocess.check_call(['scp'] + options +
                                 [local, '%s:%s' % (remote_sig, remote)])

  def Pull(self, remote, local=None):
    """See BaseTarget.Pull"""
    if local is None:
      with file_utils.UnopenedTemporaryFile() as path:
        self.Pull(remote, path)
        with open(path) as f:
          return f.read()

    remote_sig, options = self._signature(True)
    subprocess.check_call(['scp'] + options +
                          ['%s:%s' % (remote_sig, remote), local])

  def Shell(self, command, stdin=None, stdout=None, stderr=None):
    """See BaseTarget.Shell"""
    remote_sig, options = self._signature(False)

    if isinstance(command, basestring):
      command = 'ssh %s %s %s' % (' '.join(options), remote_sig, command)
      shell = True
    else:
      command = ['ssh'] + options + [remote_sig] + list(command)
      shell = False

    logging.debug('SshTarget: Run [%r]', command)
    return subprocess.call(command, stdin=stdin, stdout=stdout, stderr=stderr,
                           shell=shell)

  def IsReady(self):
    """See BaseTarget.IsReady"""
    return subprocess.call(['ping', '-c', '1', self.host]) == 0
