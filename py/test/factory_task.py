#!/usr/bin/python
#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

from cros.factory.test import test_ui
from cros.factory.test import utils
from cros.factory.utils.process_utils import Spawn


TaskState = utils.Enum(['NOT_STARTED', 'RUNNING', 'FINISHED'])
FinishReason = utils.Enum(['PASSED', 'FAILED', 'STOPPED'])


class FactoryTaskManager(object):
  '''Manages the execution of factory tasks in the context of the given UI.

  Args:
    ui: The test UI object that the manager depends on.
    task_list: A list of factory tasks to be executed.
    update_progress: Optional callback to update progress bar. Passing
       percent progress as parameter.
 '''

  def __init__(self, ui, task_list, update_progress=None):
    self._ui = ui
    self._task_list = task_list
    self._current_task = None
    self._num_tasks = len(task_list)
    self._num_done_tasks = 0
    self._update_progress = update_progress

  def RunNextTask(self):
    if self._current_task:
      self._num_done_tasks += 1
      if self._update_progress:
        self._update_progress(100 * self._num_done_tasks / self._num_tasks)

    if self._task_list:
      self._current_task = self._task_list.pop(0)
      self._current_task._task_manager = self
      self._current_task._ui = self._ui
      self._current_task._Start() # pylint: disable=W0212
    else:
      self._ui.Pass()

  def Run(self):
    self.RunNextTask()
    self._ui.Run()

  def PassCurrentTask(self):
    """Passes current task.

    If _current_task does not exist, just passes the parent test.
    """
    if self._current_task:
      self._current_task.Pass()
    else:
      self._ui.Pass()

  def FailCurrentTask(self, error_msg, later=False):
    """Fails current task with error message.

    Args:
      error_msg: error message.
      later: False to fails the parent test right now; otherwise, fails later.
    """
    if self._current_task:
      self._current_task.Fail(error_msg, later=later)
    else:
      if later:
        self._ui.FailLater(error_msg)
      else:
        self._ui.Fail(error_msg)


class FactoryTask(object):
  '''Base class for factory tasks.

  Subclass should implement Run(), and possibly Cleanup() if the user
  wants to do some cleaning jobs.'''
  _execution_status = TaskState.NOT_STARTED

  def _Start(self):
    assert self._execution_status == TaskState.NOT_STARTED, \
        'Task %s has been run before.' % self.__class__.__name__
    logging.info('Start ' + self.__class__.__name__)
    self._execution_status = TaskState.RUNNING
    self.Run()

  def _Finish(self, reason):
    """Finishes a task and performs cleanups.

    It is used for Stop, Pass, and Fail operation.

    Args:
      reason: Enum FinishReason.
    """
    logging.info('%s %s.', self.__class__.__name__, reason)
    assert self._IsRunning(), (
      'Trying to finish %s which is not running.' % (self.__class__.__name__))
    self._execution_status = TaskState.FINISHED
    self.Cleanup()

  def _IsRunning(self):
    return self._execution_status == TaskState.RUNNING

  def Stop(self):
    self._Finish(FinishReason.STOPPED)
    self._task_manager.RunNextTask() # pylint: disable=E1101

  def Pass(self):
    self._Finish(FinishReason.PASSED)
    self._task_manager.RunNextTask() # pylint: disable=E1101

  def Fail(self, error_msg, later=False):
    '''Fails the task and perform cleanup.

    Args:
      error_msg: Error message.
      later: If True, it allows subsequent tasks to execute and fails its
          parent test case later.
    '''
    logging.warning('%s FAILED. Reason: %s', self.__class__.__name__, error_msg)
    if not self._IsRunning():
      # Prevent multiple call of _Finish().
      return

    self._Finish(FinishReason.FAILED)
    if later:
      self._ui.FailLater(error_msg) # pylint: disable=E1101
      self._task_manager.RunNextTask() # pylint: disable=E1101
    else:
      self._ui.Fail(error_msg)  # pylint: disable=E1101

  def Run(self):
    raise NotImplementedError

  def Cleanup(self):
    pass

  def RunCommand(self, command, fail_message=None, fail_later=True):
    """Executes a command and checks if it runs successfully.

    Args:
      command: command list.
      fail_message: optional string. If assigned and the command's return code
          is nonzero, Fail will be called with fail_message.
      fail_later: True to fail the parent test case later when the command
          fails to execute.

    Returns:
      True if command executes successfully; otherwise, False.
    """
    logging.info('RunCommand: ' + ' '.join(command))
    p = Spawn(command, call=True, ignore_stdout=True, read_stderr=True)
    if p.returncode != 0 and fail_message:
      self.Fail(
        '%s\nFailed running: %s\nSTDERR: %s' % (
          fail_message, ' '.join(command), p.stderr_data),
        later=fail_later)
    return p.returncode == 0


class InteractiveFactoryTask(FactoryTask):  # pylint: disable=W0223
  """A FactoryTask class for interactive tasks.

  It provides common key binding methods for interactive tasks.

  Args:
    ui: UI object.
  """
  def __init__(self, ui):
    super(InteractiveFactoryTask, self).__init__()
    self._ui = ui

  def BindPassFailKeys(self, pass_key=True, fail_later=True):
    """Binds pass and/or fail keys.

    If pass_key is True, binds Enter key to pass the task; otherwise, pressing
    Enter triggers nothing.
    Always binds Esc key to fail the task.

    Args:
      pass_key: True to bind Enter key to pass the task.
      fail_later: True to fail later when Esc is pressed.
    """
    self._ui.BindKey(test_ui.ENTER_KEY,
                     lambda _: self.Pass() if pass_key else None)

    self._ui.BindKey(test_ui.ESCAPE_KEY,
                     lambda _: self.Fail(
        '%s failed by operator.' % self.__class__.__name__, later=fail_later))

  def BindDigitKeys(self, pass_digit, fail_later=True):
    """Binds the pass_digit to pass the task and other digits to fail it.

    To prevent operator's cheating by key swiping, we bind the remaining digit
    keys to fail the task.

    Arg:
      pass_digit: a digit [0, 9] to pass the task.
      fail_later: True to fail the parent test case later when the wrong key is
          pressed.
    """
    for i in xrange(0, 10):
      if i == pass_digit:
        self._ui.BindKey(str(i), lambda _: self.Pass())
      else:
        self._ui.BindKey(str(i), lambda _: self.Fail('Wrong key pressed.',
                                                     later=fail_later))

  def UnbindDigitKeys(self):
    """Unbinds all digit keys."""
    for i in xrange(0, 10):
      self._ui.UnbindKey(str(i))
