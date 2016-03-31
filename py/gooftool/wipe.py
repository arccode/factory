#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Trainsition to release state directly without reboot."""

import logging
import json
import os
import resource
import shutil
import signal
import tempfile
import textwrap
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.gooftool import chroot
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import sys_utils


WIPE_ARGS_FILE = '/tmp/factory_wipe_args'


def OnError(state_dev, logfile):
  with sys_utils.MountPartition(state_dev,
                                rw=True,
                                fstype='ext4') as mount_point:
    shutil.copyfile(logfile,
                    os.path.join(mount_point, os.path.basename(logfile)))


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


def WipeInTmpFs(is_fast=None, cutoff_args=None, shopfloor_url=None):
  """prepare to wipe by pivot root to tmpfs and unmount statefull partition.

  Args:
    is_fast: whether or not to apply fast wipe.
    cutoff_args: arguments to be passed to battery_cutoff.sh after wiping.
    shopfloor_url: for inform_shopfloor.sh
  """

  logfile = '/tmp/wipe_in_tmpfs.log'
  Daemonize()

  ResetLog(logfile)

  factory_par = sys_utils.GetRunningFactoryPythonArchivePath()
  if not factory_par:
    # try to find factory python archive at default location
    if os.path.exists('/usr/local/factory/factory-mini.par'):
      factory_par = '/usr/local/factory/factory-mini.par'
    elif os.path.exists('/usr/local/factory/factory.par'):
      factory_par = '/usr/local/factory/factory.par'
    else:
      raise RuntimeError('cannot find factory python archive')

  new_root = tempfile.mkdtemp(prefix='tmpfs.')
  binary_deps = [
      'activate_date', 'backlight_tool', 'busybox', 'cgpt', 'cgpt.bin',
      'clobber-log', 'clobber-state', 'coreutils', 'crossystem', 'dd',
      'display_boot_message', 'dumpe2fs', 'ectool', 'flashrom', 'halt',
      'initctl', 'mkfs.ext4', 'mktemp', 'mosys', 'mount', 'mount-encrypted',
      'od', 'pango-view', 'pkill', 'pv', 'python', 'reboot', 'setterm', 'sh',
      'shutdown', 'stop', 'umount', 'vpd', 'wget', 'lsof', ]
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

  root_disk = process_utils.SpawnOutput(['rootdev', '-s', '-d']).strip()
  if root_disk[-1].isdigit():
    state_dev = root_disk + 'p1'
  else:
    state_dev = root_disk + '1'
  factory_root_dev = process_utils.SpawnOutput(['rootdev', '-s']).strip()
  wipe_args = 'factory' + (' fast' if is_fast else '')

  logging.debug('state_dev: %s', state_dev)
  logging.debug('factory_par: %s', factory_par)

  old_root = 'old_root'

  try:
    with chroot.TmpChroot(
        new_root,
        file_dir_list=[
            '/bin', '/etc', '/lib', '/lib64', '/opt', '/root', '/sbin',
            '/usr/share/fonts/notocjk',
            '/usr/share/cache/fontconfig',
            '/usr/share/chromeos-assets/images',
            '/usr/share/chromeos-assets/text/boot_messages',
            '/usr/share/misc/chromeos-common.sh',
            '/usr/local/factory/sh',
            factory_par],
        binary_list=binary_deps, etc_issue=etc_issue).PivotRoot(old_root):
      logging.debug(
          'lsof: %s',
          process_utils.SpawnOutput('lsof -p %d' % os.getpid(), shell=True))

      json.dump(dict(wipe_args=wipe_args,
                     cutoff_args=cutoff_args,
                     shopfloor_url=shopfloor_url,
                     state_dev=state_dev,
                     factory_root_dev=factory_root_dev,
                     root_disk=root_disk,
                     old_root=old_root),
                open(WIPE_ARGS_FILE, 'w'))

      process_utils.Spawn(['sync'], call=True)
      time.sleep(3)

      # Restart gooftool under new root. Since current gooftool might be using
      # some resource under stateful partition, restarting gooftool ensures that
      # everything new gooftool is using comes from tmpfs and we can safely
      # unmount stateful partition.
      # There are two factory_par in the argument because os.execl's function
      # signature is: os.execl(exec_path, arg0, arg1, ...)
      os.execl(factory_par, factory_par,
               'gooftool', 'wipe_init', '--args_file', WIPE_ARGS_FILE)
      raise RuntimeError('Should not reach here')
  except:  # pylint: disable=bare-except
    logging.exception('wipe_in_place failed')
    OnError(state_dev, logfile)
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
      if service in exclude_list:
        continue
      process_utils.Spawn(['stop', service], call=True)


def _UnmountStatefulPartition(root):
  logging.debug('unmount stateful partition')
  stateful_partition_path = os.path.join(root, 'mnt/stateful_partition')
  # mount points that need chromeos_shutdown to umount

  # 1. find mount points on stateful partition
  mount_point_list = process_utils.Spawn(
      ['mount', stateful_partition_path], read_stderr=True).stderr_data

  mount_point_list = [line.split()[5] for line in mount_point_list.splitlines()
                      if 'mounted on' in line]
  # 2. find processes that are using stateful partitions

  def _ListProcOpening(paths):
    lsof_cmd = ['lsof', '-t'] + paths
    return [int(line)
            for line in process_utils.SpawnOutput(lsof_cmd).splitlines()]

  proc_list = _ListProcOpening(mount_point_list)

  if os.getpid in proc_list:
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
      os.kill(pid, sig)
    return False  # need to check again

  sync_utils.Retry(10, 0.1, None, _KillOpeningBySignal, signal.SIGTERM)
  sync_utils.Retry(10, 0.1, None, _KillOpeningBySignal, signal.SIGKILL)

  proc_list = _ListProcOpening(mount_point_list)
  assert not proc_list, "processes using stateful partition: %s" % proc_list

  os.unlink(os.path.join(root, 'var', 'run'))
  os.unlink(os.path.join(root, 'var', 'lock'))

  if os.path.exists(os.path.join(root, 'dev', 'mapper', 'encstateful')):
    def _UmountEncrypted():
      try:
        process_utils.Spawn(['mount-encrypted', 'umount'], check_call=True)
        return True
      except:  # pylint: disable=bare-except
        return False
    sync_utils.Retry(10, 0.1, None, _UmountEncrypted)

  for mount_point in mount_point_list:
    process_utils.Spawn(['umount', '-n', '-R', mount_point], call=True)
  process_utils.Spawn(['sync'], call=True)


def WipeInit(args_file):
  logfile = '/tmp/wipe_init.log'
  ResetLog(logfile)

  args = json.load(open(args_file))

  logging.debug('args: %r', args)
  logging.debug(
      'lsof: %s',
      process_utils.SpawnOutput('lsof -p %d' % os.getpid(), shell=True))

  try:
    _StopAllUpstartJobs(exclude_list=['boot-services', 'console-tty2', 'dbus',
                                      'factory-wipe', 'shill',
                                      'openssh-server'])
    _UnmountStatefulPartition(args['old_root'])
  except:  # pylint: disable=bare-except
    logging.exception('wipe_init failed')
    OnError(args['state_dev'], logfile)
    raise

