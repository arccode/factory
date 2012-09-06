#!/usr/bin/python
#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.test import factory
from cros.factory.test import utils


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
    factory.console.info('%s started.' % self.__class__.__name__)
    self._execution_status = TaskState.RUNNING
    self.Run()

  def _Finish(self, reason):
    """Finishes a task and performs cleanups.

    It is used for Stop, Pass, and Fail operation.

    Args:
      reason: Enum FinishReason.
    """
    assert self._execution_status == TaskState.RUNNING, \
        'Task %s is not running.' % self.__class__.__name__
    factory.console.info('%s %s.' % (self.__class__.__name__, reason))
    self._execution_status = TaskState.FINISHED
    self.Cleanup()

  def Stop(self):
    self._Finish(FinishReason.STOPPED)
    self._task_manager.RunNextTask() # pylint: disable=E1101

  def Pass(self):
    self._Finish(FinishReason.PASSED)
    self._task_manager.RunNextTask() # pylint: disable=E1101

  def Fail(self, error_msg, later=False):
    '''Does Cleanup and fails the task.'''
    self._Finish(FinishReason.FAILED)
    factory.console.info('error: ' + error_msg)
    if later:
      self._ui.FailLater(error_msg) # pylint: disable=E1101
      self._task_manager.RunNextTask() # pylint: disable=E1101
    else:
      self._ui.Fail(error_msg)  # pylint: disable=E1101

  def Run(self):
    raise NotImplementedError

  def Cleanup(self):
    pass
