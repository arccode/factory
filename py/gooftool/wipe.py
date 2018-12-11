# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Transition to release state directly without reboot."""

import json
import logging
import os
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
from cros.factory.gooftool.common import Shell
from cros.factory.gooftool.common import Util
from cros.factory.test.env import paths
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import sys_utils


CUTOFF_SCRIPT_DIR = '/usr/local/factory/sh/cutoff'
"""Directory of scripts for device cut-off"""

WIPE_IN_TMPFS_LOG = 'wipe_in_tmpfs.log'

STATEFUL_PARTITION_PATH = '/mnt/stateful_partition/'

WIPE_MARK_FILE = 'wipe_mark_file'

CRX_CACHE_PAYLOAD_NAME = 'cros_payloads/release_image.crx_cache'
CRX_CACHE_TAR_PATH = '/tmp/crx_cache.tar'

class WipeError(Exception):
  """Failed to complete wiping."""


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

  A daemon process will be started, and continue executing the following codes.
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
  if logging.getLogger().handlers:
    for handler in logging.getLogger().handlers:
      logging.getLogger().removeHandler(handler)
  logging.basicConfig(filename=logfile, level=logging.NOTSET)


def WipeInTmpFs(is_fast=None, shopfloor_url=None, station_ip=None,
                station_port=None, wipe_finish_token=None):
  """prepare to wipe by pivot root to tmpfs and unmount stateful partition.

  Args:
    is_fast: whether or not to apply fast wipe.
    shopfloor_url: for inform_shopfloor.sh
  """

  def _CheckBug78323428():
    # b/78323428: Check if dhcpcd is locking /var/run. If dhcpcd is locking
    # /var/run, unmount will fail. Need CL:1021611 to use /run instead.
    for pid in Shell('pgrep dhcpcd').stdout.splitlines():
      lock_result = Shell('ls -al /proc/%s/fd | grep /var/run' % pid)
      if lock_result.stdout:
        raise WipeError('dhcpcd is still locking on /var/run. Please use a '
                        'newer ChromeOS image with CL:1021611 included. '
                        'Lock info: "%s"' % lock_result.stdout)
  _CheckBug78323428()

  Daemonize()

  # Set the default umask.
  os.umask(0o022)

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
      'shutdown', 'stop', 'umount', 'vpd', 'curl', 'lsof', 'jq', '/sbin/frecon',
      'stressapptest']

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
    with chroot.TmpChroot(
        new_root,
        file_dir_list=[
            # Basic rootfs.
            '/bin', '/etc', '/lib', '/lib64', '/root', '/sbin',
            '/usr/sbin', '/usr/bin',
            # Factory related scripts.
            factory_par,
            '/usr/local/factory/sh',
            # Factory config files
            '/usr/local/factory/py/config',
            '/usr/share/fonts/notocjk',
            '/usr/share/cache/fontconfig',
            '/usr/share/chromeos-assets/images',
            '/usr/share/chromeos-assets/text/boot_messages',
            '/usr/share/misc/chromeos-common.sh',
            # lsb-factory is required for overriding cutoff configs
            '/mnt/stateful_partition/dev_image/etc/lsb-factory',
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

      # Modify display_wipe_message so we have shells in VT2.
      # --dev-mode provides shell with etc-issue.
      # --enable-vt1 allows drawing escapes (OSC) on VT1 but it'll also display
      # etc-issue and login prompt.
      # For now we only want login prompts on VT2+.
      process_utils.Spawn(['sed', '-i',
                           's/--no-login/--dev-mode/g;s/--enable-vt1//g',
                           '/usr/sbin/display_boot_message'],
                          call=True)

      # Restart gooftool under new root. Since current gooftool might be using
      # some resource under stateful partition, restarting gooftool ensures that
      # everything new gooftool is using comes from tmpfs and we can safely
      # unmount stateful partition.
      args = []
      if wipe_args:
        args += ['--wipe_args', wipe_args]
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
      raise WipeError('Should not reach here')
  except Exception:
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
    logging.info('Going to stop: services: %r', service_list)
    for service in service_list:
      if service in exclude_list or service.startswith('console-'):
        continue
      process_utils.Spawn(['stop', service], call=True, log=True)


def _UnmountStatefulPartition(root, state_dev):
  logging.debug('Unmount stateful partition.')

  # Expected stateful partition mount point.
  state_dir = os.path.join(root, STATEFUL_PARTITION_PATH.strip(os.path.sep))

  # Touch a mark file so we can check if the stateful partition is wiped
  # successfully.
  file_utils.WriteFile(os.path.join(state_dir, WIPE_MARK_FILE), '')

  # Backup extension cache (crx_cache) if available (will be restored after
  # wiping by clobber-state).
  crx_cache_path = os.path.join(state_dir, CRX_CACHE_PAYLOAD_NAME)
  if os.path.exists(crx_cache_path):
    shutil.copyfile(crx_cache_path, CRX_CACHE_TAR_PATH)

  # Find mount points on stateful partition.
  mount_output = process_utils.SpawnOutput(['mount'], log=True)

  mount_point_list = []
  for line in mount_output.splitlines():
    fields = line.split()
    if fields[0] == state_dev:
      mount_point_list.append(fields[2])
  logging.debug('stateful partitions mounted on: %s', mount_point_list)

  def _ListProcOpening(path_list):
    lsof_cmd = ['lsof', '-t'] + path_list
    return [int(line)
            for line in process_utils.SpawnOutput(lsof_cmd).splitlines()]

  def _ListMinijail():
    # Not sure why, but if we use 'minijail0', then we can't find processes that
    # starts with /sbin/minijail0.
    list_cmd = ['pgrep', 'minijail']
    return [int(line)
            for line in process_utils.SpawnOutput(list_cmd).splitlines()]

  # Find processes that are using stateful partitions.
  proc_list = _ListProcOpening(mount_point_list)

  if os.getpid() in proc_list:
    logging.error('wipe_init itself is using stateful partition')
    logging.error(
        'lsof: %s',
        process_utils.SpawnOutput('lsof -p %d' % os.getpid(), shell=True))
    raise WipeError('wipe_init itself is using stateful partition')

  def _KillOpeningBySignal(sig):
    proc_list = _ListProcOpening(mount_point_list)
    if not proc_list:
      return True  # we are done
    for pid in proc_list:
      try:
        os.kill(pid, sig)
      except Exception:
        logging.exception('killing process %d failed', pid)
    return False  # need to check again

  # Try to kill processes using stateful partition gracefully.
  sync_utils.Retry(10, 0.1, None, _KillOpeningBySignal, signal.SIGTERM)
  sync_utils.Retry(10, 0.1, None, _KillOpeningBySignal, signal.SIGKILL)

  proc_list = _ListProcOpening(mount_point_list)
  assert not proc_list, "processes using stateful partition: %s" % proc_list

  def _Unmount(mount_point, critical):
    logging.info('try to unmount %s', mount_point)
    for unused_i in xrange(10):
      output = process_utils.Spawn(['umount', '-n', '-R', mount_point],
                                   read_stderr=True, log=True).stderr_data
      # some mount points need to be unmounted multiple times.
      if (output.endswith(': not mounted\n') or
          output.endswith(': not found\n')):
        return
      time.sleep(0.5)
    logging.error('failed to unmount %s', mount_point)
    if critical:
      raise WipeError('Unmounting %s is critical. Stop.' % mount_point)

  if os.path.exists(os.path.join(root, 'dev', 'mapper', 'encstateful')):

    # minijail will make encstateful busy, but usually we can't just kill them.
    # Need to list the processes and solve each-by-each.
    proc_list = _ListMinijail()
    assert not proc_list, "processes still using minijail: %s" % proc_list

    # Doing what 'mount-encrypted umount' should do.
    for mount_point in mount_point_list:
      _Unmount(mount_point, False)
    _Unmount(os.path.join(root, 'var'), True)
    process_utils.Spawn(['dmsetup', 'remove', 'encstateful',
                         '--noudevrules', '--noudevsync'], check_call=True)
    process_utils.Spawn(['losetup', '-D'], check_call=True)

  # Try to unmount all known mount points.
  for mount_point in mount_point_list:
    _Unmount(mount_point, True)
  process_utils.Spawn(['sync'], call=True)

  # Check if the stateful partition is unmounted successfully.
  if _IsStateDevMounted(state_dev):
    raise WipeError('Failed to unmount stateful_partition')


def _IsStateDevMounted(state_dev):
  try:
    output = process_utils.CheckOutput(['df', state_dev])
    return output.splitlines()[-1].split()[0] == state_dev
  except Exception:
    return False


def _InformStation(ip, port, token, wipe_init_log=None,
                   wipe_in_tmpfs_log=None, success=True):
  if not ip:
    return
  port = int(port)

  logging.debug('inform station %s:%d', ip, port)

  try:
    sync_utils.WaitFor(
        lambda: process_utils.Spawn(['ping', '-w1', '-c1', ip],
                                    call=True).returncode == 0,
        timeout_secs=180, poll_interval=1)
  except Exception:
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


def _WipeStateDev(release_rootfs, root_disk, wipe_args, state_dev):
  clobber_state_env = os.environ.copy()
  clobber_state_env.update(ROOT_DEV=release_rootfs,
                           ROOT_DISK=root_disk)
  logging.debug('clobber-state: root_dev=%s, root_disk=%s',
                release_rootfs, root_disk)
  process_utils.Spawn(
      ['clobber-state', wipe_args], env=clobber_state_env, check_call=True)

  logging.info('Checking if stateful partition is mounted...')
  # Check if the stateful partition is wiped.
  if not _IsStateDevMounted(state_dev):
    process_utils.Spawn(['mount', state_dev, STATEFUL_PARTITION_PATH],
                        check_call=True, log=True)

  logging.info('Checking wipe mark file %s...', WIPE_MARK_FILE)
  if os.path.exists(
      os.path.join(STATEFUL_PARTITION_PATH, WIPE_MARK_FILE)):
    raise WipeError(WIPE_MARK_FILE + ' still exists')

  # Restore CRX cache.
  logging.info('Checking CRX cache %s...', CRX_CACHE_TAR_PATH)
  if os.path.exists(CRX_CACHE_TAR_PATH):
    process_utils.Spawn(['tar', '-xpvf', CRX_CACHE_TAR_PATH, '-C',
                         STATEFUL_PARTITION_PATH], check_call=True, log=True)

  # Remove developer flag, which is created by clobber-state after wiping.
  try:
    # TODO(hungte) Unlink or create developer flag according to gooftool
    # execution results.
    os.unlink(os.path.join(STATEFUL_PARTITION_PATH, '.developer_mode'))
  except OSError:
    pass

  process_utils.Spawn(['umount', STATEFUL_PARTITION_PATH], call=True)
  # Make sure that everything is synced.
  process_utils.Spawn(['sync'], call=True)
  time.sleep(3)


def EnableReleasePartition(release_rootfs):
  """Enables a release image partition on disk."""
  logging.debug('enable release partition: %s', release_rootfs)
  Util().EnableReleasePartition(release_rootfs)
  logging.debug('Device will boot from %s after reboot.', release_rootfs)


def _InformShopfloor(shopfloor_url):
  if shopfloor_url:
    logging.debug('inform shopfloor %s', shopfloor_url)
    proc = process_utils.Spawn(
        [
            os.path.join(CUTOFF_SCRIPT_DIR, 'inform_shopfloor.sh'),
            shopfloor_url, 'factory_wipe'
        ],
        read_stdout=True,
        read_stderr=True)
    logging.debug('stdout: %s', proc.stdout_data)
    logging.debug('stderr: %s', proc.stderr_data)
    if proc.returncode != 0:
      raise RuntimeError('InformShopfloor failed.')


def _Cutoff():
  logging.debug('cutoff')
  cutoff_script = os.path.join(CUTOFF_SCRIPT_DIR, 'cutoff.sh')
  process_utils.Spawn([cutoff_script], check_call=True)


def WipeInit(wipe_args, shopfloor_url, state_dev, release_rootfs,
             root_disk, old_root, station_ip, station_port, finish_token):
  Daemonize()
  logfile = '/tmp/wipe_init.log'
  wipe_in_tmpfs_log = os.path.join(old_root, 'tmp', WIPE_IN_TMPFS_LOG)
  ResetLog(logfile)

  logging.debug('wipe_args: %s', wipe_args)
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

    try:
      _WipeStateDev(release_rootfs, root_disk, wipe_args, state_dev)
    except Exception:
      process_utils.Spawn(
          [os.path.join(CUTOFF_SCRIPT_DIR, 'display_wipe_message.sh'),
           'wipe_failed'], call=True)
      raise

    EnableReleasePartition(release_rootfs)

    _InformShopfloor(shopfloor_url)

    _InformStation(station_ip, station_port, finish_token,
                   wipe_init_log=logfile,
                   wipe_in_tmpfs_log=wipe_in_tmpfs_log,
                   success=True)

    _Cutoff()

    # should not reach here
    logging.info('Going to sleep forever!')
    time.sleep(1e8)
  except Exception:
    logging.exception('wipe_init failed')
    _OnError(station_ip, station_port, finish_token, state_dev,
             wipe_in_tmpfs_log=wipe_in_tmpfs_log, wipe_init_log=logfile)
    raise
