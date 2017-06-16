#!/usr/bin/python -u
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""RPC methods exported from Goofy."""

from __future__ import print_function

import argparse
import glob
import inspect
import logging
import os
import Queue
import random
import re
import tempfile
import time
import uuid

import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.goofy import goofy_remote
from cros.factory.test.diagnosis.diagnosis_tool import DiagnosisToolRPC
from cros.factory.test.env import paths
from cros.factory.test.event import Event
from cros.factory.test.event import EventClient
from cros.factory.test import factory
from cros.factory.test import i18n
from cros.factory.test import shopfloor
from cros.factory.test import state
from cros.factory.test.test_lists.test_lists import SetActiveTestList
from cros.factory.tools import factory_bug
from cros.factory.utils import debug_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import string_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils


DEFAULT_GOOFY_RPC_TIMEOUT_SECS = 10
REBOOT_AFTER_UPDATE_DELAY_SECS = 5
PING_SHOPFLOOR_TIMEOUT_SECS = 2
UPLOAD_FACTORY_LOGS_TIMEOUT_SECS = 20
RunState = type_utils.Enum(['UNINITIALIZED', 'STARTING', 'NOT_ACTIVE_RUN',
                            'RUNNING', 'FINISHED'])


class GoofyRPCException(Exception):
  """Goofy RPC exception."""
  pass


class GoofyRPC(object):
  """Goofy RPC main class."""

  def _InRunQueue(self, func, timeout_secs=None):
    """Runs a function in the Goofy run queue.

    Args:
      func: A callable to evaluate in Goofy run queue.
      timeout_secs: The duration in seconds after which to abort the call.  None
        to block until the call is done.

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
      except Exception:
        # Failure (but not an Exception); wrap whatever it is in an exception.
        result.put((None, GoofyRPCException(debug_utils.FormatExceptionOnly())))

    def _GetFuncString():
      func_string = func.__name__
      if func.__name__ == '<lambda>':
        try:
          func_string = inspect.getsource(func).strip()
        except IOError:
          pass
      return func_string

    self.goofy.run_queue.put(Target)
    try:
      ret, exc = result.get(block=True, timeout=timeout_secs)
    except Queue.Empty:
      raise GoofyRPCException('Time out waiting for %s to complete' %
                              _GetFuncString())
    if exc:
      raise exc
    return ret

  def __init__(self, goofy):
    self.goofy = goofy

    # Creates delegate of RPC for diagnosis tool.
    self.diagnosis_tool_rpc = DiagnosisToolRPC(self)

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
        # pylint: disable=unnecessary-lambda,cell-var-from-loop
        state_instance.__dict__[name] = (
            lambda *args, **kwargs: m(*args, **kwargs))
        # pylint: enable=unnecessary-lambda,cell-var-from-loop
      SetEntry(m)

  def FlushEventLogs(self):
    """Flushes event logs if an event_log_watcher is available.

    Raises an Exception if syncing fails.
    """
    self.goofy.log_watcher.FlushEventLogs()

  def FlushTestlog(self, timeout=None):
    """Flushes Testlog logs.

    Returns:
      If successful, returns a string describing the flushing result.

    Raises:
      FlushException if flush was not successful.
    """
    return self.goofy.testlog.Flush(timeout)

  def UpdateFactory(self):
    """Performs a factory update.

    Returns:
      {'success': success, 'updated': updated, 'restart_time': restart_time,
       'error_msg': error_msg} where:
        success: Whether the operation was successful.
        updated: Whether the update was a success and the system will reboot.
        restart_time: The time at which the system will restart (on success).
        error_msg: An error message (on failure).
    """
    ret_value = Queue.Queue()
    # Record the existence of the host-based tag files, so we can restore them
    # after the update.
    device_tag = os.path.join(
        paths.FACTORY_DIR, 'init', goofy_remote.DEVICE_TAG)
    presenter_tag = os.path.join(
        paths.FACTORY_DIR, 'init', goofy_remote.PRESENTER_TAG)
    is_device = os.path.exists(device_tag)
    is_presenter = os.path.exists(presenter_tag)

    def PostUpdateHook():
      def _RestoreTag(tag_status, tag_path):
        if tag_status:
          file_utils.TouchFile(tag_path)
        else:
          file_utils.TryUnlink(tag_path)

      # Restore all the host-based tag files after update.
      _RestoreTag(is_device, device_tag)
      _RestoreTag(is_presenter, presenter_tag)

      # After update, wait REBOOT_AFTER_UPDATE_DELAY_SECS before the
      # update, and return a value to the caller.
      now = time.time()
      ret_value.put({
          'success': True, 'updated': True,
          'restart_time': now + REBOOT_AFTER_UPDATE_DELAY_SECS,
          'error_msg': None})
      time.sleep(REBOOT_AFTER_UPDATE_DELAY_SECS)

    def Target():
      try:
        self.goofy.update_factory(
            auto_run_on_restart=True,
            post_update_hook=PostUpdateHook)
        # Returned... which means that no update was necessary.
        ret_value.put({
            'success': True, 'updated': False, 'restart_time': None,
            'error_msg': None})
      except Exception:
        # There was an update available, but we couldn't get it.
        logging.exception('Update failed')
        ret_value.put({
            'success': False, 'updated': False, 'restart_time': None,
            'error_msg': debug_utils.FormatExceptionOnly()})

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
      {'dev': dev, 'name': archive_name, 'size': archive_size,
       'temporary': temporary}:
        dev: The device that was mounted or used
        archive_name: The file name of the archive
        archive_size: The size of the archive
        temporary: Whether the USB drive was temporarily mounted
    """
    try:
      with factory_bug.MountUSB() as mount:
        output_file = factory_bug.SaveLogs(mount.mount_point,
                                           archive_id=archive_id)
        return {'dev': mount.dev,
                'name': os.path.basename(output_file),
                'size': os.path.getsize(output_file),
                'temporary': mount.temporary}
    except Exception:
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
      {'name': archive_name, 'size': archive_size, 'key': archive_key}
        archive_name: The uploaded file name.
        archive_size: The size of the archive.
        archive_key: A "key" that may later be used to refer to the archive.
            This is just a randomly-chosen 8-digit number.
    """
    archive_key = '%08d' % random.SystemRandom().randint(0, 1e8)
    archive_id = '.'.join([re.sub('[^A-Za-z0-9.]', '_', x)
                           for x in (archive_key, name, serial, description)])
    output_file = factory_bug.SaveLogs(tempfile.gettempdir(),
                                       archive_id=archive_id)
    try:
      with open(output_file) as f:
        data = f.read()
      shopfloor.get_instance(
          detect=True, timeout=UPLOAD_FACTORY_LOGS_TIMEOUT_SECS
      ).SaveAuxLog(os.path.basename(output_file),
                   shopfloor.Binary(data))
      return {'name': os.path.basename(output_file),
              'size': os.path.getsize(output_file),
              'key': archive_key}
    finally:
      file_utils.TryUnlink(output_file)

  def PostEvent(self, event):
    """Posts an event."""
    self.goofy.event_client.post_event(event)

  def StopTest(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Stops current tests."""
    self._InRunQueue(
        lambda: self.goofy.stop(reason='RPC call to stop tests',
                                fail=True),
        timeout_secs=timeout_secs)

  def ClearState(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Stops current tests and clear all test state."""
    def Target():
      self.goofy.stop(reason='RPC call to clear test state',
                      fail=True)
      self.goofy.clear_state()
    self._InRunQueue(Target, timeout_secs=timeout_secs)

  def RunTest(self, path, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Runs a test."""
    test = self.goofy.test_list.LookupPath(path)
    if not test:
      raise GoofyRPCException('Unknown test path %r' % path)
    test = test.GetTopLevelParentOrGroup()

    self._InRunQueue(lambda: self.goofy.restart_tests(root=test),
                     timeout_secs=timeout_secs)
    return self.goofy.run_id

  def RestartAllTests(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Restarts all tests.

    Args:
      timeout_secs: The duration in seconds after which to abort the call.
    """
    self._InRunQueue(self.goofy.restart_tests, timeout_secs=timeout_secs)
    return self.goofy.run_id

  def ScheduleRestart(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Schedules to restart all tests when current test finished.

    Args:
      timeout_secs: The duration in seconds after which to abort the call.
    """
    self._InRunQueue(self.goofy.schedule_restart, timeout_secs=timeout_secs)

  def CancelPendingTests(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Cancels all pending tests."""
    self._InRunQueue(self.goofy.cancel_pending_tests,
                     timeout_secs=timeout_secs)

  def Shutdown(self, operation):
    """Starts a shutdown operation through Goofy.

    Args:
      operation: The shutdown operation to run ('halt', 'reboot',
        or 'full_reboot').
    """
    if operation not in ['halt', 'reboot', 'full_reboot']:
      raise GoofyRPCException('Invalid shutdown operation %r' % operation)
    # No timeout for shutdown as the operation can be delayed for arbitrary
    # duration by the factory test.
    self._InRunQueue(lambda: self.goofy.shutdown(operation))

  def GetLastShutdownTime(self):
    """Gets last shutdown time detected by Goofy."""
    return self.goofy.last_shutdown_time

  def UIPresenterCountdown(self, message, timeout_secs, timeout_message,
                           timeout_is_error=True):
    """Starts a countdown on the presenter UI.

    In situations like a reboot, Goofy is not available and on the UI
    presenter side, it looks like a disconnected state. To avoid confusing
    operators, this method may be used to inform the current status of Goofy
    and set a timeout by which Goofy is expected to come back alive.

    Args:
      message: The text to show while counting down.
      timeout_secs: The timeout for countdown.
      timeout_message: The text to show when countdown ends.
      timeout_is_error: True for red timeout message; False for black.
    """
    if self.goofy.link_manager:
      self.goofy.link_manager.StartCountdown(
          message, timeout_secs, timeout_message,
          'red' if timeout_is_error else 'black')

  def SuspendDUTMonitoring(self, interval_sec):
    """Suspends monitoring of DUT connection.

    For some tests, DUT is expected to go offline for a short period without
    rebooting. In this case, we don't want the presenter to reload the UI;
    otherwise, we lose the UI of the current running tests. By suspending
    monitoring, the link manager on the presenter side knows to ignore
    connection failure for a given amount of time.

    Args:
      interval_sec: Number of seconds to suspend.
    """
    if self.goofy.link_manager:
      self.goofy.link_manager.SuspendMonitoring(interval_sec)

  def ResumeDUTMonitoring(self):
    """Immediately resume suspended monitoring of DUT connection."""
    if self.goofy.link_manager:
      self.goofy.link_manager.ResumeMonitoring()

  def _GetTests(self):
    """Helper method to get a list of all tests and their states."""
    paths_to_run = set(self.goofy.test_list_iterator.GetPendingTests())
    ret = []
    states = self.goofy.state_instance.get_test_states()
    for t in self.goofy.test_list.Walk(in_order=True):
      test_state = states.get(t.path)
      ret.append(dict(path=t.path,
                      parent=(t.subtests != []),
                      pending=t.path in paths_to_run,
                      **test_state.__dict__))
    return ret

  def IsReadyForUIConnection(self):
    """Checks whether the Goofy backend is ready for UI connection.

    Returns:
      A boolean indicating whether the Goofy backend is ready for UI connection.
    """
    return self.goofy.ready_for_ui_connection

  def GetTests(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Returns a list of all tests and their states.

    Args:
      timeout_secs: The duration in seconds after which to abort the call.
    """
    return self._InRunQueue(self._GetTests, timeout_secs=timeout_secs)

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
          dict(id=k, name=v.label,
               enabled=(k == self.goofy.test_list.test_list_id)))

    # Sort by name.
    ret.sort(key=lambda x: i18n.Translated(x['name'])['en-US'].lower())

    return ret

  def GetTestList(self):
    """Returns the test list."""
    return self.goofy.test_list.ToStruct()

  def GetGoofyStatus(self):
    """Returns a dictionary containing Goofy status information.

    Returns:
      A dict with the following elements:
        uuid: A UUID identifying the current goofy run.
        test_list_id: The active test_list ID.
        status: The current status of Goofy.
    """
    return {'uuid': self.goofy.uuid,
            'test_list_id': (
                self.goofy.test_list.test_list_id if self.goofy.test_list
                else None),
            'run_id': self.goofy.run_id,
            'status': self.goofy.status}

  def GetActiveRunID(self):
    """Gets the id of the current active test run."""
    return self.goofy.run_id

  def GetTestRunStatus(self, run_id,
                       timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Returns the status of a given test run.

    The given run id must match the last run id stored in Goofy to get the
    status.

    Args:
      run_id: The id of a test run or None to get current test run status in
        Goofy.
      timeout_secs: The duration in seconds after which to abort the call.

    Returns:
      A dict with the following elements:
        status: The status of the given run of factory tests.

          - UNINITIALIZED: No run has been scheduled yet.
          - STARTING: Goofy just went through a reboot and the latest test run
                      state has not been restored.
          - NOT_ACTIVE_RUN: If the given run is not the current active one.
          - RUNNING: Goofy is running the scheduled tests of the given run.
          - FINISHED: Goofy has finished running the scheduled tests of the
                      given run.

        If status is RUNNING or FINISHED, the following elements are also
        included:

        run_id: The id of the current active run.
        scheduled_tests: A list of factory tests that were scheduled for
          the active run and their status.
    """
    def Target(run_id):
      if not run_id:
        run_id = self.goofy.run_id

      ret_val = {}
      if self.goofy.run_id is None:
        if self.goofy.state_instance.get_shared_data('run_id', optional=True):
          # A run ID is present in shared data but hasn't been restored.
          ret_val['status'] = RunState.STARTING
        else:
          # No test run has ever been scheduled.
          ret_val['status'] = RunState.UNINITIALIZED
      elif run_id != self.goofy.run_id:
        ret_val['status'] = RunState.NOT_ACTIVE_RUN
      else:
        tests = self._GetTests()
        scheduled_tests_status = [t for t in tests if t['path'] in
                                  self.goofy.scheduled_run_tests]
        ret_val['run_id'] = self.goofy.run_id,
        ret_val['scheduled_tests'] = scheduled_tests_status

        if (self.goofy.test_list_iterator.GetPendingTests() or
            any(t['status'] == factory.TestState.ACTIVE
                for t in scheduled_tests_status)):
          ret_val['status'] = RunState.RUNNING
        else:
          ret_val['status'] = RunState.FINISHED
      return ret_val

    return self._InRunQueue(lambda: Target(run_id), timeout_secs=timeout_secs)

  def SwitchTestList(self, test_list_id, automation_mode='none'):
    """Switches test lists.

    Args:
      test_list_id: The test list ID.
      automation_mode: The automation mode to enable.  Valid values are:
        ('none', 'partial', 'full').

    Raises:
      TestListError: The test list does not exist.
    """
    # Have goofy throw an error if the test list ID is invalid.
    self.goofy.GetTestList(test_list_id)
    SetActiveTestList(test_list_id)

    if sys_utils.InChroot():
      raise GoofyRPCException(
          'Cannot switch test in chroot; please manually restart Goofy')
    else:
      # Reset goofy_ghost so the test list in overlord is correct.
      process_utils.Spawn(['goofy_ghost', 'reset'], call=True)
      # Restart Goofy and clear state.
      process_utils.Spawn(
          ['nohup ' +
           os.path.join(paths.FACTORY_DIR, 'bin', 'factory_restart') +
           ' --automation-mode %s -a &' % automation_mode],
          shell=True, check_call=True)
      # Wait for a while.  This process should be killed long before
      # 60 seconds have passed.
      time.sleep(60)
      # This should never be reached, but not much we can do but
      # complain to the caller.
      raise GoofyRPCException('Factory did not restart as expected')

  def DeviceTakeScreenshot(self, output_file=None):
    """Takes screenshots of all the connected ports on the device.

    Args:
      output_file: The output file path to store the captured image file.
          If not given, screenshots are saved to:

            /var/log/screenshot_<TIME>-<PORT>.png

          If a file path is given, screenshots are saved to:

            <file path base>-<PORT>.<file path extension>
    """
    if not output_file:
      output_filename = ('/var/log/screenshot_%s-%%s.png' %
                         time.strftime('%Y%m%d-%H%M%S'))
    else:
      output_filename = '%s-%%s%s' % os.path.splitext(output_file)

    display = device_utils.CreateDUTInterface().display
    for port_id, port_info in display.GetPortInfo().iteritems():
      if port_info.connected:
        display.CaptureFramebuffer(port_id).save(output_filename % port_id)

  def CallExtension(self, name, timeout=DEFAULT_GOOFY_RPC_TIMEOUT_SECS,
                    **kwargs):
    """Invokes a RPC call to Factory Test Chrome Extension.

    Blocks until a return value is retrieved or if timeout is reached.

    Args:
      name: The name of extension RPC function to execute.
      timeout: Seconds to wait before RPC timeout.
      kwargs: Arguments to pass to the extension; they will be
        available in an "args" dict within the execution context.

    Returns:
      An object representing RPC call return value.

    Raises:
      type_utils.TimeoutError: if no response until timeout reached.
    """
    # To support timeout (and to avoid race condition), we need a dedicated
    # event client.
    rpc_id = str(uuid.uuid4())
    rpc_event = Event(Event.Type.EXTENSION_RPC, name=name, is_response=False,
                      rpc_id=rpc_id, args=kwargs)
    with EventClient() as event_client:
      result = event_client.request_response(
          rpc_event,
          lambda e: (e.type == rpc_event.type and e.rpc_id == rpc_id and
                     e.is_response),
          timeout)
      if result is None:
        raise type_utils.TimeoutError('Failed calling Extension RPC <%r>', name)
      return result.args

  def DeviceGetDisplayInfo(self, timeout=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Returns display information on the device (by calling extension RPC).

    Args:
      timeout: Seconds to wait before RPC timeout.

    Returns:
      A list of objects for current display. See Chrome Extension API
          chrome.system.display for the details.

    Raises:
      type_utils.TimeoutError: if no response until timeout.
    """
    return self.CallExtension('GetDisplayInfo', timeout=timeout)

  def DiagnosisToolRpc(self, *args):
    """Receives a rpc request for diagnosis tool."""
    return getattr(self.diagnosis_tool_rpc, args[0])(*args[1:])

  def DeviceCreateWindow(self, left, top,
                         timeout=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Creates a Chrome window on the device and returns its ID.

    Args:
      left: The offset in pixels from left.
      top: The offset in pixels from top.
      timeout: Seconds to wait before RPC timeout.

    Returns:
      The attributes of the created window. See Chrome Extension API
          chrome.windows for the details.

    Raises:
      type_utils.TimeoutError: if no response until timeout.
    """
    return self.CallExtension('CreateWindow', timeout=timeout,
                              left=left, top=top)

  def DeviceUpdateWindow(self, window_id, update_info,
                         timeout=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Updates a Chrome window on the device.

    See Chrome Extension API chrome.windows for the details.

    Args:
      window_id: The ID of the window.
      update_info: A dict of update info.
      timeout: Seconds to wait before RPC timeout.

    Raises:
      type_utils.TimeoutError: if no response until timeout.
    """
    self.CallExtension('UpdateWindow', timeout=timeout,
                       window_id=window_id, update_info=update_info)

  def DeviceRemoveWindow(self, window_id,
                         timeout=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Removes a Chrome window on the device.

    See Chrome Extension API chrome.windows for the details.

    Args:
      window_id: The ID of the window.
      timeout: Seconds to wait before RPC timeout.

    Raises:
      type_utils.TimeoutError: if no response until timeout.
    """
    self.CallExtension('RemoveWindow', timeout=timeout, window_id=window_id)

  def DeviceQueryTabs(self, window_id, timeout=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Queries the tabs of the given window on the device.

    See Chrome Extension API chrome.tabs for the details.

    Args:
      window_id: The ID of the window.
      timeout: Seconds to wait before RPC timeout.

    Returns:
      A list of the tab info.

    Raises:
      type_utils.TimeoutError: if no response until timeout.
    """
    return self.CallExtension('QueryTabs', timeout=timeout, window_id=window_id)

  def DeviceUpdateTab(self, tab_id, update_info,
                      timeout=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Updates the tab on the device.

    See Chrome Extension API chrome.tabs for the details.

    Args:
      tab_id: The ID of the tab.
      update_info: A dict of update info.
      timeout: Seconds to wait before RPC timeout.

    Raises:
      type_utils.TimeoutError: if no response until timeout.
    """
    self.CallExtension('UpdateTab', timeout=timeout,
                       tab_id=tab_id, update_info=update_info)

  def UpdateStatus(self, all_pass):
    """Updates the color of tab in presenter.

    Args:
      all_pass: A boolean value. True if no failed test.
    """
    if self.goofy.link_manager:
      self.goofy.link_manager.UpdateStatus(all_pass)

  def GetTestHistory(self, *test_paths):
    """Returns metadata for all previous (and current) runs of a test."""
    ret = []

    for path in test_paths:
      for f in glob.glob(os.path.join(paths.DATA_TESTS_DIR,
                                      path + '-*',
                                      'metadata')):
        try:
          ret.append(yaml.load(open(f)))
        except Exception:
          logging.exception('Unable to load test metadata %s', f)

    ret.sort(key=lambda item: item.get('init_time', None))
    return ret

  def GetTestHistoryEntry(self, path, invocation):
    """Returns metadata and log for one test invocation."""
    test_dir = os.path.join(paths.DATA_TESTS_DIR,
                            '%s-%s' % (path, invocation))

    log_file = os.path.join(test_dir, 'log')
    try:
      log = string_utils.CleanUTF8(file_utils.ReadFile(log_file))
    except Exception:
      # Oh well
      logging.exception('Unable to read log file %s', log_file)
      log = None

    return {'metadata': yaml.load(open(os.path.join(test_dir, 'metadata'))),
            'log': log}

  def GetPluginMenuItems(self):
    """Returns menu items supported by plugins."""
    return self.goofy.plugin_controller.GetPluginMenuItems()

  def OnPluginMenuItemClicked(self, item_id):
    """Called when a plugin menu item is clicked."""
    return self.goofy.plugin_controller.OnMenuItemClicked(item_id)

  def GetPluginFrontendURLs(self):
    """Returns a list of URLs of all plugin's UI."""
    return self.goofy.plugin_controller.GetFrontendURLs()


def main():
  parser = argparse.ArgumentParser(
      description='Sends an RPC to Goofy.')
  parser.add_argument(
      'command',
      help=('The command to run (as a Python expression), e.g.: '
            """RunTest('RunIn.Stress.BadBlocks')"""))
  args = parser.parse_args()

  goofy = state.get_instance()
  logging.basicConfig(level=logging.INFO)

  if '(' not in args.command:
    parser.error('Expected parentheses in command, e.g.: '
                 """RunTest('RunIn.Stress.BadBlocks')""")

  logging.info('Evaluating expression: %s', args.command)
  ret = eval(args.command, {},  # pylint: disable=eval-used
             dict((x, getattr(goofy, x))
                  for x in GoofyRPC.__dict__.keys()
                  if not x.startswith('_')))
  if ret is not None:
    print(yaml.safe_dump(ret))


if __name__ == '__main__':
  main()
