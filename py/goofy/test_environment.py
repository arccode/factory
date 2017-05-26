#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Enviroment objects that handles external test operations."""

from __future__ import print_function

import logging
import os
import subprocess
import threading
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.test import state
from cros.factory.tools import chrome_debugger
from cros.factory.utils.service_utils import GetServiceStatus
from cros.factory.utils.service_utils import SetServiceStatus
from cros.factory.utils.service_utils import Status
from cros.factory.utils import sync_utils


class Environment(object):
  """Abstract base class for external test operations, e.g., shutdown or reboot.

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

  def terminate(self):
    """Terminates and cleans up environment."""
    pass


class DUTEnvironment(Environment):
  """A real environment on a device under test."""

  def __init__(self):
    super(DUTEnvironment, self).__init__()
    self.goofy = None  # Must be assigned later by goofy.
    self.has_sockets = None  # Must be assigned later by goofy.

  def shutdown(self, operation):
    def prepare_shutdown():
      """Prepares for a clean shutdown."""
      respawn_services = ['syslog',
                          'tcsd',
                          'shill',
                          'warn-collector']
      for service in respawn_services:
        if GetServiceStatus(service, ignore_failure=True) == Status.START:
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

  def override_chrome_start_pages(self):
    # TODO(hungte) Remove this workaround (mainly for crbug.com/431645).
    override_chrome_start_file = '/usr/local/factory/init/override_chrome_start'
    if not os.path.exists(override_chrome_start_file):
      return
    url = (open(override_chrome_start_file).read() or
           ('http://%s:%s' % (state.DEFAULT_FACTORY_STATE_ADDRESS,
                              state.DEFAULT_FACTORY_STATE_PORT)))
    (host, unused_colon, port) = url.partition('http://')[2].partition(':')
    logging.info('Override chrome start pages as: %s', url)
    chrome = chrome_debugger.ChromeRemoteDebugger()
    sync_utils.WaitFor(chrome.IsReady, 30)
    chrome.SetActivePage()
    # Wait for state server to be ready.
    state_server = state.get_instance(address=host, port=int(port))

    def is_state_server_ready():
      try:
        return state_server.IsReadyForUIConnection()
      except:  # pylint: disable=bare-except
        return False
    sync_utils.WaitFor(is_state_server_ready, 30)
    chrome.PageNavigate(url)

  def launch_chrome(self):
    self.override_chrome_start_pages()
    logging.info(
        'Waiting for a web socket connection from UI presenter app or goofy UI')
    # Set the timeout to a value reasonably long enough such that UI should be
    # ready on all kinds of devices.
    sync_utils.WaitFor(self.has_sockets, 90)


class FakeChrootEnvironment(Environment):
  """A chroot environment that doesn't actually shutdown."""

  def shutdown(self, operation):
    assert operation in ['reboot', 'full_reboot', 'halt']
    logging.warn('In chroot: skipping %s', operation)
    return False

  def launch_chrome(self):
    logging.warn('In chroot; not launching Chrome. '
                 'Please open UI presenter app in Chrome or '
                 'open http://localhost:%d/ in Chrome.',
                 state.DEFAULT_FACTORY_STATE_PORT)
