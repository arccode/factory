#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import cPickle as pickle
import hashlib
import logging
import os
import subprocess
import threading
import time

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import connection_manager
from cros.factory.test import factory, state, utils


class Environment(object):
  '''
  Abstract base class for external test operations, e.g., run an autotest,
  shutdown, or reboot.

  The Environment is assumed not to be thread-safe: callers must grab the lock
  before calling any methods.  This is primarily necessary because we mock out
  this Environment with mox, and unfortunately mox is not thread-safe.
  TODO(jsalz): Try to write a thread-safe wrapper for mox.
  '''
  lock = threading.Lock()

  def shutdown(self, operation):
    '''
    Shuts the machine down (from a ShutdownStep).

    Args:
      operation: 'reboot' or 'halt'.

    Returns:
      True if Goofy should gracefully exit, or False if Goofy
        should just consider the shutdown to have suceeded (e.g.,
        in the chroot).
    '''
    raise NotImplementedError()

  def launch_chrome(self):
    '''
    Launches Chrome.

    Returns:
      The Chrome subprocess (or None if none).
    '''
    raise NotImplementedError()

  def spawn_autotest(self, name, args, env_additions, result_file):
    '''
    Spawns a process to run an autotest.

    Args:
      name: Name of the autotest to spawn.
      args: Command-line arguments.
      env_additions: Additions to the environment.
      result_file: Expected location of the result file.
    '''
    raise NotImplementedError()

  def create_connection_manager(self, wlans, scan_wifi_period_secs):
    '''
    Creates a ConnectionManager.
    '''
    raise NotImplementedError()


class DUTEnvironment(Environment):
  '''
  A real environment on a device under test.
  '''
  BROWSER_TYPE = 'system'
  EXTENSION_PATH = os.path.join(factory.FACTORY_PATH, 'py', 'goofy',
                                'factory_test_extension')
  def __init__(self):
    self.browser = None
    self.extension = None

  def shutdown(self, operation):
    assert operation in ['reboot', 'halt']
    logging.info('Shutting down: %s', operation)
    subprocess.check_call('sync')
    subprocess.check_call(operation)
    time.sleep(30)
    assert False, 'Never reached (should %s)' % operation

  def spawn_autotest(self, name, args, env_additions, result_file):
    return self.goofy.prespawner.spawn(args, env_additions)

  def launch_chrome(self):
    # Import these modules here because they are not available in chroot.
    # pylint: disable=F0401
    from telemetry.core import browser_finder
    from telemetry.core import browser_options
    from telemetry.core import extension_to_load
    from telemetry.core import util as telemetry_util

    # Telemetry flakiness: Allow one retry when starting up Chrome.
    # TODO(jcliang): Remove this when we're sure that telemetry is stable
    # enough.
    tries_left = 2
    while tries_left:
      try:
        finder_options = browser_options.BrowserFinderOptions()
        finder_options.browser_type = self.BROWSER_TYPE
        self.extension = extension_to_load.ExtensionToLoad(
            self.EXTENSION_PATH, self.BROWSER_TYPE, is_component=True)
        finder_options.extensions_to_load.append(self.extension)
        finder_options.AppendExtraBrowserArgs([
            '--kiosk',
            '--kiosk-mode-screensaver-path=/dev/null',
            '--disable-translate',
            '--ash-hide-notifications-for-factory',
            ('--default-device-scale-factor=%d' %
             self.goofy.options.ui_scale_factor)])
        finder_options.CreateParser().parse_args(args=[])
        self.browser = browser_finder.FindBrowser(finder_options).Create()
        self.browser.Start()
        break
      except telemetry_util.TimeoutException:
        tries_left -= 1
        if not tries_left:
          raise

    if len(self.browser.tabs):
      tab = self.browser.tabs[0]
    else:
      tab = self.browser.tabs.New()
    tab.Navigate('http://127.0.0.1:%d/' % state.DEFAULT_FACTORY_STATE_PORT)
    tab.Activate()
    # Press the maximize key to maximize the window.
    utils.SendKey('F4')

  def create_connection_manager(self, wlans, scan_wifi_period_secs):
    return connection_manager.ConnectionManager(wlans,
                                                scan_wifi_period_secs)


class FakeChrootEnvironment(Environment):
  '''
  A chroot environment that doesn't actually shutdown or run autotests.
  '''
  def shutdown(self, operation):
    assert operation in ['reboot', 'halt']
    logging.warn('In chroot: skipping %s', operation)
    return False

  def spawn_autotest(self, name, args, env_additions, result_file):
    logging.warn('In chroot: skipping autotest %s', name)
    # Mark it as passed with 75% probability, or failed with 25%
    # probability (depending on a hash of the autotest name).
    pseudo_random = ord(hashlib.sha1(name).digest()[0]) / 256.0
    passed = pseudo_random > .25

    with open(result_file, 'w') as out:
      pickle.dump((passed, '' if passed else 'Simulated failure'), out)
    # Start a process that will return with a true exit status in
    # 2 seconds (just like a happy autotest).
    return subprocess.Popen(['sleep', '2'])

  def launch_chrome(self):
    logging.warn('In chroot; not launching Chrome. '
           'Please open http://localhost:%d/ in Chrome.',
           state.DEFAULT_FACTORY_STATE_PORT)

  def create_connection_manager(self, wlans, scan_wifi_period_secs):
    return connection_manager.DummyConnectionManager()
