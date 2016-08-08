// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'babel-polyfill';
import fetch from 'isomorphic-fetch';

import {BOARD, API_URL} from '../common';
import ActionTypes from '../constants/ActionTypes';
import FormNames from '../constants/FormNames';
import UploadingTaskStates from '../constants/UploadingTaskStates';

function _checkHTTPStatus(response) {
  if (response.status >= 200 && response.status < 300) {
    return response;
  } else {
    var error = new Error(response.statusText);
    error.response = response;
    throw error;
  }
}

function _createAndStartUploadingTask(dispatch, getState, taskDescription,
                                      method, url, formData) {
  var uploadingTasks = getState().getIn(['bundles', 'uploadingTasks']);
  var taskIDs = uploadingTasks.keySeq().toArray().map(x => parseInt(x));

  var taskID = 1;
  if (taskIDs.length > 0) {
    taskID = 1 + Math.max(...taskIDs);
  }

  dispatch(createUploadingTask(taskID, taskDescription));

  return fetch(`${API_URL}${url}`, {
    method: method,
    body: formData
  }).then(_checkHTTPStatus).then(function() {
    dispatch(changeUploadingTaskState(
        taskID, UploadingTaskStates.UPLOADING_TASK_SUCCEEDED
    ));
  }, function(err) {
    // TODO: show an error message box
    dispatch(changeUploadingTaskState(
        taskID, UploadingTaskStates.UPLOADING_TASK_FAILED
    ));
  });
};

const requestBundles = () => ({
  type: ActionTypes.REQUEST_BUNDLES
});

const receiveBundles = bundles => ({
  type: ActionTypes.RECEIVE_BUNDLES,
  bundles
});

const fetchBundles = () => dispatch => {
  // annouce that we're currenty fetching
  dispatch(requestBundles());

  fetch(`${API_URL}/bundles.json`).then(response => {
    response.json().then(json => {
      dispatch(receiveBundles(json));
    }, error => {
      // TODO(littlecvr): better error handling
      console.log('error parsing bundle list response');
      console.log(error);
    });
  }, error => {
    // TODO(littlecvr): better error handling
    console.log('error fetching bundle list');
    console.log(error);
  });
};

const openForm = (formName, payload) => (dispatch, getState) => {
  // The file input does not fire any event when canceled, if the user opened
  // the file dialog and canceled, its onChange handler won't be called, the
  // form won't actually be opened, but its "show" attribute has already been
  // set to true.  Next time the user requests to open the form, the form won't
  // notice the difference and won't open. Therefore, we need to detect such
  // case -- close it first if it's already opened.
  const visible = getState().getIn(['bundles', 'formVisibility', formName]);
  const action = {
    type: ActionTypes.OPEN_FORM,
    formName,
    payload
  };
  if (!visible) {
    dispatch(action);
  }
  else {
    Promise.resolve()
        .then(() => dispatch(closeForm(formName)))
        .then(() => dispatch(action));
  }
};

const closeForm = formName => ({
  type: ActionTypes.CLOSE_FORM,
  formName
});

const createUploadingTask = (taskID, description) => ({
  type: ActionTypes.CREATE_UPLOADING_TASK,
  taskID: String(taskID),
  description
});

const changeUploadingTaskState = (taskID, state) => ({
  type: ActionTypes.CHANGE_UPLOADING_TASK_STATE,
  taskID: String(taskID),
  state
});

const dismissUploadingTask = taskID => ({
  type: ActionTypes.REMOVE_UPLOADING_TASK,
  taskID: String(taskID)
});

const startUploadingBundle = formData => (dispatch, getState) => {
  dispatch(closeForm(FormNames.UPLOADING_BUNDLE_FORM));
  var bundleName = formData.get('name');
  var taskDescription = `Uploading bundle ${bundleName}...`;
  _createAndStartUploadingTask(dispatch, getState, taskDescription,
                               'POST', 'bundles/', formData)
      .then(() => dispatch(fetchBundles()));
};

const startUpdatingResource = formData => (dispatch, getState) => {
  dispatch(closeForm(FormNames.UPDATING_RESOURCE_FORM));
  var bundleName = formData.get('src_bundle_name');
  var taskDescription = `Updating bundle ${bundleName}...`;
  _createAndStartUploadingTask(dispatch, getState, taskDescription,
                               'PUT', `bundles/${bundleName}/resources/`,
                               formData)
      .then(() => dispatch(fetchBundles()));
};

export default {
  fetchBundles,
  openForm,
  closeForm,
  dismissUploadingTask,
  startUploadingBundle,
  startUpdatingResource
};
