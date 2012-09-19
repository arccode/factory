# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from urlparse import urlparse
import uuid


from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.utils.process_utils import Spawn


class UpdaterException(Exception):
  pass


def CheckCriticalFiles(new_path):
  '''Raises an exception if certain critical files are missing.'''
  critical_files = [
    os.path.join(new_path, f)
    for f in ['factory/MD5SUM',
          'factory/py_pkg/cros/factory/goofy/goofy.py',
          'autotest/site_tests/factory_Finalize/factory_Finalize.py']]
  missing_files = [f for f in critical_files
           if not os.path.exists(f)]
  if missing_files:
    raise UpdaterException(
      'Aborting update: Missing critical files %r' % missing_files)


def RunRsync(*rsync_command):
  '''Runs rsync with the given command.'''
  rsync = Spawn(rsync_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                log=factory.console)
  stdout, _ = rsync.communicate()
  if stdout:
    factory.console.info('rsync output: %s', stdout)
  if rsync.returncode:
    raise UpdaterException('rsync returned status %d; aborting' %
                 rsync.returncode)
  factory.console.info('rsync succeeded')


def TryUpdate(pre_update_hook=None, timeout=15):
  '''Attempts to update the autotest directory on the device.

  Atomically replaces the autotest directory with new contents.
  This routine will always fail in the chroot (to avoid destroying
  the user's working directory).

  Args:
    pre_update_hook: A routine to be invoked before the
      autotest directory is swapped out.
    timeout: This timeout serves at two places.
      1. Timeout in seconds for RPC calls on the proxy which provides
        remote services on shopfloor server.
      2. I/O timeout of rsync in seconds.

  Returns:
    True if an update was performed and the machine should be
    rebooted.
  '''
  # On a real device, this will resolve to 'autotest' (since 'client'
  # is a symlink to that).  In the chroot, this will resolve to the
  # 'client' directory.
  # Determine whether an update is necessary.
  current_md5sum = factory.get_current_md5sum()

  url = shopfloor.get_server_url() or shopfloor.detect_default_server_url()
  factory.console.info(
    'Checking for updates at <%s>... (current MD5SUM is %s)',
    url, current_md5sum)

  shopfloor_client = shopfloor.get_instance(detect=True, timeout=timeout)
  new_md5sum = shopfloor_client.GetTestMd5sum()
  factory.console.info('MD5SUM from server is %s', new_md5sum)
  if current_md5sum == new_md5sum or new_md5sum is None:
    factory.console.info('Factory software is up to date')
    return False

  # /usr/local on the device (parent to both factory and autotest)
  parent_dir = os.path.dirname(factory.FACTORY_PATH)

  # An update is necessary.  Construct the rsync command.
  update_port = shopfloor_client.GetUpdatePort()
  new_path = os.path.join(parent_dir, 'updater.new')
  # rsync --link-dest considers any existing files to be definitive,
  # so wipe anything that's already there.
  if os.path.exists(new_path):
    shutil.rmtree(new_path)

  RunRsync(
    'rsync',
    '-a', '--delete', '--stats',
    '--timeout=%s' % timeout,
    # Use hard links of identical files from the old directories to
    # save network bandwidth and temporary space on disk.
    '--link-dest=%s' % parent_dir,
    'rsync://%s:%d/factory/%s/' % (
      urlparse(url).hostname,
      update_port,
      new_md5sum),
    '%s/' % new_path)

  hwid_path = os.path.join(factory.FACTORY_PATH, 'hwid')
  new_hwid_path = os.path.join(new_path, 'factory', 'hwid')
  if os.path.exists(hwid_path) and not os.path.exists(new_hwid_path):
    RunRsync(
      'rsync', '-a',
      hwid_path, '%s/factory' % new_path)

  CheckCriticalFiles(new_path)

  new_md5sum_path = os.path.join(new_path, 'factory', 'MD5SUM')
  new_md5sum_from_fs = open(new_md5sum_path).read().strip()
  if new_md5sum != new_md5sum_from_fs:
    raise UpdaterException(
      'Unexpected MD5SUM in %s: expected %s but found %s' %
      new_md5sum_path, new_md5sum, new_md5sum_from_fs)

  if factory.in_chroot():
    raise UpdaterException('Aborting update: In chroot')

  # Alright, here we go!  This is the point of no return.
  if pre_update_hook:
    pre_update_hook()

  old_path = os.path.join(parent_dir, 'updater.old.%s' % uuid.uuid4())
  # If one of these fails, we're screwed.
  for d in ['factory', 'autotest']:
    shutil.move(os.path.join(parent_dir, d), old_path)
    shutil.move(os.path.join(new_path, d), parent_dir)
  # Delete the old and new trees
  shutil.rmtree(old_path, ignore_errors=True)
  shutil.rmtree(new_path, ignore_errors=True)
  factory.console.info('Update successful')
  return True


def CheckForUpdate(timeout):
  '''Checks for an update synchronously.

  Raises:
    An exception if unable to contact the shopfloor server.

  Returns:
    A tuple (md5sum, needs_update):
      md5sum: the MD5SUM returned by shopfloor server, or None if it is not
        available or test environment is not installed on the shopfloor server
        yet.
      needs_update: is True if an update is necessary (i.e., md5sum is not None,
        and md5sum isn't the same as the MD5SUM in the current autotest
        directory).
  '''
  shopfloor_client = shopfloor.get_instance(detect=True, timeout=timeout)
  new_md5sum = shopfloor_client.GetTestMd5sum()
  current_md5sum = factory.get_current_md5sum()
  return (new_md5sum,
          new_md5sum and new_md5sum != current_md5sum)


def CheckForUpdateAsync(callback, timeout):
  '''Checks for an update asynchronously.

  Launches a separate thread, checks for an update, and invokes callback (in
  at most timeout seconds) in that separate thread with the following arguments:

    callback(reached_shopfloor, md5sum, needs_update)

  reached_shopfloor is True if the updater was actually able to communicate
  with the shopfloor server, or False on timeout.

  md5sum and needs_update are as in the return value for CheckForUpdate.
  '''
  def Run():
    try:
      callback(True, *CheckForUpdate(timeout))
    except:
      # Just an info, not a trace, since this is pretty common (and not
      # necessarily an error) and we don't want logs to get out of control.
      logging.info(
        'Unable to contact shopfloor server to check for updates: %s',
        '\n'.join(traceback.format_exception_only(*sys.exc_info()[:2])).strip())
      callback(False, None, False)

  update_thread = threading.Thread(target=Run, name='UpdateThread')
  update_thread.daemon = True
  update_thread.start()
  return
