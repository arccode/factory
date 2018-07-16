// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';
import {combineReducers} from 'redux';
import {ActionType, getType} from 'typesafe-actions';

import {basicActions as actions} from './actions';
import {Task} from './types';

export interface TaskState {
  tasks: Task[];
}

type TaskAction = ActionType<typeof actions>;

const findTaskIndex = (tasks: Task[], taskID: string) => {
  return tasks.findIndex((task) => task.taskID === taskID);
};

const tasksReducer = produce<Task[], TaskAction>(
  (draft: Task[], action: TaskAction) => {
    switch (action.type) {
      case getType(actions.createTaskImpl): {
        const {taskID, description, method, url} = action.payload;
        draft.push({
          taskID,
          state: 'WAITING',
          description,
          method,
          url,
          progress: {
            totalFiles: 0,
            totalSize: 0,
            uploadedFiles: 0,
            uploadedSize: 0,
          },
        });
        return;
      }

      case getType(actions.changeTaskState): {
        const {taskID, state} = action.payload;
        const taskIndex = findTaskIndex(draft, taskID);
        if (taskIndex > -1) {
          draft[taskIndex].state = state;
        }
        return;
      }

      case getType(actions.dismissTaskImpl): {
        const taskIndex = findTaskIndex(draft, action.payload.taskID);
        if (taskIndex > -1) {
          draft.splice(taskIndex, 1);
        }
        return;
      }

      case getType(actions.updateTaskProgress): {
        const {taskID, progress} = action.payload;
        const taskIndex = findTaskIndex(draft, taskID);
        if (taskIndex > -1) {
          Object.assign(draft[taskIndex].progress, progress);
        }
        return;
      }

      default:
        return;
    }
  }, []);

export default combineReducers<TaskState, TaskAction>({
  tasks: tasksReducer,
});
