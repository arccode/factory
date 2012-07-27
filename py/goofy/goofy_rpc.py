#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''RPC methods exported from Goofy.'''

import inspect
import logging
import Queue
import time

from cros.factory.test import utils

REBOOT_AFTER_UPDATE_DELAY_SECS = 5


class GoofyRPC(object):
  def __init__(self, goofy):
    self.goofy = goofy

  def RegisterMethods(self, state_instance):
    '''Registers exported RPC methods in a state object.'''
    for name, m in inspect.getmembers(self):
      # Find all non-private methods (except this one)
      if ((not inspect.ismethod(m)) or
          name.startswith('_') or
          name == 'RegisterMethods'):
        continue

      # Bind the state instance method to our method.  (The _m=m
      # argument is necessary to bind m immediately, since m will
      # change during the next for loop iteration.)
      state_instance.__dict__[name] = (
          lambda _m=m, *args, **kwargs: _m(*args, **kwargs))

  def FlushEventLogs(self):
    '''Flushes event logs if an event_log_watcher is available.

    Raises an Exception if syncing fails.
    '''
    self.goofy.log_watcher.FlushEventLogs()

  def UpdateFactory(self):
    '''Performs a factory update.

    Returns:
      [success, updated, restart_time, error_msg] where:
        success: Whether the operation was successful.
        updated: Whether the update was a success and the system will reboot.
        restart_time: The time at which the system will restart (on success).
        error_msg: An error message (on failure).
    '''
    ret_value = Queue.Queue()

    def PostUpdateHook():
      # After update, wait REBOOT_AFTER_UPDATE_DELAY_SECS before the
      # update, and return a value to the caller.
      now = time.time()
      ret_value.put([True, True, now + REBOOT_AFTER_UPDATE_DELAY_SECS, None])
      time.sleep(REBOOT_AFTER_UPDATE_DELAY_SECS)

    def Target():
      try:
        self.goofy.update_factory(
            auto_run_on_restart=True,
            post_update_hook=PostUpdateHook)
        # Returned... which means that no update was necessary.
        ret_value.put([True, False, None, None])
      except:  # pylint: disable=W0702
        # There was an update available, but we couldn't get it.
        logging.exception('Update failed')
        ret_value.put([False, False, None, utils.FormatExceptionOnly()])

    self.goofy.run_queue.put(Target)
    return ret_value.get()
