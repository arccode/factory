# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Enviroment objects that handles external test operations."""

from __future__ import print_function

import logging
import subprocess
import threading
import time


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
    raise NotImplementedError

  def terminate(self):
    """Terminates and cleans up environment."""
    pass


class DUTEnvironment(Environment):
  """A real environment on a device under test."""

  def __init__(self):
    super(DUTEnvironment, self).__init__()
    self.goofy = None  # Must be assigned later by goofy.

  def shutdown(self, operation):
    assert operation in ['reboot', 'full_reboot', 'halt']
    logging.info('Shutting down: %s', operation)
    subprocess.check_call('sync')

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
