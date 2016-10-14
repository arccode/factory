#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Transition to release state directly without reboot."""

import json
import logging
import os
import re
import resource
import shutil
import signal
import socket
import tempfile
import textwrap
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.gooftool import chroot
from cros.factory.gooftool.common import ExecFactoryPar
from cros.factory.gooftool.common import Util
from cros.factory.test.env import paths
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import sys_utils


"""Directory of scripts for device cut-off"""
CUTOFF_SCRIPT_DIR = '/usr/local/factory/sh/cutoff'

WIPE_IN_TMPFS_LOG = 'wipe_in_tmpfs.log'


def _CopyLogFileToStateDev(state_dev, logfile):
  with sys_utils.MountPartition(state_dev,
                                rw=True,
                                fstype='ext4') as mount_point:
    shutil.copyfile(logfile,
                    os.path.join(mount_point, os.path.basename(logfile)))


def _OnError(ip, port, token, state_dev, wipe_in_tmpfs_log=None,
             wipe_init_log=None):
  if wipe_in_tmpfs_log:
    _CopyLogFileToStateDev(state_dev, wipe_in_tmpfs_log)
  if wipe_init_log:
    _CopyLogFileToStateDev(state_dev, wipe_init_log)
  _InformStation(ip, port, token,
                 wipe_in_tmpfs_log=wipe_in_tmpfs_log,
                 wipe_init_log=wipe_init_log,
                 success=False)


def Daemonize(logfile=None):
  """Starts a daemon process and terminates current process.

  A daemon process will be started, and continue excuting the following codes.
  The original process that calls this function will be terminated.

  Example::

    def DaemonFunc():
      Daemonize()
      # the process calling DaemonFunc is terminated.
      # the following codes will be executed in a daemon process
      ...

  If you would like to keep the original process alive, you could fork a child
  process and let child process start the daemon.
  """
  # fork from parent process
  if os.fork():
    # stop parent process
    os._exit(0)  # pylint: disable=protected-access

  # decouple from parent process
  os.chdir('/')
  os.umask(0)
  os.setsid()

  # fork again
  if os.fork():
    os._exit(0)  # pylint: disable=protected-access

  maxfd = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
  if maxfd == resource.RLIM_INFINITY:
    maxfd = 1024

  for fd in xrange(maxfd):
    try:
      os.close(fd)
    except OSError:
      pass

  # Reopen fd 0 (stdin), 1 (stdout), 2 (stderr) to prevent errors from reading
  # or writing to these files.
  # Since we have closed all file descriptors, os.open should open a file with
  # file descriptor equals to 0
  os.open('/dev/null', os.O_RDWR)
  if logfile is None:
    os.dup2(0, 1)  # stdout
    os.dup2(0, 2)  # stderr
  else:
    os.open(logfile, os.O_RDWR | os.O_CREAT)
    os.dup2(1, 2)  # stderr


def ResetLog(logfile=None):
  if len(logging.getLogger().handlers) > 0:
    for handler in logging.getLogger().handlers:
      logging.getLogger().removeHandler(handler)
  logging.basicConfig(filename=logfile, level=logging.NOTSET)


