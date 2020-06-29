# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of cros.factory.device.device_types.DeviceLink using SSH."""

import logging
import os
import pipes
import queue
import subprocess
import tempfile
import threading
import time

from cros.factory.device import device_types
from cros.factory.test import state
from cros.factory.test.utils import dhcp_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


_DEVICE_DATA_KEY = 'DYNAMIC_SSH_TARGET_IP'


class ClientNotExistError(Exception):
  def __str__(self):
    return 'There is no DHCP client registered.'


class SSHProcess:
  ERROR_CONNECTION_TIMEOUT = 255
  MAX_RETRY = 3
  INTERVAL = 1

  def __init__(self, *args, **kwargs):
    self.__args = args
    self.__kwargs = kwargs
    self.__process = self._create_process()
    self.__retry_count = 0

  def __getattr__(self, attr):
    return getattr(self.__process, attr)

  def _create_process(self):
    return subprocess.Popen(*self.__args, **self.__kwargs)

  def wait(self):
    returncode = self.__process.wait()
    if (returncode == self.ERROR_CONNECTION_TIMEOUT and
        self.__retry_count < self.MAX_RETRY):
      time.sleep(self.INTERVAL)
      self.__retry_count += 1
      self.__process = self._create_process()
      return self.wait()
    return returncode


