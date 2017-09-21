# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import os
import shutil
import uuid

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test import factory
from cros.factory.test import server_proxy
from cros.factory.test.utils import update_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils


class UpdaterException(Exception):
  pass


def TryUpdate(pre_update_hook=None, timeout=15):
  """Attempts to update the factory directory on the device.

  Atomically replaces the factory directory with new contents.
  This routine will always fail in the chroot (to avoid destroying
  the user's working directory).

  Args:
    pre_update_hook: A routine to be invoked before the
      factory directory is swapped out.
    timeout: Timeout in seconds for RPC calls on the proxy which provides
      remote services on factory server.

  Returns:
    True if an update was performed and the machine should be
    rebooted.

  Raises:
    UpdaterException
  """
  current_version = update_utils.GetToolkitVersion()
  factory.console.info(
      'Checking for updates at <%s>... (current TOOLKIT_VERSION is %s)',
      server_proxy.GetServerURL(), current_version)

  proxy = server_proxy.GetServerProxy(timeout=timeout)
  updater = update_utils.Updater(update_utils.COMPONENTS.toolkit, proxy=proxy)
  if not updater.IsUpdateAvailable(current_version):
    factory.console.info('Factory software is up to date: %s', current_version)
    return False

  # /usr/local on the device (parent to factory)
  parent_dir = os.path.dirname(paths.FACTORY_DIR)

  src_base_path = os.path.join(parent_dir, 'updater.new')
  shutil.rmtree(src_base_path, ignore_errors=True)

  def _ExtractToolkit(target_dir, component, destination, url):
    logging.info('Extracting %s#%s to %s...', url, component, target_dir)
    process_utils.Spawn(
        ['sh', os.path.join(destination, component), '--noexec',
         '--target', target_dir], log=True, check_call=True)

  update_version = updater.GetUpdateVersion()
  updater.PerformUpdate(
      callback=lambda *args, **kargs: _ExtractToolkit(
          src_base_path, *args, **kargs))

  src_path = os.path.join(src_base_path, 'usr', 'local', 'factory')
  new_version_path = os.path.join(src_path, 'TOOLKIT_VERSION')
  new_version_from_fs = file_utils.ReadFile(new_version_path).rstrip()
  if update_version != new_version_from_fs:
    raise UpdaterException(
        'Unexpected TOOLKIT_VERSION in %s: expected %s but found %s' %
        (new_version_path, update_version, new_version_from_fs))

  # Raises an exception if certain critical files are missing.
  critical_files = [
      os.path.join(src_path, f)
      for f in ['py_pkg/cros/factory/goofy/goofy.py',
                'py/test/pytests/finalize/finalize.py']]
  missing_files = [f for f in critical_files if not os.path.exists(f)]
  if missing_files:
    raise UpdaterException(
        'Aborting update: Missing critical files %r' % missing_files)

  # Some files should be kept.
  # TODO(crbug.com/756275): We should move ALL runtime generated files outside
  # of the toolkit folder.
  for file_to_keep in ['py/test/test_lists/ACTIVE', 'hwid']:
    old_path = os.path.join(paths.FACTORY_DIR, file_to_keep)
    new_path = os.path.join(src_path, file_to_keep)
    if os.path.exists(old_path) and not os.path.exists(new_path):
      if os.path.isdir(old_path):
        shutil.copytree(old_path, new_path, symlinks=True)
      else:
        shutil.copy2(old_path, new_path)

  if sys_utils.InChroot():
    raise UpdaterException('Aborting update: In chroot')

  # Alright, here we go!  This is the point of no return.
  if pre_update_hook:
    pre_update_hook()

  old_path = os.path.join(parent_dir, 'updater.old.%s' % uuid.uuid4())
  # If one of these fails, we're screwed.
  shutil.move(paths.FACTORY_DIR, old_path)
  shutil.move(src_path, parent_dir)
  # Delete the old and new trees
  shutil.rmtree(old_path, ignore_errors=True)
  shutil.rmtree(src_path, ignore_errors=True)
  factory.console.info('Update successful')
  return True


def CheckForUpdate(timeout, quiet=False):
  """Checks for an update synchronously.

  Args:
    timeout: If not None, the timeout in seconds. This timeout is for RPC
             calls on the proxy, not for get_instance() itself.
    quiet: Suppresses error messages when factory server can not be reached.

  Returns:
    A tuple (toolkit_version, needs_update):
      toolkit_version: the TOOLKIT_VERSION returned by factory server, or
        None if it is not available or test environment is not installed on the
        factory server yet.
      needs_update: is True if an update is necessary (i.e., toolkit_version is
        not None, and toolkit_version isn't the same as the TOOLKIT_VERSION in
        the current factory directory).

  Raises:
    An exception if unable to contact the factory server.
  """
  proxy = server_proxy.GetServerProxy(timeout=timeout, quiet=quiet)
  updater = update_utils.Updater(update_utils.COMPONENTS.toolkit, proxy=proxy)
  remote_version = updater.GetUpdateVersion()
  current_version = update_utils.GetToolkitVersion()

  return (remote_version, updater.IsUpdateAvailable(current_version))


def CheckForUpdateAsync(callback, timeout, quiet=False):
  """Checks for an update asynchronously.

  Launches a separate thread, checks for an update, and invokes callback (in
  at most timeout seconds) in that separate thread with the following arguments:

    callback(reached_server, toolkit_version, needs_update)

  reached_server is True if the updater was actually able to communicate
  with the factory server, or False on timeout.

  toolkit_version and needs_update are as in the return value for
  CheckForUpdate.

  Args:
    callback: Callback function to run in the separate thread as explained
              above.
    timeout: If not None, the timeout in seconds. This timeout is for RPC
             calls on the proxy, not for get_instance() itself.
    quiet: Suppresses error messages when factory server can not be reached.
  """
  def Run():
    try:
      callback(True, *CheckForUpdate(timeout=timeout, quiet=quiet))
    except Exception:
      # Just an info, not a trace, since this is pretty common (and not
      # necessarily an error) and we don't want logs to get out of control.
      if not quiet:
        logging.exception(
            'Unable to contact factory server to check for updates.')
      callback(False, None, False)
  process_utils.StartDaemonThread(target=Run, name='UpdateThread')
