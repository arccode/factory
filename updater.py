# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import os
import shutil
import subprocess
from urlparse import urlparse
import uuid

from autotest_lib.client.cros import factory
from autotest_lib.client.cros.factory import shopfloor


class UpdaterException(Exception):
    pass


def GetCurrentMD5SUM():
    '''Returns MD5SUM of the current autotest directory.

    Returns None if there has been no update (i.e., unable to read
    the MD5SUM file).
    '''
    md5sum_file = os.path.join(factory.CLIENT_PATH, 'MD5SUM')
    if os.path.exists(md5sum_file):
        return open(md5sum_file, 'r').read().strip()
    else:
        return None


def CheckCriticalFiles(autotest_new_path):
    '''Raises an exception if certain critical files are missing.'''
    critical_files = [
        os.path.join(autotest_new_path, f)
        for f in ['MD5SUM',
                  'cros/factory/goofy.py',
                  'site_tests/factory_Finalize/factory_Finalize.py']]
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
    autotest_path = factory.CLIENT_PATH

    # Determine whether an update is necessary.
    md5sum_file = os.path.join(autotest_path, 'MD5SUM')
    if os.path.exists(md5sum_file):
        current_md5sum = open(md5sum_file).read().strip()
    else:
        current_md5sum = None

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

    # An update is necessary.  Construct the rsync command.
    update_port = shopfloor_client.GetUpdatePort()
    autotest_new_path = '%s.new' % autotest_path
    RunRsync(
        'rsync',
        '-a', '--delete', '--stats',
        # Use copies of identical files from the old autotest
        # as much as possible to save network bandwidth.
        '--copy-dest=%s' % autotest_path,
        'rsync://%s:%d/autotest/%s/autotest/' % (
            urlparse(url).hostname,
            update_port,
            new_md5sum),
        '%s/' % autotest_new_path)

    CheckCriticalFiles(autotest_new_path)

    new_md5sum_path = os.path.join(autotest_new_path, 'MD5SUM')
    new_md5sum_from_fs = open(new_md5sum_path).read().strip()
    if new_md5sum != new_md5sum_from_fs:
        raise UpdaterException(
            'Unexpected MD5SUM in %s: expected %s but found %s' %
            new_md5sum_path, new_md5sum, new_md5sum_from_fs)

    if factory.in_chroot():
        raise UpdaterException('Aborting update: In chroot')

    # Copy over autotest results.
    autotest_results = os.path.join(autotest_path, 'results')
    if os.path.exists(autotest_results):
        RunRsync('rsync', '-a',
                 autotest_results,
                 autotest_new_path)

    # Alright, here we go!  This is the point of no return.
    if pre_update_hook:
        pre_update_hook()
    autotest_old_path = '%s.old.%s' % (autotest_path, uuid.uuid4())
    # If one of these fails, we're screwed.
    shutil.move(autotest_path, autotest_old_path)
    shutil.move(autotest_new_path, autotest_path)
    # Delete the autotest.old tree
    shutil.rmtree(autotest_old_path, ignore_errors=True)
    factory.console.info('Update successful')
    return True
