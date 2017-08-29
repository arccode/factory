// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import deepcopy from 'deepcopy';

import ActionTypes from '../constants/ActionTypes';
import TaskStates from '../constants/TaskStates';

// Objects that cannot be serialized in the store.
// TODO(littlecvr): probably should move this into a TaskQueue class.
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
  var projectsSnapshot = getState().getIn(['dome', 'projects']).toList().toJS();
  return () => dispatch(receiveProjects(projectsSnapshot));
}

function recursivelyUploadFileFields(data, queue = null) {
  if (queue === null) {
    // create a queue one if none is given
    queue = Promise.resolve();
  }

  for (let key in data) {
    if (!data.hasOwnProperty(key)) {
      continue;  // only care about own properties
    }
    if (data[key] instanceof File) {
      let formData = new FormData();
      formData.append('file', data[key]);
      queue = queue
          .then(() => fetch('/files/', {method: 'POST', body: formData}))
          .then(checkHTTPStatus)
          .then(response => response.json())
          .then(json => {
            // replace `${key}` with `${key}Id` and set it to the file ID
            delete data[key];
            data[`${key}Id`] = json.id;
          });
    } else if (data[key] instanceof Object) {
      queue = recursivelyUploadFileFields(data[key], queue);
    }
  }

  return queue;
}

const recieveConfig = config => ({
  type: ActionTypes.RECIEVE_CONFIG,
  config
});

const initializeConfig = () => dispatch => {
  var body = {};
  dispatch(updateConfig(body));
}

const fetchConfig = () => dispatch => {
  fetch('/config/0').then(response => {
    response.json().then(json => {
      dispatch(recieveConfig(json));
    }, error => {
      console.error('error parsing config response');
      console.error(error);
    });
  }, error => {
    console.error('error fetching config');
    console.error(error);
  }).then( () => {
    dispatch({type: ActionTypes.FINISH_UPDATING_CONFIG});
  });
};

const updateConfig = body => (dispatch, getState) => {
  dispatch({type: ActionTypes.START_UPDATING_CONFIG});
  var description = 'Update config';
  dispatch(createTask(
      description, 'PUT', '/config/0', body,
      {onFinish: () => dispatch(fetchConfig())}
  ));
};

const enableTFTP = () => dispatch => {
  var body = {
    tftp_enabled: true
  };
  dispatch(updateConfig(body));
};

const disableTFTP = () => dispatch => {
  var body = {
    tftp_enabled: false
  };
  dispatch(updateConfig(body));
};

const setError = message => ({
  type: ActionTypes.SET_ERROR_MESSAGE,
  message
});

const showErrorDialog = () => ({
  type: ActionTypes.SHOW_ERROR_DIALOG
});

const hideErrorDialog = () => ({
  type: ActionTypes.HIDE_ERROR_DIALOG
});

// convenient wrapper of setError() + showErrorDialog()
const setAndShowErrorDialog = message => dispatch => {
  dispatch(setError(message));
  dispatch(showErrorDialog());
};

const createProject = name => dispatch => {
  var description = `Create project "${name}"`;
  dispatch(createTask(
      description, 'POST', '/projects', {name},
      {onFinish: () => dispatch(fetchProjects())}
  ));
};

const updateProject = (name, settings = {}) => (dispatch, getState) => {
  let body = {name};
  [
    'umpireEnabled',
    'umpireAddExistingOne',
    'umpireHost',
    'umpirePort',
    'netbootBundle'
  ].forEach(key => {
    if (key in settings) {
      body[key] = settings[key];
    }
  });

  // taking snapshot must be earlier than optmistic update
  let onCancel = buildOnCancel(dispatch, getState);

  // optimistic update
  dispatch({
    type: ActionTypes.UPDATE_PROJECT,
    project: Object.assign({
      name,
      umpireReady: false,
    }, settings)
  });

  let onFinish = () => dispatch({
    type: ActionTypes.UPDATE_PROJECT,
    project: {
      name,
      umpireReady: settings['umpireEnabled'] === true ? true : false
    }
  });

  var description = `Update project "${name}"`;
  dispatch(createTask(
      description, 'PUT', `/projects/${name}`, body, {onCancel, onFinish}
  ));
};