def WipeInTmpFs(is_fast=None, cutoff_args=None, shopfloor_url=None,
                station_ip=None, station_port=None, wipe_finish_token=None):
  """prepare to wipe by pivot root to tmpfs and unmount statefull partition.

  Args:
    is_fast: whether or not to apply fast wipe.
    cutoff_args: arguments to be passed to cutoff.sh after wiping.
    shopfloor_url: for inform_shopfloor.sh
  """

  Daemonize()

  # Set the defual umask.
  os.umask(0022)

  logfile = os.path.join('/tmp', WIPE_IN_TMPFS_LOG)
  ResetLog(logfile)

  factory_par = paths.GetFactoryPythonArchivePath()

  new_root = tempfile.mkdtemp(prefix='tmpfs.')
  binary_deps = [
      'activate_date', 'backlight_tool', 'busybox', 'cgpt', 'cgpt.bin',
      'clobber-log', 'clobber-state', 'coreutils', 'crossystem', 'dd',
      'display_boot_message', 'dumpe2fs', 'ectool', 'flashrom', 'halt',
      'initctl', 'mkfs.ext4', 'mktemp', 'mosys', 'mount', 'mount-encrypted',
      'od', 'pango-view', 'pkill', 'pv', 'python', 'reboot', 'setterm', 'sh',
      'shutdown', 'stop', 'umount', 'vpd', 'wget', 'lsof']
  if os.path.exists('/sbin/frecon'):
    binary_deps.append('/sbin/frecon')
  else:
    binary_deps.append('/usr/bin/ply-image')

  etc_issue = textwrap.dedent("""
    You are now in tmp file system created for in-place wiping.

    For debugging wiping fails, see log files under
    /tmp
    /mnt/stateful_partition/unencrypted

    The log file name should be
    - wipe_in_tmpfs.log
    - wipe_init.log

    You can also run scripts under /usr/local/factory/sh for wiping process.
    """)

  util = Util()

  root_disk = util.GetPrimaryDevicePath()
  release_rootfs = util.GetReleaseRootPartitionPath()
  state_dev = util.GetPrimaryDevicePath(1)
  wipe_args = 'factory' + (' fast' if is_fast else '')

  logging.debug('state_dev: %s', state_dev)
  logging.debug('factory_par: %s', factory_par)

  old_root = 'old_root'

  try:
    # pango load library module dynamically. Therefore we need to query it
    # first.
    pango_query_output = process_utils.SpawnOutput(
        ['pango-querymodules', '--system'])
    m = re.search(r'^# ModulesPath = (.+)$', pango_query_output, re.M)
    assert m != None, 'Failed to find pango module path.'
    pango_module = m.group(1)

    with chroot.TmpChroot(
        new_root,
        file_dir_list=[
            # Basic rootfs.
            '/bin', '/etc', '/lib', '/lib64', '/root', '/sbin',
            # Factory related scripts.
            factory_par,
            '/usr/local/factory/sh',
            # Fonts and assets required for showing message.
            pango_module,
            '/usr/share/fonts/notocjk',
            '/usr/share/cache/fontconfig',
            '/usr/share/chromeos-assets/images',
            '/usr/share/chromeos-assets/text/boot_messages',
            '/usr/share/misc/chromeos-common.sh',
            # File required for enable ssh connection.
            '/mnt/stateful_partition/etc/ssh',
            '/root/.ssh',
            '/usr/share/chromeos-ssh-config',
            # /var/empty is required by openssh server.
            '/var/empty'],
        binary_list=binary_deps, etc_issue=etc_issue).PivotRoot(old_root):
      logging.debug(
          'lsof: %s',
          process_utils.SpawnOutput('lsof -p %d' % os.getpid(), shell=True))

      process_utils.Spawn(['sync'], call=True)
      time.sleep(3)

      # Restart gooftool under new root. Since current gooftool might be using
      # some resource under stateful partition, restarting gooftool ensures that
      # everything new gooftool is using comes from tmpfs and we can safely
      # unmount stateful partition.
      args = []
      if wipe_args:
        args += ['--wipe_args', wipe_args]
      if cutoff_args:
        args += ['--cutoff_args', cutoff_args]
      if shopfloor_url:
        args += ['--shopfloor_url', shopfloor_url]
      if station_ip:
        args += ['--station_ip', station_ip]
      if station_port:
        args += ['--station_port', station_port]
      if wipe_finish_token:
        args += ['--wipe_finish_token', wipe_finish_token]
      args += ['--state_dev', state_dev]
      args += ['--release_rootfs', release_rootfs]
      args += ['--root_disk', root_disk]
      args += ['--old_root', old_root]

      ExecFactoryPar('gooftool', 'wipe_init', *args)
      raise RuntimeError('Should not reach here')
  except:  # pylint: disable=bare-except
    logging.exception('wipe_in_place failed')
    _OnError(station_ip, station_port, wipe_finish_token, state_dev,
             wipe_in_tmpfs_log=logfile, wipe_init_log=None)
    raise


def _StopAllUpstartJobs(exclude_list=None):
  logging.debug('stopping upstart jobs')

  # Try three times to stop running services because some service will respawn
  # one time after being stopped, e.g. shill_respawn. Two times should be enough
  # to stop shill. Adding one more try for safety.

  if exclude_list is None:
    exclude_list = []

  for unused_tries in xrange(3):
    service_list = process_utils.SpawnOutput(['initctl', 'list']).splitlines()
    service_list = [
        line.split()[0] for line in service_list if 'start/running' in line]
    for service in service_list:
      if service in exclude_list or service.startswith('console-'):
        continue
      process_utils.Spawn(['stop', service], call=True, log=True)


