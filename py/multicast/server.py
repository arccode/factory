#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Multicast service to spawn uftp server"""

import argparse
import logging
import os
import time

from cros.factory.utils import log_utils
from cros.factory.utils import json_utils
from cros.factory.utils import process_utils


LOG_FILE = 'uftp.log'
MCAST_CONFIG_NAME = 'multicast_config.json'
UMPIRE_CONFIG_NAME = 'active_umpire.json'
UMPIRE_DIR = '/var/db/factory/umpire'
UFTP_PATH = '/usr/bin/uftp'


class UftpArgs:
  CC_TYPE = 'tfmcc'  # TCP friendly multicast congestion control.
  LOG_LEVEL = '0'
  ROBUST_FACTOR = '50'  # The number of announcements sent before file transfer.
  TTL = '10'

  def __init__(self, file_path, multicast_addr, status_file_path, interface):
    """Constructor of a UFTP process argument wrapper.

    Args:
      file_path: The file path to be transferred.
      multicast_addr: The multicast address for sending announcement messages.
      status_file_path: The path for logging file transfer status.
      interface: The network interface name or IP to send the data from.
    """
    self.file_path = file_path
    self.multicast_addr = multicast_addr
    self.status_file_path = status_file_path
    self.interface = interface

  def __eq__(self, other):
    for attr in [
        'file_path', 'multicast_addr', 'status_file_path', 'interface'
    ]:
      if getattr(self, attr, '') != getattr(other, attr, ''):
        return False
    return True

  # For unit test
  def __hash__(self):
    return hash((self.file_path, self.multicast_addr, self.status_file_path,
                 self.interface))


class UftpProcess:

  def __init__(self, args: UftpArgs, logger):
    self.args = args
    self._logger = logger
    self._process = None

  def __eq__(self, other):
    return self.args == other.args

  def Spawn(self):
    addr, port = self.args.multicast_addr.split(':')

    # "-u" defines the the UDP source port, while "-p" defines the UDP
    # destination port.
    cmd = [
        UFTP_PATH, '-M', addr, '-P', addr, '-t', self.args.TTL, '-u', port,
        '-p', port, '-x', self.args.LOG_LEVEL, '-S', self.args.status_file_path,
        '-C', self.args.CC_TYPE, '-s', self.args.ROBUST_FACTOR
    ]

    if self.args.interface != '':
      cmd += ['-I', self.args.interface]

    cmd += [self.args.file_path]

    self._process = process_utils.Spawn(cmd, stderr=process_utils.PIPE)

  def RespawnIfDied(self):
    ANNOUNCE_TIMED_OUT_RETCODE = 7
    if self._process is not None and self._process.poll() is not None:
      # Skip announce timed out message.
      if self._process.returncode != ANNOUNCE_TIMED_OUT_RETCODE:
        self._logger.Log(self._process.stderr.read())
      self.Spawn()

  def Kill(self):
    self._process.kill()
    self._process.wait()


class MulticastServer:
  """Multicast server for a project."""

  def __init__(self, project, log_dir):
    self.uftp_args = []
    self._uftp_procs = []
    self._project_dir = os.path.join(UMPIRE_DIR, project)
    self._log_dir = log_dir
    self._logger = self._GetLogger(project, os.path.join(log_dir, LOG_FILE))

  @staticmethod
  def _GetLogger(project, log_path):
    # Default log level is logging.WARNING, but we only use logger.error for
    # now so no need to change it.
    logger = logging.getLogger(project)
    if not logger.hasHandlers():
      formatter = logging.Formatter(
          '%%(asctime)s:%%(levelname)s:%s:%%(message)s' % project)
      handler = logging.FileHandler(log_path)
      handler.setFormatter(formatter)
      logger.addHandler(handler)
    return log_utils.NoisyLogger(logger.error)

  def GetUftpArgsFromUmpire(self):
    """Get uftp arguments from the Umpire instance.

    Returns:
      A list of UftpArgs object.
    """
    resource_dir = os.path.join(self._project_dir, 'resources')
    try:
      mcast_config = json_utils.LoadFile(
          os.path.join(self._project_dir, MCAST_CONFIG_NAME))
    except Exception:
      self._logger.Log('Failed to read multicast config file.')
      return []

    active_args = []

    mcast_addrs = mcast_config['multicast']
    interface = mcast_config['multicast'].get('server_ip', '')

    for component in mcast_addrs:
      if component == 'server_ip':
        continue
      for part in mcast_addrs[component]:
        file_name = mcast_config[component][part]

        file_path = os.path.join(resource_dir, file_name)
        uftp_mcast_addr = mcast_addrs[component][part]
        status_file_path = os.path.join(self._log_dir,
                                        'uftp_%s.log' % file_name)

        active_args.append(
            UftpArgs(file_path, uftp_mcast_addr, status_file_path, interface))

    return active_args

  def StartAll(self):
    for _args in self.uftp_args:
      proc = UftpProcess(_args, self._logger)
      proc.Spawn()
      self._uftp_procs.append(proc)

  def StopAll(self):
    for proc in self._uftp_procs:
      proc.Kill()
    self._uftp_procs = []

  def RespawnDead(self):
    for proc in self._uftp_procs:
      proc.RespawnIfDied()


def IsUmpireEnabled(project):
  """Return True if corresponding Umpire container is running."""
  container_name = 'umpire_%s' % project

  container_list = process_utils.CheckOutput(
      ['docker', 'ps', '--all', '--format', '{{.Names}}'],
      encoding='utf-8').splitlines()
  return container_name in container_list


def IsServiceEnabled(project):
  """Return True if the multicast service is active."""
  try:
    umpire_config = json_utils.LoadFile(
        os.path.join(UMPIRE_DIR, project, UMPIRE_CONFIG_NAME))
    service_enabled = umpire_config['services']['multicast']['active']
  except Exception:
    service_enabled = False

  return service_enabled


class MulticastServerManager:

  def __init__(self, log_dir):
    self._servers = {}
    self._log_dir = log_dir

  @staticmethod
  def _ScanActiveProjects():
    return [
        project for project in os.listdir(UMPIRE_DIR)
        if IsUmpireEnabled(project) and IsServiceEnabled(project)
    ]

  def CreateAndDeleteServers(self):
    """Create new server instancess and remove inactive servers according to
    Umpire config."""
    active_projects = self._ScanActiveProjects()
    for project in set(active_projects) - set(self._servers):
      self._servers[project] = MulticastServer(project, self._log_dir)

    for project in set(self._servers) - set(active_projects):
      self._servers[project].StopAll()
      self._servers.pop(project)

  def UpdateServerArgs(self):
    """Update arguments of the servers and restart processes when needed."""
    for server in self._servers.values():
      active_args = server.GetUftpArgsFromUmpire()
      if active_args != server.uftp_args:
        server.uftp_args = active_args
        server.StopAll()
        server.StartAll()
      else:
        server.RespawnDead()

  def Run(self):
    """The main loop of multicast server manager."""
    while True:
      self.CreateAndDeleteServers()
      self.UpdateServerArgs()

      time.sleep(1)


def Main():
  parser = argparse.ArgumentParser()
  parser.add_argument('-l', '--log-dir', help='path to Umpire log directory',
                      required=True)

  args = parser.parse_args()

  manager = MulticastServerManager(args.log_dir)
  manager.Run()


if __name__ == '__main__':
  Main()
