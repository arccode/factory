// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'babel-polyfill';
import fetch from 'isomorphic-fetch';

import ActionTypes from '../constants/ActionTypes';
import TaskStates from '../constants/TaskStates';

function apiURL(getState) {
  return `/boards/${getState().getIn(['dome', 'currentBoard'])}`;
}

function checkHTTPStatus(response) {
  if (response.status >= 200 && response.status < 300) {
    return response;
  } else {
    var error = new Error(response.statusText);
    error.response = response;
    throw error;
  }
}

function createAndStartTask(
    dispatch, getState, taskDescription, method, url, body,
    contentType = null) {
  var tasks = getState().getIn(['dome', 'tasks']);
  var taskIDs = tasks.keySeq().toArray().map(parseInt);

  var taskID = 1;
  if (taskIDs.length > 0) {
    taskID = 1 + Math.max(...taskIDs);
  }

  dispatch(createTask(taskID, taskDescription));

  var request = {method, body};
  if (contentType !== null) {
    request['headers'] = {'Content-Type': contentType};
  }

  return fetch(`${apiURL(getState)}/${url}/`, request)
    .then(checkHTTPStatus)
    .then(() => {
      dispatch(changeTaskState(taskID, TaskStates.TASK_SUCCEEDED));
    }, error => {
      console.error(error);
      // TODO: show an error message box
      dispatch(changeTaskState(taskID, TaskStates.TASK_FAILED));
    });
}

const addBoard = (name, host, port) => dispatch => {
  var formData = new FormData();
  formData.append('name', name);
  formData.append('host', host);
  formData.append('port', port);
  formData.append('is_existing', true);

  fetch('/boards/', {method: 'POST', body: formData}).then(response => {
    dispatch(fetchBoards());
  }, error => {
    // TODO(littlecvr): better error handling
    console.error('error adding board');
    console.error(error);
  });
};

const createBoard = (name, port, factoryToolkitFile) => dispatch => {
  var formData = new FormData();
  formData.append('name', name);
  formData.append('port', port);
  formData.append('factory_toolkit_file', factoryToolkitFile);

  fetch('/boards/', {method: 'POST', body: formData}).then(response => {
    dispatch(fetchBoards());
  }, error => {
    // TODO(littlecvr): better error handling
    console.error('error creating board');
    console.error(error);
  });
};

const deleteBoard = board => dispatch => {
  fetch(`/boards/${board}/`, {method: 'DELETE'}).then(response => {
    dispatch(fetchBoards());
  }, error => {
    // TODO(littlecvr): better error handling
    console.error('error deleting board');
    console.error(error);
  });
};

const receiveBoards = boards => ({
  type: ActionTypes.RECEIVE_BOARDS,
  boards
});

// TODO(littlecvr): similar to fetchBundles, refactor code if possible
const fetchBoards = () => dispatch => {
  fetch('/boards.json').then(response => {
    response.json().then(json => {
      dispatch(receiveBoards(json));
    }, error => {
      // TODO(littlecvr): better error handling
      console.error('error parsing board list response');
      console.error(error);
    });
  }, error => {
    // TODO(littlecvr): better error handling
    console.error('error fetching board list');
    console.error(error);
  });
};

const switchBoard = nextBoard => (dispatch, getState) => dispatch({
  type: ActionTypes.SWITCH_BOARD,
  prevBoard: getState().getIn(['dome', 'board']),
  nextBoard
});

const switchApp = nextApp => (dispatch, getState) => dispatch({
  type: ActionTypes.SWITCH_APP,
  prevApp: getState().getIn(['dome', 'app']),
  nextApp
});

const openForm = (formName, payload) => (dispatch, getState) => {
  // The file input does not fire any event when canceled, if the user opened
  // the file dialog and canceled, its onChange handler won't be called, the
  // form won't actually be opened, but its "show" attribute has already been
  // set to true.  Next time the user requests to open the form, the form won't
  // notice the difference and won't open. Therefore, we need to detect such
  // case -- close it first if it's already opened.
  const visible = getState().getIn(['dome', 'formVisibility', formName]);
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

const createTask = (taskID, description) => ({
  type: ActionTypes.CREATE_TASK,
  taskID: String(taskID),
  description
});

const changeTaskState = (taskID, state) => ({
  type: ActionTypes.CHANGE_TASK_STATE,
  taskID: String(taskID),
  state
});

const dismissTask = taskID => ({
  type: ActionTypes.REMOVE_TASK,
  taskID: String(taskID)
});

export default {
  apiURL, createAndStartTask,
  addBoard, createBoard, deleteBoard, fetchBoards, switchBoard, switchApp,
  openForm, closeForm,
  dismissTask
};