def _UnmountStatefulPartition(root, state_dev):
  logging.debug('unmount stateful partition')
  # mount points that need chromeos_shutdown to umount

  # 1. find mount points on stateful partition
  mount_output = process_utils.SpawnOutput(['mount'], log=True)

  mount_point_list = []
  for line in mount_output.splitlines():
    fields = line.split()
    if fields[0] == state_dev:
      mount_point_list.append(fields[2])

  logging.debug('stateful partitions mounted on: %s', mount_point_list)
  # 2. find processes that are using stateful partitions

  def _ListProcOpening(path_list):
    lsof_cmd = ['lsof', '-t'] + path_list
    return [int(line)
            for line in process_utils.SpawnOutput(lsof_cmd).splitlines()]

  proc_list = _ListProcOpening(mount_point_list)

  if os.getpid() in proc_list:
    logging.error('wipe_init itself is using stateful partition')
    logging.error(
        'lsof: %s',
        process_utils.SpawnOutput('lsof -p %d' % os.getpid(), shell=True))
    raise RuntimeError('using stateful partition')

  def _KillOpeningBySignal(sig):
    proc_list = _ListProcOpening(mount_point_list)
    if not proc_list:
      return True  # we are done
    for pid in proc_list:
      try:
        os.kill(pid, sig)
      except:  # pylint: disable=bare-except
        logging.exception('killing process %d failed', pid)
    return False  # need to check again

  sync_utils.Retry(10, 0.1, None, _KillOpeningBySignal, signal.SIGTERM)
  sync_utils.Retry(10, 0.1, None, _KillOpeningBySignal, signal.SIGKILL)

  proc_list = _ListProcOpening(mount_point_list)
  assert not proc_list, "processes using stateful partition: %s" % proc_list

  os.unlink(os.path.join(root, 'var', 'run'))
  os.unlink(os.path.join(root, 'var', 'lock'))

  if os.path.exists(os.path.join(root, 'dev', 'mapper', 'encstateful')):
    # Doing what 'mount-encrypted umount' should do.
    for mount_point in mount_point_list:
      process_utils.Spawn(['umount', '-n', '-R', mount_point], call=True)
    process_utils.Spawn(['umount', '-nR', os.path.join(root, 'var')],
                        check_call=True)
    process_utils.Spawn(['dmsetup', 'remove', 'encstateful'], check_call=True)
    process_utils.Spawn(['losetup', '-D'], check_call=True)

  for mount_point in mount_point_list:
    process_utils.Spawn(['umount', '-n', '-R', mount_point], call=True)
  process_utils.Spawn(['sync'], call=True)

  # Check if the stateful partition is unmounted successfully.
  process_utils.Spawn(r'mount | grep -c "^\S*stateful" | grep -q ^0$',
                      shell=True, check_call=True)


def _InformStation(ip, port, token, wipe_init_log=None,
                   wipe_in_tmpfs_log=None, success=True):
  if not ip:
    return
  port = int(port)

  logging.debug('inform station %s:%d', ip, port)

  try:
    sync_utils.WaitFor(
        lambda: 0 == process_utils.Spawn(['ping', '-w1', '-c1', ip],
                                         call=True).returncode,
        timeout_secs=180, poll_interval=1)
  except:  # pylint: disable=bare-except
    logging.exception('cannot get network connection...')
  else:
    sock = socket.socket()
    sock.connect((ip, port))

    response = dict(token=token, success=success)

    if wipe_init_log:
      with open(wipe_init_log) as f:
        response['wipe_init_log'] = f.read()

    if wipe_in_tmpfs_log:
      with open(wipe_in_tmpfs_log) as f:
        response['wipe_in_tmpfs_log'] = f.read()

    sock.sendall(json.dumps(response) + '\n')
    sock.close()


