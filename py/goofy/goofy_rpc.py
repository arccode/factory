#!/usr/bin/env python3
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""RPC methods exported from Goofy."""

import argparse
import base64
import glob
import inspect
import json
import logging
import os
import queue
import random
import re
import tempfile
import time
import uuid
import xmlrpc.client

import yaml

from cros.factory.test.diagnosis.diagnosis_tool import DiagnosisToolRPC
from cros.factory.test.env import paths
from cros.factory.test.event import Event
from cros.factory.test.event import SendEvent
from cros.factory.test.i18n import translation
from cros.factory.test import server_proxy
from cros.factory.test import state
from cros.factory.test.test_lists import manager
from cros.factory.test.test_lists import test_list
from cros.factory.tools import factory_bug
from cros.factory.utils import debug_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils


DEFAULT_GOOFY_RPC_TIMEOUT_SECS = 15
REBOOT_AFTER_UPDATE_DELAY_SECS = 5
PING_SERVER_TIMEOUT_SECS = 2
UPLOAD_FACTORY_LOGS_TIMEOUT_SECS = 20
RunState = type_utils.Enum(['UNINITIALIZED', 'STARTING', 'NOT_ACTIVE_RUN',
                            'RUNNING', 'FINISHED'])


class GoofyRPCException(Exception):
  """Goofy RPC exception."""


class GoofyRPC:
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
    result = queue.Queue()

    def Target():
      try:
        # Call the function, and put the the return value on success.
        result.put((func(), None))
      except Exception as e:
        # Failure; put e.
        logging.exception('Exception in RPC handler')
        result.put((None, e))
      except:  # pylint: disable=bare-except
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

    self.goofy.RunEnqueue(Target)
    try:
      ret, exc = result.get(block=True, timeout=timeout_secs)
    except queue.Empty:
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

  def FlushTestlog(self, *args, **kwargs):
    """Flushes Testlog logs.

    Returns:
      If successful, returns a string describing the flushing result.

    Raises:
      FlushException if flush was not successful.
    """
    return self.goofy.testlog.Flush(*args, **kwargs)

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
    ret_value = queue.Queue()

    def PostUpdateHook():
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
        self.goofy.UpdateFactory(
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

    self.goofy.RunEnqueue(Target)
    return ret_value.get()

  def AddNote(self, note):
    note['timestamp'] = int(time.time())
    # TODO(stimim): log this by testlog.
    self.goofy.event_log.Log('note',
                             name=note['name'],
                             text=note['text'],
                             timestamp=note['timestamp'],
                             level=note['level'])
    logging.info('Factory note from %s at %s (level=%s): %s',
                 note['name'], note['timestamp'], note['level'],
                 note['text'])
    if note['level'] == 'CRITICAL':
      self.goofy.RunEnqueue(self.goofy.Stop)
    self.goofy.state_instance.DataShelfAppendToList('factory_note', note)
    self.PostEvent(Event(Event.Type.UPDATE_NOTES))

  def ClearNotes(self):
    logging.info('Clearing factory note')
    self.goofy.state_instance.DataShelfDeleteKeys('factory_note', optional=True)
    self.PostEvent(Event(Event.Type.UPDATE_NOTES))

  def LogStackTraces(self):
    """Logs the stack backtraces of all threads."""
    logging.info(debug_utils.DumpStackTracebacks())

  def IsUSBDriveAvailable(self):
    try:
      with factory_bug.MountRemovable(read_only=True):
        return True
    except (IOError, OSError):
      return False

  def SaveLogsToUSB(self, archive_id=None, probe=False):
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
      with factory_bug.MountRemovable() as mount:
        output_file = factory_bug.SaveLogs(mount.mount_point,
                                           archive_id=archive_id,
                                           probe=probe)
        return {'dev': mount.dev,
                'name': os.path.basename(output_file),
                'size': os.path.getsize(output_file),
                'temporary': mount.temporary}
    except Exception:
      logging.exception('Unable to save logs to USB')
      raise

  def PingFactoryServer(self):
    """Pings the factory server.

    Raises:
      Exception if unable to contact factory server.
    """
    server_proxy.GetServerProxy(timeout=PING_SERVER_TIMEOUT_SECS).Ping()

  def ReloadTestList(self):

    def Target():
      if isinstance(self.goofy.test_list, test_list.TestList):
        self.goofy.test_list.ForceReload()
        for f in self.goofy.test_list.Walk():
          f.UpdateState(iterations=f.iterations, retries=f.retries)
      else:
        raise NotImplementedError(
            'Unknown type: %s' % type(self.goofy.test_list))

    return self._InRunQueue(Target)

  def UploadFactoryLogs(self, name, serial, description):
    """Uploads logs to the factory server.

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
      data = file_utils.ReadFile(output_file, encoding=None)
      server_proxy.GetServerProxy(
          timeout=UPLOAD_FACTORY_LOGS_TIMEOUT_SECS).SaveAuxLog(
              os.path.basename(output_file),
              xmlrpc.client.Binary(data))
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
        lambda: self.goofy.Stop(reason='RPC call to stop tests',
                                fail=True),
        timeout_secs=timeout_secs)

  def ClearState(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Stops current tests and clear all test state."""
    def Target():
      self.goofy.Stop(reason='RPC call to clear test state',
                      fail=True)
      self.goofy.ClearState()
    self._InRunQueue(Target, timeout_secs=timeout_secs)

  def RunTest(self, path, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Runs a test."""
    test = self.goofy.test_list.LookupPath(path)
    if not test:
      raise GoofyRPCException('Unknown test path %r' % path)
    test = test.GetTopLevelParentOrGroup()

    self._InRunQueue(lambda: self.goofy.RestartTests(root=test),
                     timeout_secs=timeout_secs)
    return self.goofy.run_id

  def RestartAllTests(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Restarts all tests.

    Args:
      timeout_secs: The duration in seconds after which to abort the call.
    """
    self._InRunQueue(self.goofy.RestartTests, timeout_secs=timeout_secs)
    return self.goofy.run_id

  def ScheduleRestart(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Schedules to restart all tests when current test finished.

    Args:
      timeout_secs: The duration in seconds after which to abort the call.
    """
    self._InRunQueue(self.goofy.ScheduleRestart, timeout_secs=timeout_secs)

  def CancelPendingTests(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Cancels all pending tests."""
    self._InRunQueue(self.goofy.CancelPendingTests, timeout_secs=timeout_secs)

  def Shutdown(self, operation):
    """Starts a shutdown operation through Goofy.

    Args:
      operation: The shutdown operation to run ('halt', 'reboot',
        or 'full_reboot').
    """
    if operation not in ['force_halt', 'halt', 'reboot', 'full_reboot']:
      raise GoofyRPCException('Invalid shutdown operation %r' % operation)
    # No timeout for shutdown as the operation can be delayed for arbitrary
    # duration by the factory test.
    self._InRunQueue(lambda: self.goofy.Shutdown(operation))

  def GetLastShutdownTime(self):
    """Gets last shutdown time detected by Goofy."""
    return self.goofy.last_shutdown_time

  def _GetTests(self):
    """Helper method to get a list of all tests and their states."""
    paths_to_run = set(self.goofy.test_list_iterator.GetPendingTests())
    ret = []
    states = self.goofy.state_instance.GetTestStates()
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

  def WaitForWebSocketUp(self):
    """Checks whether the Goofy web socket is ready for UI connection."""
    self.goofy.web_socket_manager.wait()

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
    for k, v in self.goofy.test_lists.items():
      ret.append(
          dict(id=k, name=v.label,
               enabled=(k == self.goofy.test_list.test_list_id)))

    # Sort by name.
    ret.sort(key=lambda x: x['name'][translation.DEFAULT_LOCALE].lower())

    return ret

  def GetTestList(self):
    """Returns the test list in JSON serializable struct."""
    # goofy.js will need 'path'
    return self.goofy.test_list.ToStruct(extra_fields=['path'])

  def GetTestStateMap(self):
    """Returns the test states in JSON serializable struct."""
    states = self.goofy.state_instance.GetTestStates()
    return {key: state.ToStruct() for key, state in states.items()}

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
        if self.goofy.state_instance.DataShelfGetValue('run_id', optional=True):
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
        ret_val['run_id'] = self.goofy.run_id
        ret_val['scheduled_tests'] = scheduled_tests_status

        if (self.goofy.test_list_iterator.GetPendingTests() or
            any(t['status'] == state.TestState.ACTIVE
                for t in scheduled_tests_status)):
          ret_val['status'] = RunState.RUNNING
        else:
          ret_val['status'] = RunState.FINISHED
      return ret_val

    return self._InRunQueue(lambda: Target(run_id), timeout_secs=timeout_secs)

  def SwitchTestList(self, test_list_id):
    """Switches test lists.

    Args:
      test_list_id: The test list ID.

    Raises:
      TestListError: The test list does not exist.
    """
    # Have goofy throw an error if the test list ID is invalid.
    self.goofy.GetTestList(test_list_id)
    manager.Manager.SetActiveTestList(test_list_id)

    if sys_utils.InChroot():
      raise GoofyRPCException(
          'Cannot switch test in chroot; please manually restart Goofy')

    # Reset goofy_ghost so the test list in overlord is correct.
    process_utils.Spawn(['goofy_ghost', 'reset'], call=True)
    # Restart Goofy and clear state.
    process_utils.Spawn(
        ['nohup ' +
         os.path.join(paths.FACTORY_DIR, 'bin', 'factory_restart') +
         ' -a &'],
        shell=True, check_call=True)
    # Wait for a while.  This process should be killed long before
    # 60 seconds have passed.
    time.sleep(60)
    # This should never be reached, but not much we can do but
    # complain to the caller.
    raise GoofyRPCException('Factory did not restart as expected')

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
    rpc_id = str(uuid.uuid4())
    rpc_event = Event(Event.Type.EXTENSION_RPC, name=name, is_response=False,
                      rpc_id=rpc_id, args=kwargs)
    result = SendEvent(
        rpc_event,
        lambda e: (e.type == rpc_event.type and e.rpc_id == rpc_id and
                   e.is_response),
        timeout)
    if result is None:
      raise type_utils.TimeoutError('Failed calling Extension RPC <%r>' % name)
    return result.args

  def DeviceTakeScreenshot(self, output_file=None,
                           timeout=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Takes screenshots of all the connected ports on the device.

    Args:
      output_file: The output file path to store the captured image file.
          If not given, screenshots are saved to:

            /var/log/screenshot_<TIME>.png

          If a file path is given, screenshots are saved to:

            <file path base>.<file path extension>
    """

    if not output_file:
      output_filename = ('/var/log/screenshot_%s.png' %
                         time.strftime('%Y%m%d-%H%M%S'))
    else:
      output_filename = '%s' % output_file

    tmp_file = self.CallExtension('TakeScreenshot', timeout=timeout)
    image = base64.b64decode(file_utils.ReadFile(tmp_file).split(',')[1])
    file_utils.WriteFile(output_filename, image, encoding=None)
    file_utils.TryUnlink(tmp_file)

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

  def DeviceSetDisplayProperties(self, id_, info,
                                 timeout=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Set the display properties on the device (by calling extension RPC).

    Args:
      id_: The display's unique identifier.
      info: The information about display properties that should be changed.
          See Chrome Extension API chrome.system.display.setDisplayProperties
          for the details.
      timeout: Seconds to wait before RPC timeout.

    Returns:
      `None` if the RPC call succeed; otherwise an string of failure reason
          will be returned.

    Raises:
      type_utils.TimeoutError: if no response until timeout.
    """
    return self.CallExtension(
        'SetDisplayProperties', timeout=timeout, id=id_, info=info)

  def DeviceSetDisplayMirrorMode(self, info,
                                 timeout=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Set the display mirror mode on the device (by calling extension RPC).

    Args:
      info: The mirror mode information to set.
          See Chrome Extension API chrome.system.display.setMirrorMode for
          the details.
      timeout: Seconds to wait before RPC timeout.

    Returns:
      `None` if the RPC call succeed; otherwise an string of failure reason
          will be returned.

    Raises:
      type_utils.TimeoutError: if no response until timeout.
    """
    return self.CallExtension(
        'SetDisplayMirrorMode', timeout=timeout, info=info)

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

  def PostHookEvent(self, event_name, *args, **kargs):
    """Posts an event to Goofy hooks."""
    return self.goofy.hooks.OnEvent(event_name, *args, **kargs)

  def GetTestHistory(self, *test_paths):
    """Returns metadata for all previous (and current) runs of a test."""
    ret = []

    for path in test_paths:
      for f in glob.glob(os.path.join(paths.DATA_TESTS_DIR,
                                      path + '-*',
                                      'testlog.json')):
        try:
          ret.append(yaml.load(open(f)))
        except Exception:
          logging.exception('Unable to load test metadata %s', f)

    ret.sort(key=lambda item: item.get('startTime', None))
    return ret

  def GetTestHistoryEntry(self, path, invocation):
    """Returns metadata and log for one test invocation."""
    test_dir = os.path.join(paths.DATA_TESTS_DIR,
                            '%s-%s' % (path, invocation))

    testlog = json.load(open(os.path.join(test_dir, 'testlog.json')))

    log_file = os.path.join(test_dir, 'log')
    try:
      log = file_utils.ReadFile(log_file)
    except Exception:
      # Oh well
      logging.exception('Unable to read log file %s', log_file)
      log = None

    source_code_file = os.path.join(test_dir, 'source_code')
    try:
      source_code = file_utils.ReadFile(source_code_file)
    except Exception:
      # Oh well
      logging.exception('Unable to read source code %s', source_code_file)
      source_code = None

    return {'testlog': testlog,
            'log': log,
            'source_code': source_code}

  def GetInvocationResolvedArgs(self, invocation_id):
    """Returns the resolved arguments of an invocation.

    Returns:
      A dictionary represents the resolved arguments of an invocation. Returns
      None if the invocation no longer exists.
    """
    invocation = self.goofy.invocations.get(invocation_id)
    return invocation.resolved_dargs if invocation else None

  def GetPluginMenuItems(self):
    """Returns menu items supported by plugins."""
    return self.goofy.plugin_controller.GetPluginMenuItems()

  def OnPluginMenuItemClicked(self, item_id):
    """Called when a plugin menu item is clicked."""
    return self.goofy.plugin_controller.OnMenuItemClicked(item_id)._asdict()

  def GetPluginFrontendConfigs(self):
    """Returns a list of configs of all plugin's UI."""
    return self.goofy.plugin_controller.GetFrontendConfigs()

  def IsPluginEnabled(self, plugin_name):
    """Returns whether a plugin is enabled."""
    return bool(self.goofy.plugin_controller.GetPluginInstance(plugin_name))

  def UploadTemporaryFile(self, content):
    """Save content to a temporary file.

    The caller is responsible of deleting the file after it's used.

    Returns:
      The path of the temporary file.
    """
    path = file_utils.CreateTemporaryFile(prefix='goofy_rpc_temp_')
    file_utils.WriteFile(path, content)
    return path


def main():
  parser = argparse.ArgumentParser(
      description='Sends an RPC to Goofy.')
  parser.add_argument(
      'command',
      help=('The command to run (as a Python expression), e.g.: '
            """RunTest('RunIn.Stress.BadBlocks')"""))
  args = parser.parse_args()

  goofy = state.GetInstance()
  logging.basicConfig(level=logging.INFO)

  if '(' not in args.command:
    parser.error('Expected parentheses in command, e.g.: '
                 """RunTest('RunIn.Stress.BadBlocks')""")

  logging.info('Evaluating expression: %s', args.command)
  ret = eval(args.command, {},  # pylint: disable=eval-used
             {x: getattr(goofy, x)
              for x in GoofyRPC.__dict__ if not x.startswith('_')})
  if ret is not None:
    print(yaml.safe_dump(ret))


if __name__ == '__main__':
  main()
