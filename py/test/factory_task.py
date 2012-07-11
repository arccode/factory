#!/usr/bin/python
#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.test import factory

_FACTORY_TASK_EVENT_SUBTYPE = 'NextTask'
_TASK_STATE_NOT_STARTED = 1
_TASK_STATE_RUNNING = 2
_TASK_STATE_FINISHED = 3


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
      self._current_task._Start() # pylint: disable=W0212
    else:
      self._ui.Pass()

  def Run(self):
    self.RunNextTask()
    self._ui.Run()


class FactoryTask(object):
  '''Base class for factory tasks.

  Subclass should implement Run(), and possibly Cleanup() if the user
  wants to do soem cleaning jobs.'''
  _execution_status = _TASK_STATE_NOT_STARTED

  def _Start(self):
    assert self._execution_status == _TASK_STATE_NOT_STARTED, \
           'Task %s has been run before.' % self.__class__.__name__
    factory.console.info('%s started.' % self.__class__.__name__)
    self._execution_status = _TASK_STATE_RUNNING
    self.Run()

  def Stop(self):
    assert self._execution_status == _TASK_STATE_RUNNING, \
           'Task %s is not running.' % self.__class__.__name__
    factory.console.info('%s stopped.' % self.__class__.__name__)
    self._execution_status = _TASK_STATE_FINISHED
    self.Cleanup()
    self._task_manager.RunNextTask() # pylint: disable=E1101

  def Run(self):
    raise NotImplementedError

  def Cleanup(self):
    pass