def _WipeStateDev(release_rootfs, root_disk, wipe_args):
  stateful_partition_path = '/mnt/stateful_partition'

  clobber_state_env = os.environ.copy()
  clobber_state_env.update(ROOT_DEV=release_rootfs,
                           ROOT_DISK=root_disk,
                           FACTORY_RETURN_AFTER_WIPING='YES')
  logging.debug('clobber-state: root_dev=%s, root_disk=%s',
                release_rootfs, root_disk)
  process_utils.Spawn(['clobber-state', wipe_args], env=clobber_state_env,
                      call=True)

  shutil.move('/tmp/clobber-state.log', os.path.join(stateful_partition_path,
                                                     'unencrypted',
                                                     'clobber-state.log'))
  # remove developer flag, which is created by clobber-state after wiping.
  try:
    os.unlink(os.path.join(stateful_partition_path, '.developer_mode'))
  except OSError:
    pass
  # make sure that everything is synced
  for unused_i in xrange(3):
    process_utils.Spawn(['sync'], call=True)
    time.sleep(1)


def EnableReleasePartition(release_rootfs):
  """Enables a release image partition on disk."""
  logging.debug('enable release partition: %s', release_rootfs)
  Util().EnableReleasePartition(release_rootfs)
  logging.debug('Device will boot from %s after reboot.', release_rootfs)


def _InformShopfloor(shopfloor_url):
  if shopfloor_url:
    logging.debug('inform shopfloor %s', shopfloor_url)
    proc = process_utils.Spawn(
        [os.path.join(CUTOFF_SCRIPT_DIR, 'inform_shopfloor.sh'), shopfloor_url,
         'factory_wipe'], check_call=True)
    logging.debug('stdout: %s', proc.stdout_data)
    logging.debug('stderr: %s', proc.stderr_data)


def _Cutoff(cutoff_args):
  if cutoff_args is None:
    cutoff_args = ''
  logging.debug('cutoff: args=%s', cutoff_args)
  cutoff_script = os.path.join(CUTOFF_SCRIPT_DIR, 'cutoff.sh')
  process_utils.Spawn('%s %s' % (cutoff_script, cutoff_args),
                      shell=True, check_call=True)


def WipeInit(wipe_args, cutoff_args, shopfloor_url, state_dev, release_rootfs,
             root_disk, old_root, station_ip, station_port, finish_token):
  Daemonize()
  logfile = '/tmp/wipe_init.log'
  wipe_in_tmpfs_log = os.path.join(old_root, 'tmp', WIPE_IN_TMPFS_LOG)
  ResetLog(logfile)

  logging.debug('wipe_args: %s', wipe_args)
  logging.debug('cutoff_args: %s', cutoff_args)
  logging.debug('shopfloor_url: %s', shopfloor_url)
  logging.debug('state_dev: %s', state_dev)
  logging.debug('release_rootfs: %s', release_rootfs)
  logging.debug('root_disk: %s', root_disk)
  logging.debug('old_root: %s', old_root)

  try:
    _StopAllUpstartJobs(exclude_list=[
        # Milestone marker that use to determine the running of other services.
        'boot-services',
        'system-services',
        'failsafe',
        # Keep dbus to make sure we can shutdown the device.
        'dbus',
        # Keep shill for connecting to shopfloor or stations.
        'shill',
        # Keep openssh-server for debugging purpose.
        'openssh-server',
        # sslh is a service in ARC++ for muxing between ssh and adb.
        'sslh'
        ])
    _UnmountStatefulPartition(old_root, state_dev)

    process_utils.Spawn(
        [os.path.join(CUTOFF_SCRIPT_DIR, 'display_wipe_message.sh'), 'wipe'],
        call=True)

    _WipeStateDev(release_rootfs, root_disk, wipe_args)

    EnableReleasePartition(release_rootfs)

    _InformShopfloor(shopfloor_url)

    _InformStation(station_ip, station_port, finish_token,
                   wipe_init_log=logfile,
                   wipe_in_tmpfs_log=wipe_in_tmpfs_log,
                   success=True)

    _Cutoff(cutoff_args)

    # should not reach here
    time.sleep(1e8)
  except:  # pylint: disable=bare-except
    logging.exception('wipe_init failed')
    _OnError(station_ip, station_port, finish_token, state_dev,
             wipe_in_tmpfs_log=wipe_in_tmpfs_log, wipe_init_log=logfile)
    raise
