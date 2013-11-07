#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""RPC methods exported from Goofy."""

import argparse
import inspect
import logging
import os
import Queue
import random
import re
import tempfile
import threading
import time
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory import factory_bug
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import state
from cros.factory.test import utils
from cros.factory.test.event import Event
from cros.factory.test.test_lists.test_lists import SetActiveTestList
from cros.factory.utils import debug_utils, file_utils, process_utils


REBOOT_AFTER_UPDATE_DELAY_SECS = 5
PING_SHOPFLOOR_TIMEOUT_SECS = 2
UPLOAD_FACTORY_LOGS_TIMEOUT_SECS = 20
VAR_LOG_MESSAGES = '/var/log/messages'


class GoofyRPCException(Exception):
  pass


class GoofyRPC(object):
  def _InRunQueue(self, func):
    """Runs a function in the Goofy run queue.

    Returns:
      Any value returned by the function.

    Raises:
      Any exception raised by the function.
    """
    # A queue to store the results of evaluating the function.  This
    # will contain a two-element tuple (ret, exc), where ret is the
    # return value or exc is any exception thrown.  Only one will be
    # set.
    result = Queue.Queue()
    def Target():
      try:
        # Call the function, and put the the return value on success.
        result.put((func(), None))
      except Exception as e:
        # Failure; put e.
        logging.exception('Exception in RPC handler')
        result.put((None, e))
      except:
        # Failure (but not an Exception); wrap whatever it is in an exception.
        result.put((None, GoofyRPCException(utils.FormatExceptionOnly())))

    self.goofy.run_queue.put(Target)
    ret, exc = result.get()
    if exc:
      raise exc
    return ret

  def __init__(self, goofy):
    self.goofy = goofy

  def RegisterMethods(self, state_instance):
    """Registers exported RPC methods in a state object."""
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
    """Flushes event logs if an event_log_watcher is available.

    Raises an Exception if syncing fails.
    """
    self.goofy.log_watcher.FlushEventLogs()

  def UpdateFactory(self):
    """Performs a factory update.

    Returns:
      [success, updated, restart_time, error_msg] where:
        success: Whether the operation was successful.
        updated: Whether the update was a success and the system will reboot.
        restart_time: The time at which the system will restart (on success).
        error_msg: An error message (on failure).
    """
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
    if note['level'] == 'CRITICAL':
      self.goofy.run_queue.put(self.goofy.stop)
    self.goofy.state_instance.append_shared_data_list(
        'factory_note', note)
    self.PostEvent(Event(Event.Type.UPDATE_NOTES))

  def GetVarLogMessages(self, max_length=256*1024):
    """Returns the last n bytes of /var/log/messages.

    Args:
      max_length: Maximum number of bytes to return.
    """
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
    """Returns the last few lines in /var/log/messages before the current boot.

    Args:
      See utils.var_log_messages_before_reboot.
    """
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
    """Returns the contents of dmesg.

    Approximate timestamps are added to each line."""
    dmesg = process_utils.Spawn(['dmesg'],
                                check_call=True, read_stdout=True).stdout_data
    uptime = float(self._ReadUptime().split()[0])
    boot_time = time.time() - uptime

    def FormatTime(match):
      return (utils.TimeString(boot_time + float(match.group(1))) + ' ' +
              match.group(0))

    # (?m) = multiline
    return re.sub(r'(?m)^\[\s*([.\d]+)\]', FormatTime, dmesg)

  def LogStackTraces(self):
    """Logs the stack backtraces of all threads."""
    logging.info(debug_utils.DumpStackTracebacks())

  def IsUSBDriveAvailable(self):
    try:
      with factory_bug.MountUSB(read_only=True):
        return True
    except (IOError, OSError):
      return False

  def SaveLogsToUSB(self, archive_id=None):
    """Saves logs to a USB stick.

    Returns:
      [dev, archive_name, archive_size, temporary]:
        dev: The device that was mounted or used
        archive_name: The file name of the archive
        archive_size: The size of the archive
        temporary: Whether the USB drive was temporarily mounted
    """
    try:
      with factory_bug.MountUSB() as mount:
        output_file = factory_bug.SaveLogs(mount.mount_point, archive_id)
        return [mount.dev, os.path.basename(output_file),
                os.path.getsize(output_file),
                mount.temporary]
    except:
      logging.exception('Unable to save logs to USB')
      raise

  def PingShopFloorServer(self):
    """Pings the shop floor server.

    Raises:
      Exception if unable to contact shop floor server.
    """
    shopfloor.get_instance(
        detect=True, timeout=PING_SHOPFLOOR_TIMEOUT_SECS).Ping()

  def UploadFactoryLogs(self, name, serial, description):
    """Uploads logs to the shopfloor server.

    Returns:
      [archive_name, archive_size, archive_key]
        archive_name: The uploaded file name.
        archive_size: The size of the archive.
        archive_key: A "key" that may later be used to refer to the archive.
            This is just a randomly-chosen 8-digit number.
    """
    archive_key = "%08d" % random.SystemRandom().randint(0, 1e8)
    archive_id = '.'.join([re.sub('[^A-Za-z0-9.]', '_', x)
                           for x in (archive_key, name, serial, description)])
    output_file = factory_bug.SaveLogs(tempfile.gettempdir(), archive_id)
    try:
      with open(output_file) as f:
        data = f.read()
      shopfloor.get_instance(
          detect=True, timeout=UPLOAD_FACTORY_LOGS_TIMEOUT_SECS
          ).SaveAuxLog(os.path.basename(output_file),
                       shopfloor.Binary(data))
      return [os.path.basename(output_file), os.path.getsize(output_file),
              archive_key]
    finally:
      file_utils.TryUnlink(output_file)

  def UpdateSkippedTests(self):
    """Updates skipped tests based on run_if."""
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
    """Posts an event."""
    self.goofy.event_client.post_event(event)

  def StopTest(self):
    """Stops current tests."""
    self._InRunQueue(
        lambda: self.goofy.stop(reason='RPC call to stop tests',
                                fail=True))

  def ClearState(self):
    """Stops current tests and clear all test state."""
    def Target():
      self.goofy.stop(reason='RPC call to clear test state',
                      fail=True)
      self.goofy.clear_state()
    self._InRunQueue(Target)

  def RunTest(self, path):
    """Runs a test."""
    test = self.goofy.test_list.lookup_path(path)
    if not test:
      raise GoofyRPCException('Unknown test path %r' % path)
    test = test.get_top_level_parent_or_group()

    self._InRunQueue(lambda: self.goofy.restart_tests(root=test))

  def GetTests(self):
    """Returns a list of all tests and their states."""
    def Target():
      paths_to_run = set([t.path for t in self.goofy.tests_to_run])

      ret = []
      states = self.goofy.state_instance.get_test_states()
      for t in self.goofy.test_list.walk(in_order=True):
        test_state = states.get(t.path)
        ret.append(dict(path=t.path,
                        parent=(t.subtests != []),
                        pending=t.path in paths_to_run,
                        **test_state.__dict__))
      return ret

    return self._InRunQueue(Target)

  def GetTestLists(self):
    """Returns available test lists.

    Returns:
      An array of test lists, each a dict containing:
        id: An identifier for the test list (empty for the default test list).
        name: A human-readable name of the test list.
        enabled: Whether this is the current-enabled test list.
    """
    ret = []
    for k, v in self.goofy.test_lists.iteritems():
      ret.append(
        dict(id=k, name=v.label_en,
             enabled=(k == self.goofy.test_list.test_list_id)))

    # Sort by name.
    ret.sort(key=lambda x: x['name'].lower())

    return ret

  def GetGoofyStatus(self):
    """Returns a dictionary containing Goofy status information.

    Returns: A dict with the following elements:
      uuid: A UUID identifying the current goofy run
      test_list_id: The active test_list ID
    """
    return {'uuid': self.goofy.uuid,
            'test_list_id': (
                self.goofy.test_list.test_list_id if self.goofy.test_list
                else None),
            'status': self.goofy.status}

  def SwitchTestList(self, test_list_id):
    """Switches test lists.

    Args:
      test_list_id: The test list ID.

    Raises:
      TestListError: The test list does not exist.
    """
    # Have goofy throw an error if the test list ID is invalid.
    self.goofy.GetTestList(test_list_id)
    SetActiveTestList(test_list_id)

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

  def _GetGoofyTab(self):
    if utils.in_chroot():
      raise GoofyRPCException(
          'Cannot evaluate Javascript through telemetry in chroot')
    if not self.goofy.env.browser:
      raise GoofyRPCException('Browser instance is not initialized')

    tabs = self.goofy.env.browser.tabs
    for i in xrange(0, len(tabs)):
      if tabs[i].url == ('http://127.0.0.1:%d/' %
                         state.DEFAULT_FACTORY_STATE_PORT):
        return tabs[i]

  def EvaluateJavaScript(self, script):
    return self._GetGoofyTab().EvaluateJavaScript(script)

  def ExecuteJavaScript(self, script):
    self._GetGoofyTab().ExecuteJavaScript(script)

  def GetDisplayInfo(self):
    """Gets display info from the factory test chrome extension page.

    Returns:
      A dict of display info.

    Raises:
      GoofyRPCException: If this is called inside chroot, or browser instance is
          not initialized.
    """
    if utils.in_chroot():
      raise GoofyRPCException('Cannot get display info in chroot')
    if not self.goofy.env.browser or not self.goofy.env.extension:
      raise GoofyRPCException('Browser instance is not initialized')

    ext_page = self.goofy.env.browser.extensions[self.goofy.env.extension]
    ext_page.ExecuteJavaScript(
        'window.__display_info = null;')
    ext_page.ExecuteJavaScript(
        'chrome.system.display.getInfo(function(info) {'
        '    window.__display_info = info;})')

    def _FetchDisplayInfo():
      return ext_page.EvaluateJavaScript(
          'window.__display_info')

    utils.WaitFor(_FetchDisplayInfo, 10)
    return _FetchDisplayInfo()

  def TakeScreenshot(self, output_file=None):
    """Takes a screenshot through Telemetry tab.Screenshot API.

    Args:
      output_file: The output file path to store the captured PNG file.  If not
          given the screenshot is saved to /var/log/screenshot_<TIME>.png.
    """
    screenshot = self._GetGoofyTab().Screenshot(timeout=5)
    if not output_file:
      output_file = (
          '/var/log/screenshot_%s.png' % time.ctime().replace(' ', '_'))
    screenshot.WriteFile(output_file)


def main():
  parser = argparse.ArgumentParser(
      description="Sends an RPC to Goofy.")
  parser.add_argument(
      'command',
      help=('The command to run (as a Python expression), e.g.: '
            """RunTest('RunIn.Stress.BadBlocks')"""))
  args = parser.parse_args()

  goofy = factory.get_state_instance()
  logging.basicConfig(level=logging.INFO)

  if '(' not in args.command:
    parser.error('Expected parentheses in command, e.g.: '
                 """RunTest('RunIn.Stress.BadBlocks')""")

  logging.info('Evaluating expression: %s', args.command)
  ret = eval(args.command, {},
             dict((x, getattr(goofy, x))
                  for x in GoofyRPC.__dict__.keys()
                  if not x.startswith('_')))
  if ret is not None:
    print yaml.safe_dump(ret)


if __name__ == '__main__':
  main()
