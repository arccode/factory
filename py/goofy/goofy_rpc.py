#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''RPC methods exported from Goofy.'''

import inspect
import logging
import os
import Queue
import re
import time

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.utils.process_utils import Spawn


REBOOT_AFTER_UPDATE_DELAY_SECS = 5
VAR_LOG_MESSAGES = '/var/log/messages'


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

  def GetVarLogMessages(self, max_length=256*1024):
    '''Returns the last n bytes of /var/log/messages.

    Args:
      max_length: Maximum number of bytes to return.
    '''
    offset = max(0, os.path.getsize(VAR_LOG_MESSAGES) - max_length)
    with open(VAR_LOG_MESSAGES, 'r') as f:
      f.seek(offset)
      if offset != 0:
        # Skip first (probably incomplete) line
        offset += len(f.readline())
      data = f.read()

    if offset:
      data = ('<truncated %d bytes>\n' % offset) + data

    return unicode(data, encoding='utf-8', errors='replace')

  def GetVarLogMessagesBeforeReboot(self, lines=100, max_length=5*1024*1024):
    '''Returns the last few lines in /var/log/messages before the current boot.

    Args:
      See utils.var_log_messages_before_reboot.
    '''
    lines = utils.var_log_messages_before_reboot(lines=lines,
                                                 max_length=max_length)
    if lines:
      return unicode('\n'.join(lines) + '\n',
                     encoding='utf-8', errors='replace')
    else:
      return None

  def GetDmesg(self):
    '''Returns the contents of dmesg.

    Approximate timestamps are added to each line.'''
    try:
      dmesg = Spawn(['dmesg'], check_call=True, read_stdout=True).stdout_data
      uptime = float(open('/proc/uptime').read().split()[0])
      boot_time = time.time() - uptime

      def FormatTime(match):
        return (utils.TimeString(boot_time + float(match.group(1))) + ' ' +
                match.group(0))

      # (?m) = multiline
      return re.sub(r'(?m)^\[\s*([.\d]+)\]', FormatTime, dmesg)
    except:
      logging.exception('Blah')
      raise
