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
from cros.factory.goofy_split.service_manager import GetServiceStatus
from cros.factory.goofy_split.service_manager import SetServiceStatus
from cros.factory.goofy_split.service_manager import Status
from cros.factory.goofy_split import connection_manager
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
      operation: 'reboot', 'full_reboot', or 'halt'.

    Returns:
      True if Goofy should gracefully exit, or False if Goofy
        should just consider the shutdown to have suceeded (e.g.,
        in the chroot).
    """
    raise NotImplementedError()

  def controller_ready_for_ui(self):
    """Hooks called when Goofy controller is ready for UI connection."""
    pass

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

  def terminate(self):
    """Terminates and cleans up environment."""
    pass


class DUTEnvironment(Environment):
  """A real environment on a device under test."""

  def __init__(self):
    super(DUTEnvironment, self).__init__()
    self.goofy = None  # Must be assigned later by goofy.
    self.has_sockets = None # Must be assigned later by goofy.

  def shutdown(self, operation):
    def prepare_shutdown():
      """Prepares for a clean shutdown."""
      self.goofy.connection_manager.DisableNetworking()
      respawn_services = ['syslog',
                          'tcsd',
                          'shill',
                          'warn-collector']
      for service in respawn_services:
        if GetServiceStatus(service) == Status.START:
          SetServiceStatus(service, Status.STOP)

    assert operation in ['reboot', 'full_reboot', 'halt']
    logging.info('Shutting down: %s', operation)
    subprocess.check_call('sync')

    prepare_shutdown()

    if operation == 'full_reboot':
      subprocess.check_call(['ectool', 'reboot_ec', 'cold', 'at-shutdown'])
      subprocess.check_call(['shutdown', '-h', 'now'])
    else:
      commands = dict(reboot=['shutdown', '-r', 'now'],
                      halt=['shutdown', '-h', 'now'])
      subprocess.check_call(commands[operation])
    # TODO(hungte) Current implementation will raise SIGTERM so goofy can't
    # really gracefully shutdown. We should do "on exit" instead.
    time.sleep(30)
    assert False, 'Never reached (should %s)' % operation

  def spawn_autotest(self, name, args, env_additions, result_file):
    return self.goofy.prespawner.spawn(args, env_additions)

  def launch_chrome(self):
    utils.WaitFor(self.has_sockets, 30)
    subprocess.check_call(['initctl', 'emit', 'login-prompt-visible'])
    # Disable X-axis two-finger scrolling on touchpad.
    utils.SetTouchpadTwoFingerScrollingX(False)
    # If we have a touchpad, then disable touchscreen so that operators won't
    # accidentally roll back to previous webpage. If we have no touchpad, we
    # assume that the touch UI is required.
    if utils.GetTouchpadDeviceIds():
      for device_id in utils.GetTouchscreenDeviceIds():
        utils.SetXinputDeviceEnabled(device_id, False)

  def create_connection_manager(self, wlans, scan_wifi_period_secs):
    return connection_manager.ConnectionManager(wlans,
                                                scan_wifi_period_secs)


class DUTTelemetryEnvironment(DUTEnvironment):
  """A real environment on a device under test, using Telemetry."""
  BROWSER_TYPE_LOGIN = 'system'
  BROWSER_TYPE_GUEST = 'system-guest'
  CLOSE_GOOFY_TAB = 'CloseGoofyTab'
  EXTENSION_PATH = os.path.join(factory.FACTORY_PATH, 'py', 'goofy',
                                'factory_test_extension')
  GUEST_MODE_TAG_FILE = os.path.join(state.DEFAULT_FACTORY_STATE_FILE_PATH,
                                     'enable_guest_mode')

  def __init__(self):
    super(DUTTelemetryEnvironment, self).__init__()
    self.browser = None
    self.extension = None
    self.telemetry_proc = None
    self.telemetry_proc_pipe = None
    if os.path.exists(self.GUEST_MODE_TAG_FILE):
      # Only enable guest mode for this boot.
      os.unlink(self.GUEST_MODE_TAG_FILE)
      self.browser_type = self.BROWSER_TYPE_GUEST
    else:
      self.browser_type = self.BROWSER_TYPE_LOGIN

  def shutdown(self, operation):
    if self.telemetry_proc_pipe:
      self.telemetry_proc_pipe.send(None)
      self.telemetry_proc.join()
    super(DUTTelemetryEnvironment, self).shutdown(operation)

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
        # login screen with no error.
        #
        # Retry telemetry login in another process. This is more robust as
        # telemetry is isolated in another process and does not affects goofy
        # process. The drawback is that we will not be able to access
        # telemetry-based features such as screen capture or remote debugging.
        parent_conn, child_conn = multiprocessing.Pipe()
        self.telemetry_proc = multiprocessing.Process(
            target=self._start_telemetry, args=(child_conn,))
        self.telemetry_proc.start()
        logging.info('Waiting for UI to load (try_num = %d)', try_num)
        utils.WaitFor(self.goofy.web_socket_manager.has_sockets, 30)
        logging.info('UI loaded')
        self.telemetry_proc_pipe = parent_conn
        break
      except utils.TimeoutError:
        utils.kill_process_tree(self.telemetry_proc, 'telemetry')
        logging.exception('Failed to load UI (try_num = %d)', try_num)

    if not self.goofy.web_socket_manager.has_sockets():
      logging.error('UI did not load after %d tries; giving up',
                    self.goofy.test_list.options.chrome_startup_tries)

  def _start_telemetry(self, pipe=None):
    """Starts UI through telemetry."""
    # Import these modules here because they are not available in chroot.
    # pylint: disable=F0401
    from telemetry.core import browser_finder
    from telemetry.core import browser_options
    from telemetry.core import extension_to_load

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
      # Disable touchscreen so that operators won't accidentally roll back to
      # previous webpage.
      for device_id in utils.GetTouchscreenDeviceIds():
        utils.SetXinputDeviceEnabled(device_id, False)

      # Serve events forever.
      while True:
        event = pipe.recv()
        if event is None:
          logging.info('[UI process] received None, shutting down UI process')
          break
        logging.info('[UI Process] received event %s', event)
        pipe.send(self._ui_rpc_event_handler(event))

    except Exception:
      # Do not fail on exception here as we have a retry loop in
      # launch_chrome().
      logging.exception('Telemetry login failed')

  def _ui_rpc_event_handler(self, event):
    """Event handler for UI RPC.

    Args:
      event: The UI RPC event to handle.

    Returns:
      The return value of the corresponding function call to Telemetry, or a
      Exception object if anything goes wrong.
    """
    if not self.browser or not self.extension:
      return Exception('Browser instance is not initialized')

    def _GetGoofyTab():
      tabs = self.browser.tabs
      for i in xrange(0, len(tabs)):
        if tabs[i].url == ('http://127.0.0.1:%d/' %
                           state.DEFAULT_FACTORY_STATE_PORT):
          return tabs[i]

    try:
      if event['type'] == self.CLOSE_GOOFY_TAB:
        _GetGoofyTab().Close()

    except Exception as e:
      return e

  def terminate(self):
    if self.goofy.env.telemetry_proc_pipe is None:
      logging.error('UI is not ready.')
      return
    data = {'type': self.CLOSE_GOOFY_TAB, 'args': None}
    self.telemetry_proc_pipe.send(data)
    self.telemetry_proc_pipe.recv()
    # We don't relly care about received result since it's already in
    # termination.


class FakeChrootEnvironment(Environment):
  """A chroot environment that doesn't actually shutdown or run autotests."""
  def shutdown(self, operation):
    assert operation in ['reboot', 'full_reboot', 'halt']
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
                 'Please open UI presenter app in Chrome.')

  def create_connection_manager(self, wlans, scan_wifi_period_secs):
    return connection_manager.DummyConnectionManager()
