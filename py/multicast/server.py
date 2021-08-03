#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Multicast service to spawn uftp server"""

import argparse
import logging
import os
import time

from cros.factory.utils import json_utils
from cros.factory.utils import process_utils


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

  def __init__(self, args: UftpArgs):
    self.args = args
    self._process = None

  def __eq__(self, other):
    return self.args == other.args

  def Spawn(self):
    addr, port = self.args.multicast_addr.split(':')

    # "-u" defines the the UDP source port, while "-p" defines the UDP
    # destination port.
    cmd = [
        UFTP_PATH, '-M', addr, '-t', self.args.TTL, '-u', port, '-p', port,
        '-x', self.args.LOG_LEVEL, '-S', self.args.status_file_path, '-C',
        self.args.CC_TYPE, '-s', self.args.ROBUST_FACTOR
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
        logging.error(self._process.stderr.read())
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
      logging.exception('Failed to read multicast config file.')
      return []

    scanned_args = []

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

        scanned_args.append(
            UftpArgs(file_path, uftp_mcast_addr, status_file_path, interface))

    return scanned_args

  def StartAll(self):
    for _args in self.uftp_args:
      proc = UftpProcess(_args)
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


def Main():
  parser = argparse.ArgumentParser()
  parser.add_argument('-l', '--log-dir', help='path to Umpire log directory',
                      required=True)

  args = parser.parse_args()

  servers = {}

  while True:
    scanned_projects = []
    for project in os.listdir(UMPIRE_DIR):
      if not (IsUmpireEnabled(project) and IsServiceEnabled(project)):
        continue

      scanned_projects.append(project)

    for project in scanned_projects:
      if project in servers:
        mcast_server = servers[project]
      else:
        mcast_server = MulticastServer(project, args.log_dir)
        servers[project] = mcast_server

      scanned_args = mcast_server.GetUftpArgsFromUmpire()
      if scanned_args != mcast_server.uftp_args:
        mcast_server.uftp_args = scanned_args
        mcast_server.StopAll()
        mcast_server.StartAll()
      else:
        mcast_server.RespawnDead()

    for project in set(servers) - set(scanned_projects):
      servers[project].StopAll()
      servers.pop(project)

    time.sleep(1)


if __name__ == '__main__':
  Main()
