#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''RPC methods exported from Goofy.'''

import argparse
import glob
import inspect
import logging
import os
import Queue
import re
import threading
import time

import factory_common  # pylint: disable=W0611
from cros.factory import factory_bug
from cros.factory.test import factory
from cros.factory.test import utils
from cros.factory.test.event import Event
from cros.factory.utils import file_utils, process_utils


REBOOT_AFTER_UPDATE_DELAY_SECS = 5
VAR_LOG_MESSAGES = '/var/log/messages'


class GoofyRPCException(Exception):
  pass


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

      # Bind the state instance method to our method.  (We need to
      # put this in a separate method to rebind m, since it will
      # change during the next for loop iteration.)
      def SetEntry(m):
        # pylint: disable=W0108
        state_instance.__dict__[name] = (
          lambda *args, **kwargs: m(*args, **kwargs))
      SetEntry(m)

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

  def AddNote(self, note):
    note['timestamp'] = int(time.time())
    self.goofy.event_log.Log('note',
                             name=note['name'],
                             text=note['text'],
                             timestamp=note['timestamp'],
                             level=note['level'])
    logging.info('Factory note from %s at %s (level=%s): %s',
                 note['name'], note['timestamp'], note['level'],
                 note['text'])
    self.goofy.run_queue.put(self.goofy.stop)
    return self.goofy.state_instance.append_shared_data_list(
        'factory_note', note)

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

  @staticmethod
  def _ReadUptime():
    return open('/proc/uptime').read()

  def GetDmesg(self):
    '''Returns the contents of dmesg.

    Approximate timestamps are added to each line.'''
    dmesg = process_utils.Spawn(['dmesg'],
                                check_call=True, read_stdout=True).stdout_data
    uptime = float(self._ReadUptime().split()[0])
    boot_time = time.time() - uptime

    def FormatTime(match):
      return (utils.TimeString(boot_time + float(match.group(1))) + ' ' +
              match.group(0))

    # (?m) = multiline
    return re.sub(r'(?m)^\[\s*([.\d]+)\]', FormatTime, dmesg)

  def IsUSBDriveAvailable(self):
    try:
      with factory_bug.MountUSB(read_only=True):
        return True
    except (IOError, OSError):
      return False

  def SaveLogsToUSB(self, archive_id=None):
    '''Saves logs to a USB stick.

    Returns:
      [dev, archive_name, archive_size, temporary]:
        dev: The device that was mounted or used
        archive_name: The file name of the archive
        archive_size: The size of the archive
        temporary: Whether the USB drive was temporarily mounted
    '''
    try:
      with factory_bug.MountUSB() as mount:
        output_file = factory_bug.SaveLogs(mount.mount_point, archive_id)
        return [mount.dev, os.path.basename(output_file),
                os.path.getsize(output_file),
                mount.temporary]
    except:
      logging.exception('Unable to save logs to USB')
      raise

  def UpdateSkippedTests(self):
    '''Updates skipped tests based on run_if.'''
    done = threading.Event()

    def Target():
      try:
        self.goofy.update_skipped_tests()
      finally:
        done.set()

    self.goofy.run_queue.put(Target)
    done.wait()

  def SyncTimeWithShopfloorServer(self):
    self.goofy.sync_time_with_shopfloor_server(True)

  def PostEvent(self, event):
    '''Posts an event.'''
    self.goofy.event_client.post_event(event)

  def RunTest(self, path):
    '''Runs a test.'''
    self.PostEvent(Event(Event.Type.RESTART_TESTS,
                         path=path))

  def GetTestLists(self):
    '''Returns available test lists.

    Returns:
      An array of test lists, each a dict containing:
        id: An identifier for the test list (empty for the default test list).
        name: A human-readable name of the test list.
        enabled: Whether this is the current-enabled test list.
    '''
    ret = []

    for f in sorted(
        glob.glob(os.path.join(factory.TEST_LISTS_PATH, 'test_list*'))):
      try:
        if f.endswith('~') or f.endswith('#'):
          continue

        # Special case: if we see test_list.generic but we've already seen
        # test_list, then ignore it (since test_list is provided from
        # the board overlay and overrides test_list.generic).
        if (os.path.basename(f) == 'test_list.generic' and
            any(x['id'] == '' for x in ret)):
          continue

        match = re.match(r'test_list(?:\.(.+))?$', os.path.basename(f))
        if not match:
          continue

        test_list_id = match.group(1) or ''
        name = match.group(1) or 'Default'
        enabled = (os.path.realpath(f) ==
                   os.path.realpath(self.goofy.options.test_list))

        # Look for the test list name, if specified in the test list.
        match = re.search(r"^TEST_LIST_NAME\s*=\s*"
                          r"u?"        # Optional u for unicode
                          r"([\'\"])"  # Single or double quote
                          r"(.+)"      # The actual name
                          r"\1",       # The quotation mark
                          open(f).read(), re.MULTILINE)
        if match:
          name = match.group(2)

        ret.append({'id': test_list_id, 'name': name, 'enabled': enabled})
      except:  # pylint: disable=W0702
        logging.exception('Unable to process test list %s', f)
        # But keep trucking

    return ret

  def SwitchTestList(self, test_list_id):
    '''Switches test lists.

    This adds a symlink from $FACTORY/test_lists/active to the given
    test list.

    Args:
      test_list_id: the suffix of the test list in
          $FACTORY/test_lists, or an empty string for the default test list.
    '''
    path = os.path.join(factory.TEST_LISTS_PATH, 'test_list')
    if test_list_id:
      path += '.' + test_list_id
    if not os.path.isfile(path):
      raise GoofyRPCException('Invalid test list "%s": "%s" does not exist' % (
          test_list_id, path))

    file_utils.TryUnlink(factory.ACTIVE_TEST_LIST_SYMLINK)
    os.symlink(os.path.basename(path), factory.ACTIVE_TEST_LIST_SYMLINK)

    if utils.in_chroot():
      raise GoofyRPCException(
          'Cannot switch test in chroot; please manually restart Goofy')
    else:
      # Restart Goofy and clear state.
      process_utils.Spawn(
          ['nohup ' +
           os.path.join(factory.FACTORY_PATH, 'bin', 'factory_restart') +
           ' -a &'], shell=True, check_call=True)
      # Wait for a while.  This process should be killed long before
      # 60 seconds have passed.
      time.sleep(60)
      # This should never be reached, but not much we can do but
      # complain to the caller.
      raise GoofyRPCException('Factory did not restart as expected')


def main():
  parser = argparse.ArgumentParser(
      description="Sends an RPC to Goofy.")
  parser.add_argument(
      'command',
      help=('The command to run (as a Python expression), e.g.: '
            '''RunTest('RunIn.Stress.BadBlocks')'''))
  args = parser.parse_args()

  goofy = factory.get_state_instance()
  logging.basicConfig(level=logging.INFO)

  if '(' not in args.command:
    parser.error('Expected parentheses in command, e.g.: '
                 '''RunTest('RunIn.Stress.BadBlocks')''')

  logging.info('Evaluating expression: %s', args.command)
  eval(args.command, {},
       dict((x, getattr(goofy, x))
            for x in GoofyRPC.__dict__.keys()
            if not x.startswith('_')))


if __name__ == '__main__':
  main()
