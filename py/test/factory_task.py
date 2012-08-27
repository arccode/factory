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


class FactoryTaskManager(object):
  '''Manages the execution of factory tasks in the context of the given UI.

  Args:
    ui: The test UI object that the manager depends on.
    task_list: A list of factory tasks to be executed.'''

  def __init__(self, ui, task_list):
    self._ui = ui
    self._task_list = task_list
    self._current_task = None

  def RunNextTask(self):
    if self._current_task:
      self._task_list.remove(self._current_task)

    if self._task_list:
      self._current_task = self._task_list[0]
      self._current_task._task_manager = self
      self._current_task._ui = self._ui
      self._current_task._Start() # pylint: disable=W0212
    else:
      self._ui.Pass()

  def Run(self):
    self.RunNextTask()
    self._ui.Run()


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

  def Stop(self):
    assert self._execution_status == TaskState.RUNNING, \
        'Task %s is not running.' % self.__class__.__name__
    factory.console.info('%s stopped.' % self.__class__.__name__)
    self._execution_status = TaskState.FINISHED
    self.Cleanup()
    self._task_manager.RunNextTask() # pylint: disable=E1101

  def Fail(self, error_msg, later=False):
    '''Does Cleanup and fails the task.'''
    assert self._execution_status == TaskState.RUNNING, \
        'Task %s is not running.' % self.__class__.__name__
    factory.console.info('%s failed: %s' % (self.__class__.__name__, error_msg))
    self._execution_status = TaskState.FINISHED
    self.Cleanup()
    if later:
      self._ui.FailLater(error_msg) # pylint: disable=E1101
    else:
      self._ui.Fail(error_msg)  # pylint: disable=E1101

  def Run(self):
    raise NotImplementedError

  def Cleanup(self):
    pass
