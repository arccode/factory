// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';
import {createAction} from 'typesafe-actions';
import uuid from 'uuid/v4';

import error from '@app/error';
import {Dispatch, RootState} from '@app/types';
import {authorizedAxios} from '@common/utils';

import {getAllTasks} from './selectors';
import {TaskProgress, TaskResult, TaskState} from './types';

const createTaskImpl = createAction('CREATE_TASK', (resolve) =>
  (taskID: string, description: string, method: string, url: string) =>
    resolve({taskID, description, method, url}));

const dismissTaskImpl = createAction('DISMISS_TASK', (resolve) =>
  (taskID: string) => resolve({taskID}));

export const changeTaskState = createAction('CHANGE_TASK_STATE', (resolve) =>
  (taskID: string, state: TaskState) => resolve({taskID, state}));

export const updateTaskProgress = createAction('UPDATE_TASK_PROGRESS',
  (resolve) => (taskID: string, progress: Partial<TaskProgress>) =>
    resolve({taskID, progress}));

export const basicActions = {
  createTaskImpl,
  dismissTaskImpl,
  changeTaskState,
  updateTaskProgress,
};

const filterFileFields = (obj: any): string[][] => {
  const result: string[][] = [];
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

const getIn = (obj: any, path: string[]): any => {
  return path.reduce((o, key) => o[key], obj);
};

// Objects that cannot be serialized in the store.
// The taskBodies can't be serialized since it might contains File objects.
const taskBodies: {[id: string]: any} = {};
const taskResolves: {[id: string]: (result: TaskResult) => void} = {};

export const runTask =
  <T>(description: string, method: string, url: string, body: any) =>
    (dispatch: Dispatch, getState: () => RootState): Promise<TaskResult<T>> =>
      new Promise((resolve) => {
        const taskID = uuid();
        // if all tasks before succeed, start this task now.
        const startNow =
          getAllTasks(getState()).every(({state}) => state === 'SUCCEEDED');

        taskBodies[taskID] = body;
        taskResolves[taskID] = resolve;
        dispatch(createTaskImpl(taskID, description, method, url));

        if (startNow) {
          dispatch(runTaskImpl(taskID));
        }
      });

export const dismissTask = (taskID: string) => (dispatch: Dispatch) => {
  delete taskBodies[taskID];
  delete taskResolves[taskID];
  dispatch(dismissTaskImpl(taskID));
};

export const cancelWaitingTaskAfter = (taskID: string) =>
  (dispatch: Dispatch, getState: () => RootState) => {
    // TODO(pihsun): probably need a better action name.
    // This action tries to cancel all waiting or failed tasks below and
    // include taskID.
    const tasks = getAllTasks(getState());
    const taskIndex = tasks.findIndex((task) => task.taskID === taskID);
    if (taskIndex > -1) {
      const toCancelTasks =
        tasks.slice(taskIndex).filter(({state}) => (
          state === 'WAITING' || state === 'FAILED'
        )).reverse();

      // cancel all tasks below and include the target task
      for (const {taskID: id} of toCancelTasks) {
        taskResolves[id]({cancel: true});
        dispatch(dismissTask(id));
      }
    }
  };

const runTaskImpl = (taskID: string) =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    const task = getAllTasks(getState()).find((t) => t.taskID === taskID);
    if (!task) {
      console.warn(`Get runTaskImpl with non-exist taskID: ${taskID}`);
      return;
    }
    const body = taskBodies[taskID];

    try {
      const client = authorizedAxios();

      // go through the body and upload files first
      const fileFields = filterFileFields(body);
      // This is only an estimate, since this doesn't include the payload
      // header size for FormData.
      let totalSize = fileFields
        .map((path) => (getIn(body, path) as File).size)
        .reduce((a, b) => a + b, 0);

      dispatch(updateTaskProgress(taskID, {
        totalFiles: fileFields.length,
        totalSize,
      }));
      dispatch(changeTaskState(taskID, 'RUNNING_UPLOAD_FILE'));

      let data = body;
      let uploadedFiles = 0;
      let uploadedSize = 0;
      for (const path of fileFields) {
        const file: File = getIn(body, path);
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
          const key = prefix.pop() as string;
          const obj = getIn(draft, prefix);
          delete obj[key];
          obj[`${key}Id`] = response.data.id;
        });
        totalSize += payloadSize - file.size;
        uploadedSize += payloadSize;
        uploadedFiles += 1;
        dispatch(updateTaskProgress(taskID, {uploadedFiles}));
      }

      dispatch(changeTaskState(taskID, 'RUNNING_WAIT_RESPONSE'));

      // send the end request
      const endResponse = await client.request({
        url: task.url,
        method: task.method,
        data,
      });

      taskResolves[taskID]({response: endResponse, cancel: false});

      // if all sub-tasks succeeded, mark it as succeeded, and start the next
      // task.
      dispatch(changeTaskState(taskID, 'SUCCEEDED'));

      // find the first waiting task and start it
      const nextTask =
        getAllTasks(getState()).find(({state}) => state === 'WAITING');
      if (nextTask) {
        dispatch(runTaskImpl(nextTask.taskID));
      }
    } catch (err) {
      // if any sub-task above failed, display the error message
      const {response} = err;
      if (response) {
        const {data} = response;
        const responseText =
          typeof (data) === 'string' ? data : JSON.stringify(data, null, 2);
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
      dispatch(changeTaskState(taskID, 'FAILED'));
    }
  };