class SSHLink(device_types.DeviceLink):
  """A DUT target that is connected via SSH interface.

  Properties:
    host: A string for SSH host, if it's None, will get from shared data.
    user: A string for the user accont to login. Defaults to 'root'.
    port: An integer for the SSH port on remote host.
    identify: An identity file to specify credential.
    use_ping: A bool, whether using ping(8) to check connection with DUT or not.
              If it's False, will use ssh(1) instead. This is useful if DUT
              drops incoming ICMP packets.
    connect_timeout: An integer for ssh(1) connection timeout in seconds.
    control_persist: An integer for ssh(1) to keep master connection remain
              opened for given seconds, or None to not using master control.

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
          'interface_blocklist_file': '/path/to/blocklist/file',
          'exclude_ip_prefix': [('10.0.0.0', 24), ...],
          # the following three properties can only be set in python script,
          # not in environment variable (CROS_FACTORY_DUT_OPTIONS)
          'on_add': None,
          'on_old': None,
          'on_del': None,
        }
      }
  """

  def __init__(self, host=None, user='root', port=22, identity=None,
               use_ping=True, connect_timeout=1, control_persist=300):
    self._host = host
    self.user = user
    self.port = port
    self.identity = identity
    self.use_ping = use_ping
    self.connect_timeout = connect_timeout
    self.control_persist = control_persist

    self._state = state.GetInstance()

  @property
  def host(self):
    if self._host is None:
      if not state.DataShelfHasKey(_DEVICE_DATA_KEY):
        raise ClientNotExistError
      return state.DataShelfGetValue(_DEVICE_DATA_KEY)
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
               '-o', 'StrictHostKeyChecking=no',
               '-o', 'ConnectTimeout=%d' % self.connect_timeout]
    if self.control_persist is not None:
      options += ['-o', 'ControlMaster=auto',
                  '-o', 'ControlPath=/tmp/.ssh-%r@%h:%p',
                  '-o', 'ControlPersist=%s' % self.control_persist]
    if self.port:
      options += ['-P' if is_scp else '-p', str(self.port)]
    if self.identity:
      options += ['-i', self.identity]
    return sig, options

  def _DoSCP(self, src, dest, is_push, options=None, max_retry=3):
    remote_sig, scp_options = self._signature(True)

    if is_push:
      dest = '%s:%s' % (remote_sig, dest)
    else:
      src = '%s:%s' % (remote_sig, src)

    if options:
      if isinstance(options, list):
        scp_options += options
      elif isinstance(options, str):
        scp_options.append(options)
      else:
        raise ValueError('options must be a list or string (got %r)' % options)

    def _TryOnce():
      with tempfile.TemporaryFile('w+') as stderr:
        proc = subprocess.Popen(['scp'] + scp_options + [src, dest],
                                stderr=stderr)
        self._StartWatcher(proc)
        returncode = proc.wait()

        if returncode != 0:
          # SCP returns error code "1" for SSH connection failure,
          # which means "generic error".
          # Therefore, we cannot tell the difference between connection failure
          # and other errors (e.g. file not found) by looking at return code
          # only, we need to parse the error message.
          stderr.flush()
          stderr.seek(0)
          error = stderr.read()
          SSH_CONNECT_ERROR_MSG = [
              'ssh: connect to host',
              'Connection timed out',
          ]
          if [msg for msg in SSH_CONNECT_ERROR_MSG if msg in error]:
            # this is a connection issue
            logging.warning(error)
            return False
        # either succeeded, or failed by other reasons, stop trying
        return (True, returncode)

    def _Callback(retry_time, max_retry_times):
      logging.info('SCP: src=%s, dst=%s (%d/%d)',
                   src, dest, retry_time, max_retry_times)

    result = sync_utils.Retry(
        max_retry, 0.1, callback=_Callback, target=_TryOnce)

    returncode = result[1] if result else 255
    if returncode:
      raise subprocess.CalledProcessError(
          returncode, 'SCP failed: src=%s, dst=%s' % (src, dest))
    return 0

  def Push(self, local, remote):
    """See DeviceLink.Push"""
    return self._DoSCP(local, remote, is_push=True)

  def PushDirectory(self, local, remote):
    """See DeviceLink.PushDirectory"""
    return self._DoSCP(local, remote, is_push=True, options='-r')

  def Pull(self, remote, local=None):
    """See DeviceLink.Pull"""
    if local is None:
      with file_utils.UnopenedTemporaryFile() as path:
        self.Pull(remote, path)
        with open(path) as f:
          return f.read()

    return self._DoSCP(remote, local, is_push=False)

  def _StartWatcher(self, subproc):
    watcher = self.__class__.ControlMasterWatcher(self)
    watcher.Start()  # make sure the watcher is running
    watcher.AddProcess(subproc.pid, os.getpid())

  def Shell(self, command, stdin=None, stdout=None, stderr=None, cwd=None,
            encoding='utf-8'):
    """See DeviceLink.Shell"""
    remote_sig, options = self._signature(False)

    if not isinstance(command, str):
      command = ' '.join(map(pipes.quote, command))
    if cwd:
      command = 'cd %s ; %s' % (pipes.quote(cwd), command)

    command = ['ssh'] + options + [remote_sig, command]

    logging.debug('SSHLink: Run [%r]', command)
    proc = SSHProcess(command, shell=False, close_fds=True, stdin=stdin,
                      stdout=stdout, stderr=stderr, encoding=encoding)
    self._StartWatcher(proc)
    return proc

  def IsReady(self):
    """See DeviceLink.IsReady"""
    try:
      if self.use_ping:
        cmd = ['ping', '-w', '1', '-c', '1', self.host]
      else:
        remote_sig, options = self._signature(False)
        cmd = ['ssh'] + options + [remote_sig] + ['true']
      return subprocess.call(cmd) == 0
    except Exception:
      return False

  _dhcp_manager = None
  _dhcp_manager_lock = threading.Lock()

  @classmethod
  def SetLinkIP(cls, ip):
    state.DataShelfSetValue(_DEVICE_DATA_KEY, ip)

  @classmethod
  def ResetLinkIP(cls):
    if state.DataShelfHasKey(_DEVICE_DATA_KEY):
      state.DataShelfDeleteKeys(_DEVICE_DATA_KEY)

  # pylint: disable=arguments-differ
  @classmethod
  def PrepareLink(cls,
                  start_dhcp_server=True,
                  start_dhcp_server_after_ping=None,
                  dhcp_server_args=None):
    """Prepare for SSHLink connection

    Arguments:
      start_dhcp_server (default: False):
        Start the default DHCP server or not
      start_dhcp_server_after_ping (default: None):
        Start the DHCP server only after a successfully ping to a target.
        This should be a dict like: {
          "host": "192.168.234.1",
          "timeout_secs": 30,
          "interval_secs": 1
        }, with the ``timeout_secs`` and ``interval_secs`` being optional.
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

      wait_ping = start_dhcp_server_after_ping or {}
      cls._WaitPing(**wait_ping)

      cls._dhcp_manager = cls.LinkManager(**options)
      cls._dhcp_manager.Start()

  @classmethod
  def _WaitPing(cls, host=None, timeout_secs=30, interval_secs=1):
    if not host:
      return

    def ping():
      cmd = ['ping', '-w', '1', '-c', '1', host]
      return subprocess.call(cmd) == 0

    sync_utils.PollForCondition(ping,
                                timeout_secs=timeout_secs,
                                poll_interval_secs=interval_secs)

  class ControlMasterWatcher(metaclass=type_utils.Singleton):
    def __init__(self, link_instance):
      assert isinstance(link_instance, SSHLink)

      self._link = link_instance
      self._thread = threading.Thread(target=self.Run)
      self._proc_queue = queue.Queue()

      self._user = self._link.user
      self._host = self._link._host  # pylint: disable=protected-access
      self._port = self._link.port
      self._link_class_name = self._link.__class__.__name__

    def IsRunning(self):
      if not self._thread:
        return False
      if not self._thread.is_alive():
        self._thread = None
        return False
      return True

    def Start(self):
      if self.IsRunning():
        return

      if self._link.control_persist is None:
        logging.debug('%s %s@%s:%s is not using control master, don\'t start',
                      self._link_class_name, self._user, self._host, self._port)
        return

      self._thread = process_utils.StartDaemonThread(target=self.Run)

    def AddProcess(self, pid, ppid=None):
      """Add an SSH process to monitor.

      If any of added SSH process is still running, ControlMasterWatcher will
      keep monitoring network connectivity.  If network is down, control master
      will be killed.

      Args:
        pid: PID of process using SSH
        ppid: parent PID of given process
      """
      if not self.IsRunning():
        logging.warning('Watcher is not running, %d is not added', pid)
        return
      self._proc_queue.put((pid, ppid))

    def Run(self):
      logging.debug('start monitoring control master')

      # an alias to prevent duplicated pylint warnings
      # pylint: disable=protected-access
      _GetLinkSignature = self._link._signature

      def _IsControlMasterRunning():
        sig, options = _GetLinkSignature(False)
        return subprocess.call(
            ['ssh', '-O', 'check'] + options + [sig, 'true']) == 0

      def _StopControlMaster():
        sig, options = _GetLinkSignature(False)
        subprocess.call(['ssh', '-O', 'exit'] + options + [sig, 'true'])

      def _CallTrue():
        sig, options = _GetLinkSignature(False)
        proc = subprocess.Popen(['ssh'] + options + [sig, 'true'])
        time.sleep(1)
        returncode = proc.poll()
        if returncode != 0:
          proc.kill()
          return False
        return True

      def _PollingCallback(is_process_alive):
        if not is_process_alive:
          return True  # returns True to stop polling

        try:
          if not _IsControlMasterRunning():
            logging.info('control master is not running, skipped')
            return False

          if not _CallTrue():
            logging.info('loss connection, stopping control master')
            _StopControlMaster()
        except Exception:
          logging.info('monitoring %s to %s@%s:%s',
                       self._link_class_name,
                       self._user, self._host, self._port, exc_info=True)
        return False

      while True:
        # get a new process from queue to monitor
        # since queue.get will block if queue is empty, we don't need to sleep
        pid, ppid = self._proc_queue.get()
        logging.debug('start monitoring control master until %d terminates',
                      pid)

        sync_utils.PollForCondition(
            lambda: process_utils.IsProcessAlive(pid, ppid),
            condition_method=_PollingCallback,
            timeout_secs=None,
            poll_interval_secs=1)


  class LinkManager:
    def __init__(self,
                 lease_time=3600,
                 interface_blocklist_file=None,
                 exclude_ip_prefix=None,
                 on_add=None,
                 on_old=None,
                 on_del=None):
      """
        A LinkManager will automatically start a DHCP server for each availiable
        network interfaces, if the interface is not default gateway or in the
        blocklist.

        This LinkManager will automatically save IP of the latest client in
        system-wise shared data, make it availible to SSHLinks whose host is set
        to None.

        Options:
          lease_time:
            lease time of DHCP servers
          interface_blocklist_file:
            a path to the file of blocklist, each line represents an interface
            (e.g. eth0, wlan1, ...)
          exclude_ip_prefix:
            some IP range cannot be used becase of system settings, this
            argument should be a list of tuple of (ip, prefix_bits).
          on_add, on_old, on_del:
            callback functions for DHCP servers.
      """
      self._lease_time = lease_time
      self._blocklist_file = interface_blocklist_file
      self._on_add = on_add
      self._on_old = on_old
      self._on_del = on_del
      self._dhcp_server = None
      self._exclude_ip_prefix = exclude_ip_prefix

      self._devices = type_utils.UniqueStack()

    def _SetLastDUT(self):
      last_dut = self._devices.Get()
      if last_dut:
        SSHLink.SetLinkIP(last_dut[0])
      else:
        SSHLink.ResetLinkIP()

    def _OnDHCPAdd(self, ip, mac_address):
      # update last device
      self._devices.Add((ip, mac_address))
      self._SetLastDUT()

      # invoke callback function
      if callable(self._on_add):
        self._on_add(ip, mac_address)

    def _OnDHCPOld(self, ip, mac_address):
      # update last device
      self._devices.Add((ip, mac_address))
      self._SetLastDUT()

      # invoke callback function
      if callable(self._on_old):
        self._on_old(ip, mac_address)

    def _OnDHCPDel(self, ip, mac_address):
      # remove the device
      self._devices.Del((ip, mac_address))
      self._SetLastDUT()

      # invoke callback function
      if callable(self._on_del):
        self._on_del(ip, mac_address)

    def _StartHDCPServer(self):
      self._dhcp_server = dhcp_utils.StartDHCPManager(
          blocklist_file=self._blocklist_file,
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
