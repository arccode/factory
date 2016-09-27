// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import ActionTypes from '../constants/ActionTypes';
import TaskStates from '../constants/TaskStates';

// Task bodies cannot be put in the state because they may contain file objects
// which are not serializable.
var _taskBodies = {};
var _taskOnFinishes = {};
var _taskOnCancels = {};

function checkHTTPStatus(response) {
  if (response.status >= 200 && response.status < 300) {
    return response;
  } else {
    var error = new Error(response.statusText);
    error.response = response;
    throw error;
  }
}

function buildOnCancel(dispatch, getState) {
  var boardsSnapshot = getState().getIn(['dome', 'boards']).toList().toJS();
  return () => dispatch(receiveBoards(boardsSnapshot));
}

const createBoard = name => dispatch => {
  var formData = new FormData();
  formData.append('name', name);

  var description = `Create board "${name}"`;
  dispatch(createTask(
      description, 'POST', 'boards', formData, () => dispatch(fetchBoards()),
  ));
};

const updateBoard = (name, settings = {}) => (dispatch, getState) => {
  let formData = new FormData();
  formData.append('name', name);

  [
    // TODO(littlecvr): should be CamelCased
    'umpire_enabled',
    'umpire_add_existing_one',
    'umpire_host',
    'umpire_port',
    'umpire_factory_toolkit_file'
  ].forEach(key => {
    if (key in settings) {
      formData.append(key, settings[key]);
    }
  });

  // taking snapshot must be earlier than optmistic update
  let onCancel = buildOnCancel(dispatch, getState);

  // optimistic update
  dispatch({
    type: ActionTypes.UPDATE_BOARD,
    board: Object.assign({
      name,
      // TODO(littlecvr): should be CamelCased
      umpire_ready: false,
    }, settings)
  });

  let onFinish = () => dispatch({
    type: ActionTypes.UPDATE_BOARD,
    board: {
      name,
      umpire_ready: settings['umpire_enabled'] === true ? true : false
    }
  });

  var description = `Update board "${name}"`;
  dispatch(createTask(
      description, 'PUT', `boards/${name}`, formData, onFinish, onCancel
  ));
};

const deleteBoard = name => dispatch => {
  var description = `Delete board "${name}"`;
  dispatch(createTask(
      description, 'DELETE', `boards/${name}`, new FormData(),
      () => dispatch(fetchBoards()),
  ));
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

const createTask = (description, method, url, body,
                    onFinish = null, onCancel = null, contentType = null) => (
  (dispatch, getState) => {
    var tasks = getState().getIn(['dome', 'tasks']);
    var taskIDs = tasks.keySeq().sort().toArray();

    var taskID = String(1);
    if (taskIDs.length > 0) {
      taskID = String(1 + Math.max(...taskIDs.map(x => parseInt(x))));
    }

    _taskBodies[taskID] = body;
    _taskOnFinishes[taskID] = onFinish;
    _taskOnCancels[taskID] = onCancel;
    dispatch({
      type: ActionTypes.CREATE_TASK,
      taskID,
      description,
      method,
      url,
      contentType
    });

    // if all tasks except this one succeeded, start this task now
    var startNow = true;
    for (const id of taskIDs) {
      let s = tasks.getIn([id, 'state']);
      if (id != taskID && s != TaskStates.SUCCEEDED) {
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
  delete _taskOnCancels[taskID];
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

  return fetch(`${task.get('url')}/`, request)
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
        if (_taskOnCancels[taskIDs[i]]) {
          _taskOnCancels[taskIDs[i]]();
        }
        dispatch(removeTask(taskIDs[i]));
      }
    }
  }
};

export default {
  createBoard, updateBoard, deleteBoard, fetchBoards, switchBoard,
  switchApp,
  openForm, closeForm,
  createTask, removeTask, cancelTaskAndItsDependencies
};
