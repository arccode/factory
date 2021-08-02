# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module for base test case for pytests."""

import collections
import sys
import threading
import time
import unittest

from cros.factory.test import event as test_event
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test import session
from cros.factory.test.utils import pytest_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


class TaskEndException(Exception):
  """The exception to end a task."""


_Task = collections.namedtuple('Task', ['name', 'run'])


class TestCase(unittest.TestCase):
  """A unittest.TestCase, with task system and optional UI.

  Test should override runTest to do testing in background.
  """

  ui_class = test_ui.StandardUI

  def __init__(self, methodName='runTest'):
    super(TestCase, self).__init__(methodName='_RunTest')
    self.event_loop = None

    self.__method_name = methodName
    self.__task_end_event = threading.Event()
    self.__task_failed = False
    self.__tasks = []

    self.__exceptions = []
    self.__exceptions_lock = threading.Lock()

  def PassTask(self):
    """Pass current task.

    Should only be called in the event callbacks or primary background test
    thread.
    """
    raise TaskEndException

  def FailTask(self, msg):
    """Fail current task.

    Should only be called in the event callbacks or primary background test
    thread.
    """
    raise type_utils.TestFailure(msg)

  def __WaitTaskEnd(self, timeout):
    if self.__task_end_event.wait(timeout=timeout):
      raise TaskEndException

  def WaitTaskEnd(self):
    """Wait for either TaskPass or TaskFail is called.

    Task that need to wait for frontend events to judge pass / fail should call
    this at the end of the task.
    """
    self.__WaitTaskEnd(None)

  def Sleep(self, secs):
    """Sleep for secs seconds, but ends early if test failed.

    An exception would be raised if TaskPass or TaskFail is called before
    timeout. This makes the function acts like time.sleep that ends early when
    timeout is given.

    Args:
      secs: Seconds to sleep, would return or raise immediately if value <= 0.

    Raises:
      TaskEndException if the task end before secs seconds.
    """
    self.__WaitTaskEnd(secs)

  def AddTask(self, task, *task_args, **task_kwargs):
    """Add a task to the test.

    Extra arguments would be passed to the task function.

    Args:
      task: A task function.
      task_args, task_kwargs: Arguments for the task function.
    """
    name = task.__name__
    run = lambda: task(*task_args, **task_kwargs)

    self.__tasks.append(_Task(name=name, run=run))

  @type_utils.LazyProperty
  def ui(self):
    """The UI of the test.

    This is initialized on first use, so task can be used even for tests that
    want to use default UI.
    """
    ui = self.ui_class(event_loop=self.event_loop)
    ui.SetupStaticFiles()
    return ui


  def run(self, result=None):
    # We override TestCase.run and do initialize of ui objects here, since the
    # session.GetCurrentTestFilePath() used by UI is not set when __init__ is
    # called (It's set by invocation after the TestCase instance is created),
    # and initialize using setUp() means that all pytests inheriting this need
    # to remember calling super(..., self).setUp(), which is a lot of
    # boilerplate code and easy to forget.
    self.event_loop = test_ui.EventLoop(self.__HandleException)

    super(TestCase, self).run(result=result)

  def _RunTest(self):
    """The main test procedure that would be run by unittest."""
    thread = process_utils.StartDaemonThread(target=self.__RunTasks)
    try:
      end_event = self.event_loop.Run()
      if end_event.status == state.TestState.FAILED:
        exc_idx = getattr(end_event, 'exception_index', None)
        if exc_idx is None:
          raise type_utils.TestFailure(getattr(end_event, 'error_msg', None))
        # pylint: disable=invalid-sequence-index
        raise pytest_utils.IndirectException(*self.__exceptions[exc_idx])
    finally:
      # Ideally, the background would be the one calling FailTask / PassTask,
      # or would be waiting in WaitTaskEnd when an exception is thrown, so the
      # thread should exit cleanly shortly after the event loop ends.
      #
      # If after 1 second, the thread is alive, most likely that the thread is
      # in some blocking operation and someone else fails the test, then we
      # assume that we don't care about the thread not cleanly stopped.
      #
      # In this case, we try to raise an exception in the thread (To possibly
      # trigger some cleanup process in finally block or context manager),
      # wait for 3 more seconds for (possible) cleanup to run, and just ignore
      # the thread. (Even if the thread doesn't terminate in time.)
      thread.join(1)
      if thread.isAlive():
        try:
          sync_utils.TryRaiseExceptionInThread(thread.ident, TaskEndException)
        except ValueError:
          # The thread is no longer valid, ignore it
          pass
        else:
          thread.join(3)

  def __RunTasks(self):
    """Run the tasks in background daemon thread."""
    # Set the sleep function for various polling methods in sync_utils to
    # self.WaitTaskEnd, so tests using methods like sync_utils.WaitFor would
    # still be ended early when the test ends.
    with sync_utils.WithPollingSleepFunction(self.Sleep):
      # Add runTest as the only task if there's none.
      if not self.__tasks:
        self.AddTask(getattr(self, self.__method_name))

      for task in self.__tasks:
        self.__task_end_event.clear()
        try:
          self.__SetupGoofyJSEvents()
          try:
            task.run()
          finally:
            self.__task_end_event.set()
            self.event_loop.ClearHandlers()
            self.ui.UnbindAllKeys()
        except Exception:
          self.__HandleException()
          if self.__task_failed:
            return

      self.event_loop.PostNewEvent(
          test_event.Event.Type.END_EVENT_LOOP, status=state.TestState.PASSED)

  def __HandleException(self):
    """Handle exception in event handlers or tasks.

    This should be called in the except clause, and is also called by the event
    loop in the main thread.
    """
    unused_exc_type, exception, tb = sys.exc_info()
    assert exception is not None, 'Not handling an exception'

    if not isinstance(exception, TaskEndException):
      with self.__exceptions_lock:
        exc_idx = len(self.__exceptions)
        self.__exceptions.append((exception, tb))

      self.event_loop.PostNewEvent(
          test_event.Event.Type.END_EVENT_LOOP,
          status=state.TestState.FAILED,
          exception_index=exc_idx)
      self.__task_failed = True
    self.__task_end_event.set()

  def __SetupGoofyJSEvents(self):
    """Setup handlers for events from frontend JavaScript."""

    def TestResultHandler(event):
      status = event.data.get('status')
      if status == state.TestState.PASSED:
        self.PassTask()
      elif status == state.TestState.FAILED:
        self.FailTask(event.data.get('error_msg', ''))
      else:
        raise ValueError('Unexpected status in event %r' % event)

    # pylint: disable=unused-argument
    def ScreenshotHandler(event):
      output_filename = ('/var/factory/log/screenshots/screenshot_%s.png' %
                         time.strftime('%Y%m%d-%H%M%S'))
      state.GetInstance().DeviceTakeScreenshot(output_filename)
      session.console.info('Take a screenshot of Goofy page and store as %s',
                           output_filename)

    file_utils.TryMakeDirs('/var/factory/log/screenshots')
    self.event_loop.AddEventHandler('goofy_ui_task_end', TestResultHandler)
    self.event_loop.AddEventHandler('goofy_ui_screenshot', ScreenshotHandler)
