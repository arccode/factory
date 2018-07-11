// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';
import uuid from 'uuid/v4';

import error from '@app/error';
import {authorizedAxios} from '@common/utils';

import actionTypes from './actionTypes';
import {TaskStates} from './constants';
import {getAllTasks} from './selectors';

const changeTaskState = (taskID, state) => ({
  type: actionTypes.CHANGE_TASK_STATE,
  taskID,
  state,
});

const updateTaskProgress = (taskID, progress) => ({
  type: actionTypes.UPDATE_TASK_PROGRESS,
  taskID,
  progress,
});

const filterFileFields = (obj) => {
  const result = [];
  for (const [key, value] of Object.entries(obj)) {
    if (value.constructor === Object) {
      result.push(
          ...filterFileFields(value).map((path) => [key, ...path]));
    } else if (value instanceof File) {
      result.push([key]);
    }
  }
  return result;
};

const getIn = (obj, path) => {
  return path.reduce((o, key) => o[key], obj);
};

class TaskQueue {
  constructor() {
    // Objects that cannot be serialized in the store.
    // The taskBodies_ can't be serialized since it might contains File objects.
    this.taskBodies_ = {};
    this.taskResolves_ = {};
  }

  runTask = (description, method, url, body) => {
    return (dispatch, getState) => new Promise((resolve) => {
      const taskID = uuid();
      // if all tasks before succeed, start this task now.
      const startNow = getAllTasks(getState()).every(
          ({state}) => state === TaskStates.SUCCEEDED);

      this.taskBodies_[taskID] = body;
      this.taskResolves_[taskID] = resolve;
      dispatch({
        type: actionTypes.CREATE_TASK,
        taskID,
        description,
        method,
        url,
      });

      if (startNow) {
        dispatch(this.runTask_(taskID));
      }
    });
  }

  dismissTask = (taskID) => (dispatch) => {
    delete this.taskBodies_[taskID];
    delete this.taskResolves_[taskID];
    dispatch({
      type: actionTypes.DISMISS_TASK,
      taskID,
    });
  }

  runTask_ = (taskID) => async (dispatch, getState) => {
    const task = getAllTasks(getState()).find((t) => t.taskID === taskID);
    const body = this.taskBodies_[taskID];

    try {
      const client = authorizedAxios();

      // go through the body and upload files first
      const fileFields = filterFileFields(body);
      // This is only an estimate, since this doesn't include the payload
      // header size for FormData.
      let totalSize = fileFields
          .map((path) => getIn(body, path).size)
          .reduce((a, b) => a + b, 0);

      dispatch(updateTaskProgress(taskID, {
        totalFiles: fileFields.length,
        totalSize,
      }));
      dispatch(changeTaskState(taskID, TaskStates.RUNNING_UPLOAD_FILE));

      let data = body;
      let uploadedFiles = 0;
      let uploadedSize = 0;
      for (const path of fileFields) {
        const file = getIn(body, path);
        const formData = new FormData();
        formData.append('file', file);
        let payloadSize = 0;
        const response = await authorizedAxios().post('/files/', formData, {
          onUploadProgress: (event) => {
            payloadSize = event.total;
            dispatch(updateTaskProgress(taskID, {
              totalSize: totalSize - file.size + payloadSize,
              uploadedSize: uploadedSize + event.loaded,
            }));
          },
        });
        data = produce(data, (draft) => {
          const prefix = [...path];
          const key = prefix.pop();
          const obj = getIn(draft, prefix);
          delete obj[key];
          obj[`${key}Id`] = response.data.id;
        });
        totalSize += payloadSize - file.size;
        uploadedSize += payloadSize;
        uploadedFiles += 1;
        dispatch(updateTaskProgress(taskID, {uploadedFiles}));
      }

      dispatch(changeTaskState(taskID, TaskStates.RUNNING_WAIT_RESPONSE));

      // send the end request
      const endResponse = await client.request({
        url: task.url,
        method: task.method,
        data,
      });

      this.taskResolves_[taskID]({response: endResponse, cancel: false});

      // if all sub-tasks succeeded, mark it as succeeded, and start the next
      // task.
      dispatch(changeTaskState(taskID, TaskStates.SUCCEEDED));

      // find the first waiting task and start it
      const nextTask = getAllTasks(getState()).find(
          ({state}) => state === TaskStates.WAITING);
      if (nextTask) {
        dispatch(this.runTask_(nextTask.taskID));
      }
    } catch (err) {
      // if any sub-task above failed, display the error message
      const {response} = err;
      if (response) {
        const {data} = response;
        const responseText =
            typeof(data) === 'string' ? data : JSON.stringify(data, null, 2);
        dispatch(error.actions.setAndShowErrorDialog(
            `${err.message}\n\n${responseText}`));
      } else {
        // Some unexpected error that is not server-side happened, probably a
        // bug in the task code.
        console.error(err);
        dispatch(error.actions.setAndShowErrorDialog(
            `Unexpected Dome error: ${err}`));
      }
      // mark the task as failed
      dispatch(changeTaskState(taskID, TaskStates.FAILED));
    }
  }

  cancelWaitingTaskAfter = (taskID) => (dispatch, getState) => {
    // TODO(pihsun): probably need a better action name.
    // This action tries to cancel all waiting or failed tasks below and
    // include taskID.
    const tasks = getAllTasks(getState());
    const taskIndex = tasks.findIndex((task) => task.taskID === taskID);
    if (taskIndex > -1) {
      const toCancelTasks =
          tasks.slice(taskIndex).filter(({state}) => (
            state === TaskStates.WAITING || state === TaskStates.FAILED
          )).reverse();

      // cancel all tasks below and include the target task
      for (const {taskID: id} of toCancelTasks) {
        this.taskResolves_[id]({cancel: true});
        dispatch(this.dismissTask(id));
      }
    }
  }
}

const taskQueue = new TaskQueue();
const {runTask, dismissTask, cancelWaitingTaskAfter} = taskQueue;

export {runTask, dismissTask, cancelWaitingTaskAfter};