const deleteProject = name => dispatch => {
  dispatch(createTask(
      `Delete project "${name}"`, 'DELETE', `/projects/${name}`, {},
      {onFinish: () => dispatch(fetchProjects())}
  ));
};

const receiveProjects = projects => ({
  type: ActionTypes.RECEIVE_PROJECTS,
  projects
});

// TODO(littlecvr): similar to fetchBundles, refactor code if possible
const fetchProjects = () => dispatch => {
  fetch('/projects.json').then(response => {
    response.json().then(json => {
      dispatch(receiveProjects(json));
    }, error => {
      // TODO(littlecvr): better error handling
      console.error('error parsing project list response');
      console.error(error);
    });
  }, error => {
    // TODO(littlecvr): better error handling
    console.error('error fetching project list');
    console.error(error);
  });
};

const switchProject = nextProject => (dispatch, getState) => dispatch({
  type: ActionTypes.SWITCH_PROJECT,
  prevProject: getState().getIn(['dome', 'project']),
  nextProject
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

// TODO(littlecvr): this action is growing bigger, we should probably
//                  implement a task queue class instead of making this more
//                  complicated
const createTask = (description, method, url, body, {
                      onCancel = function() {},
                      onFinish = function() {}
                    } = {}) => (
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
      url
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

// TODO(littlecvr): this action is growing bigger, we should probably
//                  implement a task queue class instead of making this more
//                  complicated
const startTask = taskID => (dispatch, getState) => {
  taskID = String(taskID);  // make sure taskID is always a string
  dispatch(changeTaskState(taskID, TaskStates.RUNNING));

  let task = getState().getIn(['dome', 'tasks', taskID]);
  let body = deepcopy(_taskBodies[taskID]);  // make a copy

  let queue = Promise.resolve();  // task queue powered by Promise

  // go through the body and upload files first
  queue = recursivelyUploadFileFields(body, queue);

  // send the end request
  queue = queue.then(() => {
    let request = {
      method: task.get('method'),
      headers: {'Content-Type': 'application/json'},  // always send in JSON
      body: JSON.stringify(body)
    };
    return fetch(`${task.get('url')}/`, request);
  }).then(checkHTTPStatus).then(_taskOnFinishes[taskID]);

  // if all sub-tasks succeeded, mark it as succeeded, and start the next task
  queue = queue.then(() => {
    dispatch(changeTaskState(taskID, TaskStates.SUCCEEDED));

    // find the next task and start it
    let tasks = getState().getIn(['dome', 'tasks']);
    let taskIDs = tasks.keySeq().sort().toArray();
    let nextIndex = 1 + taskIDs.indexOf(taskID);
    if (nextIndex > 0 && nextIndex < taskIDs.length) {
      let nextID = taskIDs[nextIndex];
      dispatch(startTask(nextID));
    }
  });

  // if any sub-task above failed, display the error message
  queue = queue.catch(error => {
    let setAndShow = response => {
      dispatch(setAndShowErrorDialog(`${error.message}\n\n${response}`));
    };
    if (error.response.headers.get('Content-Type') == 'application/json') {
      error.response.json().then(JSON.stringify).then(setAndShow);
    } else {
      error.response.text().then(setAndShow);
    }

    // mark the task as failed
    dispatch(changeTaskState(taskID, TaskStates.FAILED));
  });
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
  recieveConfig, updateConfig, fetchConfig, initializeConfig,
  enableTFTP, disableTFTP,
  setError, showErrorDialog, hideErrorDialog, setAndShowErrorDialog,
  createProject, updateProject, deleteProject, fetchProjects, switchProject,
  switchApp,
  openForm, closeForm,
  createTask, removeTask, cancelTaskAndItsDependencies
};
