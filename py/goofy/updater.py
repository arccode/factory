# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import os
import shutil
import subprocess
from urlparse import urlparse
import uuid

from cros.factory.test import factory
from cros.factory.test import shopfloor


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
  factory.console.info('Running `%s`',
             ' '.join(rsync_command))
  # Run rsync.
  rsync = subprocess.Popen(rsync_command,
               stdout=subprocess.PIPE,
               stderr=subprocess.STDOUT)
  stdout, _ = rsync.communicate()
  if stdout:
    factory.console.info('rsync output: %s', stdout)
  if rsync.returncode:
    raise UpdaterException('rsync returned status %d; aborting' %
                 rsync.returncode)
  factory.console.info('rsync succeeded')


def TryUpdate(pre_update_hook=None):
  '''Attempts to update the autotest directory on the device.

  Atomically replaces the autotest directory with new contents.
  This routine will always fail in the chroot (to avoid destroying
  the user's working directory).

  Args:
    pre_update_hook: A routine to be invoked before the
      autotest directory is swapped out.

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

  shopfloor_client = shopfloor.get_instance(detect=True)
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
  RunRsync(
    'rsync',
    '-a', '--delete', '--stats',
    # Use copies of identical files from the old autotest
    # as much as possible to save network bandwidth.
    '--copy-dest=%s' % parent_dir,
    'rsync://%s:%d/factory/%s/' % (
      urlparse(url).hostname,
      update_port,
      new_md5sum),
    '%s/' % new_path)

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
