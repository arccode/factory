#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Enviroment objects that handles external test operations."""

import cPickle as pickle
import hashlib
import logging
import multiprocessing
import os
import subprocess
import threading
import time

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import connection_manager
from cros.factory.test import factory, state, utils


class Environment(object):
  """Abstract base class for external test operations, e.g., run an autotest,
  shutdown, or reboot.

  The Environment is assumed not to be thread-safe: callers must grab the lock
  before calling any methods.  This is primarily necessary because we mock out
  this Environment with mox, and unfortunately mox is not thread-safe.
  TODO(jsalz): Try to write a thread-safe wrapper for mox.
  """
  lock = threading.Lock()

  def shutdown(self, operation):
    """Shuts the machine down (from a ShutdownStep).

    Args:
      operation: 'reboot' or 'halt'.

    Returns:
      True if Goofy should gracefully exit, or False if Goofy
        should just consider the shutdown to have suceeded (e.g.,
        in the chroot).
    """
    raise NotImplementedError()

  def launch_chrome(self):
    """Launches Chrome.

    Returns:
      The Chrome subprocess (or None if none).
    """
    raise NotImplementedError()

  def spawn_autotest(self, name, args, env_additions, result_file):
    """Spawns a process to run an autotest.

    Args:
      name: Name of the autotest to spawn.
      args: Command-line arguments.
      env_additions: Additions to the environment.
      result_file: Expected location of the result file.
    """
    raise NotImplementedError()

  def create_connection_manager(self, wlans, scan_wifi_period_secs):
    """Creates a ConnectionManager."""
    raise NotImplementedError()


class DUTEnvironment(Environment):
  """A real environment on a device under test."""
  BROWSER_TYPE_LOGIN = 'system'
  BROWSER_TYPE_GUEST = 'system-guest'
  EXTENSION_PATH = os.path.join(factory.FACTORY_PATH, 'py', 'goofy',
                                'factory_test_extension')
  GUEST_MODE_TAG_FILE = os.path.join(state.DEFAULT_FACTORY_STATE_FILE_PATH,
                                     'enable_guest_mode')

  def __init__(self):
    super(DUTEnvironment, self).__init__()
    self.browser = None
    self.extension = None
    self.start_process = True
    if os.path.exists(self.GUEST_MODE_TAG_FILE):
      # Only enable guest mode for this boot.
      os.unlink(self.GUEST_MODE_TAG_FILE)
      self.browser_type = self.BROWSER_TYPE_GUEST
    else:
      self.browser_type = self.BROWSER_TYPE_LOGIN

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
    # Telemetry flakiness: Allow retries when starting up Chrome.
    # TODO(jcliang): Remove this when we're sure that telemetry is stable
    # enough.
    for try_num in xrange(
        1, self.goofy.test_list.options.chrome_startup_tries + 1):
      try:
        if try_num > 1:
          logging.info('Retry loading UI through telemetry (try_num = %d)',
                       try_num)
        # Telemetry UI login may fail with an exception, or just stuck at
        # login screen with no error. We provide two retry logic here:
        # thread-based or process-based.
        if self.start_process:
          # Retry telemetry login in another process. This is more robust as
          # telemetry is isolated in another process and does not affects goofy
          # process. The drawback is that we will not be able to access
          # telemetry-based features such as screen capture or remote debugging.
          process = multiprocessing.Process(target=self._start_telemetry)
          process.start()
        else:
          # Retry telemetry login in another thread so it will not block current
          # thread in the latter case. A new call to _start_telemetry should
          # cause all previous calls to the same method to fail with exception
          # since ui process will be restarted.
          utils.StartDaemonThread(target=self._start_telemetry)
        logging.info('Waiting for UI to load (try_num = %d)', try_num)
        utils.WaitFor(self.goofy.web_socket_manager.has_sockets, 30)
        logging.info('UI loaded')
        break
      except utils.TimeoutError:
        if self.start_process:
          utils.kill_process_tree(process, 'telemetry')
        logging.exception('Failed to load UI (try_num = %d)', try_num)

    if not self.goofy.web_socket_manager.has_sockets():
      logging.error('UI did not load after %d tries; giving up',
                    self.goofy.test_list.options.chrome_startup_tries)

  def _start_telemetry(self):
    """Starts UI through telemetry."""
    # Telemetry sets up several signal handlers, which requires running the
    # telemetry module in the main thread or an exception will be raised.
    # Our retry logic here starts telemetry in a separate daemon thread so we
    # fake signal.signal when importing telemetry modules.
    import signal
    if not self.start_process:
      original_signal = signal.signal
      signal.signal = lambda sig, action: True
    # Import these modules here because they are not available in chroot.
    # pylint: disable=F0401
    from telemetry.core import browser_finder
    from telemetry.core import browser_options
    from telemetry.core import extension_to_load
    if not self.start_process:
      signal.signal = original_signal

    try:
      finder_options = browser_options.BrowserFinderOptions()
      finder_options.browser_type = self.browser_type
      if self.browser_type == self.BROWSER_TYPE_LOGIN:
        # Extension is not supported in guest mode.
        self.extension = extension_to_load.ExtensionToLoad(
            self.EXTENSION_PATH, self.browser_type, is_component=True)
        finder_options.extensions_to_load.append(self.extension)
      finder_options.AppendExtraBrowserArgs([
          '--ash-hide-notifications-for-factory',
          ('--default-device-scale-factor=%d' %
           self.goofy.options.ui_scale_factor),
          '--disable-translate',
          '--enable-gpu-benchmarking',
          '--kiosk',
          '--kiosk-mode-screensaver-path=/dev/null'])
      # Telemetry alters logging verbosity level.  Use '-v' to set
      # logging level to INFO and '-vv' to set to DEBUG.
      finder_options.CreateParser().parse_args(args=[
          '-vv' if self.goofy.options.verbose else '-v'])
      self.browser = browser_finder.FindBrowser(finder_options).Create()
      self.browser.Start()

      if len(self.browser.tabs):
        tab = self.browser.tabs[0]
      else:
        tab = self.browser.tabs.New()
      tab.Navigate('http://127.0.0.1:%d/' % state.DEFAULT_FACTORY_STATE_PORT)
      tab.Activate()
      # Press the maximize key to maximize the window.
      utils.SendKey('F4')
      # Disable X-axis two-finger scrolling on touchpad.
      utils.SetTouchpadTwoFingerScrollingX(False)
      if self.start_process:
        # Just loop forever if this is in a separate process.
        while True:
          time.sleep(10)
    except Exception:
      # Do not fail on exception here as we have a retry loop in
      # launch_chrome().
      logging.exception('Telemetry login failed')

  def create_connection_manager(self, wlans, scan_wifi_period_secs):
    return connection_manager.ConnectionManager(wlans,
                                                scan_wifi_period_secs)


class FakeChrootEnvironment(Environment):
  """A chroot environment that doesn't actually shutdown or run autotests."""
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
