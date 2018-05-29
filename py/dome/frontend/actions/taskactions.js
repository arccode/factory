// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';
import uuid from 'uuid/v4';

import ActionTypes from '../constants/ActionTypes';
import TaskStates from '../constants/TaskStates';

import DomeActions from './domeactions';

const changeTaskState = (taskID, state) => ({
  type: ActionTypes.CHANGE_TASK_STATE,
  taskID,
  state,
});

const checkHTTPStatus = (response) => {
  if (!response.ok) {
    const error = new Error(response.statusText);
    error.response = response;
    throw error;
  }
};

const recursivelyUploadFileFields = async (data) => {
  if (data instanceof Immutable.List) {
    const result = [];
    for (const value of data) {
      result.push(await recursivelyUploadFileFields(value));
    }
    return Immutable.List(result);
  } else if (data instanceof Immutable.Map) {
    const result = {};
    for (const [key, value] of data) {
      if (value instanceof File) {
        const formData = new FormData();
        formData.append('file', data.get(key));
        // TODO(pihsun): We can do parallel uploading by using Promise.all if
        // needed.
        const response = await DomeActions.authorizedFetch('/files/', {
          method: 'POST',
          body: formData,
        });
        checkHTTPStatus(response);
        const json = await response.json();
        // replace `${key}` with `${key}Id` and set it to the file ID
        result[`${key}Id`] = json.id;
      } else {
        result[key] = await recursivelyUploadFileFields(value);
      }
    }
    return Immutable.Map(result);
  } else {
    return data;
  }
};

class TaskQueue {
  constructor() {
    // Objects that cannot be serialized in the store.
    this._taskBodies = {};
    this._taskResolves = {};
  }

  runTask = (description, method, url, body) => {
    return (dispatch, getState) => new Promise((resolve) => {
      const getTaskState = () => getState().get('task');

      const taskID = uuid();
      // if all tasks before succeed, start this task now.
      const startNow = getTaskState().get('tasks').every(
          (task) => task.get('state') === TaskStates.SUCCEEDED);

      this._taskBodies[taskID] = Immutable.fromJS(body);
      this._taskResolves[taskID] = resolve;
      dispatch({
        type: ActionTypes.CREATE_TASK,
        taskID,
        description,
        method,
        url,
      });

      if (startNow) {
        dispatch(this._runTask(taskID));
      }
    });
  }

  dismissTask = (taskID) => (dispatch) => {
    delete this._taskBodies[taskID];
    delete this._taskResolves[taskID];
    dispatch({
      type: ActionTypes.DISMISS_TASK,
      taskID,
    });
  };

  _runTask = (taskID) => async (dispatch, getState) => {
    const getTaskState = () => getState().get('task');

    dispatch(changeTaskState(taskID, TaskStates.RUNNING));

    const task = getTaskState().getIn(['tasks', taskID]);
    let body = this._taskBodies[taskID];

    try {
      // go through the body and upload files first
      body = await recursivelyUploadFileFields(body);

      // send the end request
      const request = {
        method: task.get('method'),
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      };
      const response =
          await DomeActions.authorizedFetch(task.get('url'), request);
      checkHTTPStatus(response);
      this._taskResolves[taskID]({response, cancel: false});

      // if all sub-tasks succeeded, mark it as succeeded, and start the next
      // task.
      dispatch(changeTaskState(taskID, TaskStates.SUCCEEDED));

      // find the first waiting task and start it
      const nextTaskEntry = getTaskState().get('tasks').findEntry(
          (task) => task.get('state') === TaskStates.WAITING);
      if (nextTaskEntry) {
        dispatch(this._runTask(nextTaskEntry[0]));
      }
    } catch (error) {
      // if any sub-task above failed, display the error message
      const {response} = error;
      if (response) {
        let responseText;
        if (response.headers.get('Content-Type') == 'application/json') {
          responseText = JSON.stringify(await response.json());
        } else {
          responseText = await response.text();
        }
        dispatch(DomeActions.setAndShowErrorDialog(
            `${error.message}\n\n${responseText}`));
      } else {
        // Some unexpected error that is not server-side happened, probably a
        // bug in the task code.
        console.error(error);
        dispatch(DomeActions.setAndShowErrorDialog(
            `Unexpected Dome error: ${error}`));
      }
      // mark the task as failed
      dispatch(changeTaskState(taskID, TaskStates.FAILED));
    }
  };

  cancelWaitingTaskAfter = (taskID) => (dispatch, getState) => {
    // TODO(pihsun): probably need a better action name.
    // This action tries to cancel all waiting or failed tasks below and
    // include taskID.
    const getTaskState = () => getState().get('task');

    const tasks = getTaskState().get('tasks');
    const toCancelTasks =
        tasks.skipUntil((unusedTask, id) => id === taskID).filter((task) => {
          const state = task.get('state');
          return state === TaskStates.WAITING || state === TaskStates.FAILED;
        }).keySeq().reverse();

    // cancel all tasks below and include the target task
    for (const taskID of toCancelTasks) {
      this._taskResolves[taskID]({cancel: true});
      dispatch(this.dismissTask(taskID));
    }
  };
};

const taskQueue = new TaskQueue();
const {runTask, dismissTask, cancelWaitingTaskAfter} = taskQueue;

export default {runTask, dismissTask, cancelWaitingTaskAfter};
