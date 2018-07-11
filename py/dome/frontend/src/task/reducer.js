// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';
import {combineReducers} from 'redux';

import actionTypes from './actionTypes';
import {TaskStates} from './constants';

const findTaskIndex = (tasks, taskID) => {
  return tasks.findIndex((task) => task.taskID === taskID);
};

const tasksReducer = produce((draft, action) => {
  switch (action.type) {
    case actionTypes.CREATE_TASK:
      draft.push({
        taskID: action.taskID,
        state: TaskStates.WAITING,
        description: action.description,
        method: action.method,
        url: action.url,
        contentType: action.contentType,
        progress: {
          totalFiles: 0,
          totalSize: 0,
          uploadedFiles: 0,
          uploadedSize: 0,
        },
      });
      return;

    case actionTypes.CHANGE_TASK_STATE: {
      const taskIndex = findTaskIndex(draft, action.taskID);
      if (taskIndex > -1) {
        draft[taskIndex].state = action.state;
      }
      return;
    }

    case actionTypes.DISMISS_TASK: {
      const taskIndex = findTaskIndex(draft, action.taskID);
      if (taskIndex > -1) {
        draft.splice(taskIndex, 1);
      }
      return;
    }

    case actionTypes.UPDATE_TASK_PROGRESS: {
      const taskIndex = findTaskIndex(draft, action.taskID);
      if (taskIndex > -1) {
        Object.assign(draft[taskIndex].progress, action.progress);
      }
      return;
    }
  }
}, []);

export default combineReducers({
  tasks: tasksReducer,
});
