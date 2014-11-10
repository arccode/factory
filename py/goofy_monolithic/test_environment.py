#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Enviroment objects that handles external test operations."""

from __future__ import print_function

import cPickle as pickle
import hashlib
import logging
import os
import subprocess
import threading
import time

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import connection_manager
from cros.factory.system.service_manager import GetServiceStatus
from cros.factory.system.service_manager import SetServiceStatus
from cros.factory.system.service_manager import Status
from cros.factory.test import state
from cros.factory.test import utils
from cros.factory.tools import chrome_debugger


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

  def override_chrome_start_pages(self):
    # TODO(hungte) Remove this workaround (mainly for crbug.com/431645).
    override_chrome_start_file = '/usr/local/factory/init/override_chrome_start'
    if not os.path.exists(override_chrome_start_file):
      return
    chrome = chrome_debugger.ChromeRemoteDebugger()
    utils.WaitFor(chrome.IsReady, 30)
    chrome.SetActivePage()
    chrome.PageNavigate(open(override_chrome_start_file).read() or
                        ('http://127.0.0.1:%s/' %
                         state.DEFAULT_FACTORY_STATE_PORT))

  def launch_chrome(self):
    self.override_chrome_start_pages()

    utils.WaitFor(self.goofy.web_socket_manager.has_sockets, 30)
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
           'Please open http://localhost:%d/ in Chrome.',
           state.DEFAULT_FACTORY_STATE_PORT)

  def create_connection_manager(self, wlans, scan_wifi_period_secs):
    return connection_manager.DummyConnectionManager()
