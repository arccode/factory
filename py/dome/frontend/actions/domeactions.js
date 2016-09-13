// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'babel-polyfill';
import fetch from 'isomorphic-fetch';

import ActionTypes from '../constants/ActionTypes';
import TaskStates from '../constants/TaskStates';

// Task bodies cannot be put in the state because they may contain file objects
// which are not serializable.
var _taskBodies = {};
var _taskOnFinishes = {};

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

const changeTaskState = (taskID, state) => ({
  type: ActionTypes.CHANGE_TASK_STATE,
  taskID,
  state
});

const createTask = (description, method, url, body, onFinish = null,
                    contentType = null) => (
  (dispatch, getState) => {
    var tasks = getState().getIn(['dome', 'tasks']);
    var taskIDs = tasks.keySeq().sort().toArray();

    var taskID = String(1);
    if (taskIDs.length > 0) {
      taskID = String(1 + Math.max(...taskIDs.map(x => parseInt(x))));
    }

    _taskBodies[taskID] = body;
    _taskOnFinishes[taskID] = onFinish;
    dispatch({
      type: ActionTypes.CREATE_TASK,
      taskID,
      description,
      method,
      url,
      contentType
    });

    // if all tasks except this one succeeded (or failed), start this task now
    var startNow = true;
    for (const id of taskIDs) {
      let s = tasks.getIn([id, 'state']);
      if (id != taskID &&
          (s == TaskStates.RUNNING || s == TaskStates.WAITING)) {
        startNow = false;
        break;
      }
    }
    if (startNow) {
      dispatch(startTask(taskID));
    }
  }
);

const removeTask = taskID => dispatch => {
  taskID = String(taskID);  // make sure taskID is always a string
  delete _taskBodies[taskID];
  delete _taskOnFinishes[taskID];
  dispatch({
    type: ActionTypes.REMOVE_TASK,
    taskID
  });
};

const startTask = taskID => (dispatch, getState) => {
  taskID = String(taskID);  // make sure taskID is always a string
  var task = getState().getIn(['dome', 'tasks', taskID]);

  dispatch(changeTaskState(taskID, TaskStates.RUNNING));

  var request = {method: task.get('method'), body: _taskBodies[taskID]};
  if (task.get('contentType') !== null) {
    request['headers'] = {'Content-Type': task.get('contentType')};
  }

  return fetch(`${apiURL(getState)}/${task.get('url')}/`, request)
    .then(checkHTTPStatus)
    .then(_taskOnFinishes[taskID])
    .then(
      () => {
        dispatch(changeTaskState(taskID, TaskStates.SUCCEEDED));

        // find next queued task and start it
        var tasks = getState().getIn(['dome', 'tasks']);
        var taskIDs = tasks.keySeq().sort().toArray();
        var nextIndex = 1 + taskIDs.indexOf(taskID);
        if (nextIndex > 0 && nextIndex < taskIDs.length) {
          var nextID = taskIDs[nextIndex];
          dispatch(startTask(nextID));
        }
      },
      error => {
        console.error(error);
        // TODO: show an error message box
        dispatch(changeTaskState(taskID, TaskStates.FAILED));
      }
    );
};

const cancelTaskAndItsDependencies = taskID => (dispatch, getState) => {
  // TODO(littlecvr): probably need a better action name or better description.
  //                  This would likely to be confused with removeTask().
  // This action tries to cancel all waiting tasks below and include taskID.
  taskID = String(taskID);  // make sure taskID is always a string
  var tasks = getState().getIn(['dome', 'tasks']);
  var taskIDs = tasks.keySeq().sort().toArray();
  var index = taskIDs.indexOf(taskID);

  // cancel all tasks below and include the target task
  if (index >= 0) {
    for (let i = taskIDs.length - 1; i >= index; --i) {
      let state = tasks.getIn([taskIDs[i], 'state']);
      if (state == TaskStates.WAITING || state == TaskStates.FAILED) {
        dispatch(removeTask(taskIDs[i]));
      }
    }
  }
};

export default {
  apiURL,
  addBoard, createBoard, deleteBoard, fetchBoards, switchBoard,
  switchApp,
  openForm, closeForm,
  createTask, removeTask, cancelTaskAndItsDependencies
};
