#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""SSH port forward watchdog tool.

Can either be used as a library, or as a CLI.
"""

import argparse
import logging
import os
import subprocess
import sys
import threading
import time


_CTRL_C_EXIT_CODE = 130


class SSHPortForwarder(object):
  """Creates and maintains an SSH port forwarding connection.

  This is meant to be a standalone class to maintain an SSH port forwarding
  connection to a given server.  It provides a fail/retry mechanism, and also
  can report its current connection status.
  """
  _FAILED_STR = 'port forwarding failed'
  _DEFAULT_PORT = 22
  _DEFAULT_RETRIES = 0  # retry forever
  _DEFAULT_RETRY_ON_FORWARD_FAILURE = True
  _DEFAULT_CONNECT_TIMEOUT = 10
  _DEFAULT_ALIVE_INTERVAL = 10
  _DEFAULT_DISCONNECT_WAIT = 1
  _DEFAULT_EXP_FACTOR = 0
  _DEFAULT_BLOCKING = False
  _DEFAULT_FORWARD_HOST = '127.0.0.1'
  _DEBUG_INTERVAL = 2

  CONNECTING = 1
  INITIALIZED = 2
  FAILED = 4

  REMOTE = 1
  LOCAL = 2

  @classmethod
  def ToRemote(cls, *args, **kwargs):
    """Calls contructor with forward_to=REMOTE."""
    return cls(*args, forward_to=cls.REMOTE, **kwargs)

  @classmethod
  def ToLocal(cls, *args, **kwargs):
    """Calls contructor with forward_to=LOCAL."""
    return cls(*args, forward_to=cls.LOCAL, **kwargs)

  def __init__(self,
               forward_to,
               src_port,
               dst_port,
               user,
               identity_file,
               host,
               port=_DEFAULT_PORT,
               src_host=None,
               dst_host=None,
               extra_args=None,
               retries=None,
               retry_on_forward_failure=None,
               connect_timeout=None,
               alive_interval=None,
               disconnect_wait=None,
               exp_factor=None,
               blocking=None):
    """Constructor.

    Args:
      forward_to: Which direction to forward traffic: REMOTE or LOCAL.
      src_port: Bind to source port for traffic forwarding.
      dst_port: Send traffic to destination port for traffic forwarding.
      user: Username on remote server.
      identity_file: Identity file for passwordless authentication on remote
          server.
      host: Host of remote server.
      port: Port of remote server.
      src_host: Bind to source hostname for traffic forwarding.
      dst_host: Send traffic to destination hostname for traffic forwarding.
      extra_args: Extra arguments to pass to SSH.  Should be an array of
          strings.
      retries: The number of times to retry before reporting a failed
          connection.  If 0, retry forever.
      retry_on_forward_failure: Whether or not to retry after successfully
          connecting, but not successfully forwarding the port (it is probably
          in use).
      connect_timeout: The number of seconds to wait before assuming the SSH
          connection has succeeded.  SSH doesn't output any information while
          making the connection, so we can only "assume" it has successfully
          connected after a certain period of time.
      alive_interval: The number of seconds to wait before sending a null
          packet to the server (to keep the connection alive).
      disconnect_wait: The number of seconds to wait before reconnecting after
          the first disconnect.  This number is multiplied by 2^exp_factor
          on each connection attempt.
      exp_factor: After each reconnect, the disconnect wait time is multiplied
          by 2^exp_factor.
      blocking: Whether or not to block until all retries have been exhausted.
    """
    def ValidateArg(value, default):
      return default if value is None else value

    # Internal use.
    self._ssh_thread = None
    self._ssh_output = None
    self._exception = None
    self._state = self.CONNECTING
    self._poll = threading.Event()

    # Connection arguments.
    self._forward_to = forward_to
    self._src_port = src_port
    self._dst_port = dst_port
    self._user = user
    self._identity_file = identity_file
    self._host = host
    self._port = ValidateArg(port, self._DEFAULT_PORT)
    self._src_host = ValidateArg(src_host, self._DEFAULT_FORWARD_HOST)
    self._dst_host = ValidateArg(dst_host, self._DEFAULT_FORWARD_HOST)
    self._extra_args = extra_args or []

    # Configuration arguments.
    self._retries = ValidateArg(retries, self._DEFAULT_RETRIES)
    self._retry_on_forward_failure = ValidateArg(
        retry_on_forward_failure,
        self._DEFAULT_RETRY_ON_FORWARD_FAILURE)
    self._connect_timeout = ValidateArg(
        connect_timeout, self._DEFAULT_CONNECT_TIMEOUT)
    self._alive_interval = ValidateArg(
        alive_interval, self._DEFAULT_ALIVE_INTERVAL)
    self._disconnect_wait = ValidateArg(
        disconnect_wait, self._DEFAULT_DISCONNECT_WAIT)
    self._exp_factor = ValidateArg(exp_factor, self._DEFAULT_EXP_FACTOR)
    self._blocking = ValidateArg(blocking, self._DEFAULT_BLOCKING)

    if blocking:
      self._Run(self._disconnect_wait, self._retries)
    else:
      t = threading.Thread(
          target=self._Run,
          args=(self._disconnect_wait, self._retries))
      t.daemon = True
      t.start()

  def __str__(self):
    # State representation.
    if self._state == self.CONNECTING:
      state_str = 'connecting'
    elif self._state == self.INITIALIZED:
      state_str = 'initialized'
    else:
      state_str = 'failed'

    # Port forward representation.
    src = str(self._src_port) + (
        ':%s' % self._src_host if self._src_host else '')
    dst = str(self._dst_port) + (
        ':%s' % self._dst_host if self._dst_host else '')
    if self._forward_to == self.REMOTE:
      fwd_str = '%s->%s' % (src, dst)
    else:
      fwd_str = '%s<-%s' % (dst, src)

    return 'SSHPortForwarder(%s,%s)' % (state_str, fwd_str)

  def _ForwardArgs(self):
    flag = '-L' if self._forward_to == self.REMOTE else '-R'
    return [flag, '%s:%d:%s:%d' % (
        self._src_host, self._src_port, self._dst_host, self._dst_port)]

  def _RunSSHCmd(self):
    """Runs the SSH command, storing the exception on failure."""
    try:
      cmd = [
          'ssh',
          '-o', 'StrictHostKeyChecking=no',
          '-o', 'GlobalKnownHostsFile=/dev/null',
          '-o', 'UserKnownHostsFile=/dev/null',
          '-o', 'ExitOnForwardFailure=yes',
          '-o', 'ConnectTimeout=%d' % self._connect_timeout,
          '-o', 'ServerAliveInterval=%d' % self._alive_interval,
          '-o', 'ServerAliveCountMax=1',
          '-o', 'TCPKeepAlive=yes',
          '-o', 'BatchMode=yes',
          '-i', self._identity_file,
          '-N',
          '-p', str(self._port),
          '%s@%s' % (self._user, self._host),
      ] + self._ForwardArgs() + self._extra_args
      logging.info(' '.join(cmd))
      self._ssh_output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
      self._exception = e
    finally:
      pass

  def _Run(self, disconnect_wait, retries):
    """Wraps around the SSH command, detecting its connection status."""
    while True:
      logging.info('%s: Connecting to %s:%d',
                   self, self._host, self._port)

      # Set identity file permissions.  Need to only be user-readable for SSH to
      # use the key.
      try:
        identity_mode = os.stat(self._identity_file).st_mode
        if identity_mode & 0o77 or not identity_mode & 0o400:
          logging.error('%s: Please set file permissions 0600 on %s',
                        self, self._identity_file)
          self._state = self.FAILED
          return
      except OSError as e:
        logging.error('%s: Error accessing identity file: %s', self, e)
        self._state = self.FAILED
        return

      # Start a thread.  If it fails, deal with the failure.  If it is still
      # running after connect_timeout seconds, assume everything's working
      # great, and tell the caller.  Then, continue waiting for it to end.
      self._ssh_thread = threading.Thread(target=self._RunSSHCmd)
      self._ssh_thread.daemon = True
      self._ssh_thread.start()

      # See if the SSH thread is still working after connect_timeout.
      self._ssh_thread.join(self._connect_timeout)
      if self._ssh_thread.is_alive():
        # Assumed to be working.  Tell our caller that we are connected.
        if self._state != self.INITIALIZED:
          self._state = self.INITIALIZED
          self._poll.set()
        logging.info('%s: Still connected after timeout=%ds',
                     self, self._connect_timeout)

      # Only for debug purposes.  Keep showing connection status.
      while self._ssh_thread.is_alive():
        logging.debug('%s: Still connected', self)
        self._ssh_thread.join(self._DEBUG_INTERVAL)

      # Figure out what went wrong.
      if not self._exception:
        logging.info('%s: SSH unexpectedly exited: %s',
                     self, self._ssh_output.rstrip())
      if self._exception and self._FAILED_STR in self._exception.output:
        logging.info('%s: Port forwarding failed', self)
        # If retry_on_forward_failure is set, keep retrying.
        if not self._retry_on_forward_failure:
          self._state = self.FAILED
          self._poll.set()
          return
      if retries == 1:
        logging.info('%s: Disconnected (0 retries left)', self)
        self._state = self.FAILED
        self._poll.set()
        return
      elif retries == 0:
        logging.info('%s: Disconnected, retrying (sleep %ds)',
                     self, disconnect_wait)
        time.sleep(disconnect_wait)
        disconnect_wait = disconnect_wait * (2 ** self._exp_factor)
      else:
        logging.info('%s: Disconnected, retrying (sleep %ds, %d retries left)',
                     self, disconnect_wait, retries - 1)
        time.sleep(disconnect_wait)
        disconnect_wait = disconnect_wait * (2 ** self._exp_factor)
        retries -= 1

  def GetState(self):
    """Returns the current connection state.

    State may be one of:

      CONNECTING: Still attempting to make the first successful connection.
      INITIALIZED: Is either connected or is trying to make subsequent
          connection.
      FAILED: Has completed all connection attempts, or server has reported that
          target port is in use.
    """
    return self._state

  def GetDstPort(self):
    """Returns the current target port."""
    return self._dst_port

  def Wait(self):
    """Waits for a state change, and returns the new state."""
    self._poll.wait()
    self._poll.clear()
    return self.GetState()


def main():
  parser = argparse.ArgumentParser(description='SSH port forwarding watchdog')
  parser.add_argument(
      'src_port', type=int,
      help='source port for traffic forwarding')
  parser.add_argument(
      'direction', choices=['in', 'out'],
      help='forward traffic from remote host "in" to the local host, '
           'or from local host "out" to the remote host')
  parser.add_argument(
      'dst_port', type=int,
      help='destination port for traffic forwarding')
  parser.add_argument(
      'host',
      help='host of remote server')
  parser.add_argument(
      'user',
      help='username on remote server')
  parser.add_argument(
      'identity_file',
      help='identity file for passwordless authentication on remote server')
  parser.add_argument(
      'extra_args', nargs=argparse.REMAINDER,
      help='extra arguments to pass to SSH')
  parser.add_argument(
      '-s', '--src-host', type=str,
      help='bind to hostname on the source for traffic forwarding; NOTE: '
           'for this to work correctly on a remote host, the remote sshd '
           'configuration must have GatewayPorts set to "clientspecified"')
  parser.add_argument(
      '-d', '--dst-host', type=str,
      help='send traffic to hostname on the destination for traffic forwarding')
  parser.add_argument(
      '-p', '--port', type=int,
      help='port of remote server')
  parser.add_argument(
      '-r', '--retries', type=int,
      help='the number of times to retry before reporting a failed '
           'connection (0 means retry forever)')
  parser.add_argument(
      '--exit-on-forward-failure', action='store_true',
      help='whether or not to exit after successfully connecting, but not '
           'successfully forwarding the port (it is probably in use)')
  parser.add_argument(
      '--connect-timeout', type=int,
      help='the number of seconds to wait before assuming the SSH '
           'connection has succeeded')
  parser.add_argument(
      '--alive-interval', type=int,
      help='the number of seconds to wait before sending a keep-alive '
           'packet to the server')
  parser.add_argument(
      '--disconnect-wait', type=int,
      help='the number of seconds to wait before reconnecting after the first '
           'disconnect (subsequently multiplied by 2^exp_factor each time)')
  parser.add_argument(
      '--exp-factor', type=float,
      help='on each reconnect, the disconnect wait time is multiplied '
           'by 2^exp_factor')
  parser.add_argument(
      '-q', '--silent', action='store_true',
      help='do not display any output')

  args = parser.parse_args()

  # Set logging level based on --silent flag.
  logging.basicConfig(
      level=logging.ERROR if args.silent else logging.INFO)

  if args.direction == 'in':
    forward_to = SSHPortForwarder.LOCAL
  else:  # 'out'
    forward_to = SSHPortForwarder.REMOTE

  try:
    SSHPortForwarder(
        forward_to=forward_to,
        src_port=args.src_port,
        dst_port=args.dst_port,
        user=args.user,
        identity_file=args.identity_file,
        host=args.host,
        port=args.port,
        src_host=args.src_host,
        dst_host=args.dst_host,
        extra_args=args.extra_args,
        retries=args.retries,
        retry_on_forward_failure=not args.exit_on_forward_failure,
        connect_timeout=args.connect_timeout,
        alive_interval=args.alive_interval,
        disconnect_wait=args.disconnect_wait,
        exp_factor=args.exp_factor,
        blocking=True)  # always block
  except KeyboardInterrupt:
    sys.exit(_CTRL_C_EXIT_CODE)


if __name__ == '__main__':
  main()
