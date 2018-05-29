// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import ActionTypes from '../constants/ActionTypes';

import TaskActions from './taskactions';

// TODO(pihsun): Have a better way to handle task cancellation.
const buildOnCancel = (dispatch, getState) => {
  const projectsSnapshot =
      getState().getIn(['dome', 'projects']).toList();
  return () => dispatch(receiveProjects(projectsSnapshot.toJS()));
};

// add authentication token to header
const authorizedFetch = (url, req) => {
  if (!req.hasOwnProperty('headers')) {
    req['headers'] = {};
  }
  req['headers']['Authorization'] = 'Token ' + localStorage.getItem('token');
  return fetch(url, req);
};

const loginSucceed = (token) => {
  localStorage.setItem('token', token);
  return {type: ActionTypes.LOGIN_SUCCEED};
};

const loginFailed = () => {
  localStorage.removeItem('token');
  return {type: ActionTypes.LOGIN_FAILED};
};

const tryLogin = (data) => async (dispatch) => {
  data = data.toJS();
  const response = await fetch('/auth', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  });
  const json = await response.json();
  const token = json['token'];
  if (token) {
    dispatch(loginSucceed(token));
  } else {
    dispatch(loginFailed());
    // TODO(pihsun): Don't use blocking window.alert.
    window.alert('\nLogin failed :(');
  }
};

const testAuthToken = () => async (dispatch) => {
  const token = localStorage.getItem('token');
  if (token != null) {
    const resp = await authorizedFetch('/projects.json', {});
    if (resp.ok) {
      dispatch(loginSucceed(token));
    } else {
      dispatch(loginFailed());
    }
  }
};

const logout = () => (dispatch) => {
  localStorage.removeItem('token');
  dispatch({type: ActionTypes.LOGOUT});
};

const recieveConfig = (config) => ({
  type: ActionTypes.RECIEVE_CONFIG,
  config,
});

const initializeConfig = () => (dispatch) => {
  const body = {};
  dispatch(fetchConfig(body));
};

const fetchConfig = () => async (dispatch) => {
  const response = await authorizedFetch('/config/0', {});
  const json = await response.json();
  dispatch(recieveConfig(json));
};

const updateConfig = (body) => async (dispatch, getState) => {
  dispatch({type: ActionTypes.START_UPDATING_CONFIG});
  const description = 'Update config';
  const {cancel} = await dispatch(
      TaskActions.runTask(description, 'PUT', '/config/0/', body));
  if (!cancel) {
    await dispatch(fetchConfig());
    dispatch({type: ActionTypes.FINISH_UPDATING_CONFIG});
  }
};

const enableTFTP = () => (dispatch) => {
  const body = {
    tftp_enabled: true,
  };
  dispatch(updateConfig(body));
};

const disableTFTP = () => (dispatch) => {
  const body = {
    tftp_enabled: false,
  };
  dispatch(updateConfig(body));
};

const setError = (message) => ({
  type: ActionTypes.SET_ERROR_MESSAGE,
  message,
});

const showErrorDialog = () => ({
  type: ActionTypes.SHOW_ERROR_DIALOG,
});

const hideErrorDialog = () => ({
  type: ActionTypes.HIDE_ERROR_DIALOG,
});

// convenient wrapper of setError() + showErrorDialog()
const setAndShowErrorDialog = (message) => (dispatch) => {
  dispatch(setError(message));
  dispatch(showErrorDialog());
};

const createProject = (name) => async (dispatch) => {
  const description = `Create project "${name}"`;
  const {cancel} = await dispatch(
      TaskActions.runTask(description, 'POST', '/projects/', {name}));
  if (!cancel) {
    await dispatch(fetchProjects());
  }
};

const updateProject = (name, settings = {}) => async (dispatch, getState) => {
  const body = {name};
  [
    'umpireEnabled',
    'umpireAddExistingOne',
    'umpireHost',
    'umpirePort',
    'netbootBundle',
  ].forEach((key) => {
    if (key in settings) {
      body[key] = settings[key];
    }
  });

  // taking snapshot must be earlier than optimistic update
  const onCancel = buildOnCancel(dispatch, getState);

  // optimistic update
  dispatch({
    type: ActionTypes.UPDATE_PROJECT,
    project: Object.assign({
      name,
      umpireReady: false,
    }, settings),
  });

  const description = `Update project "${name}"`;
  const {cancel, response} = await dispatch(
      TaskActions.runTask(description, 'PUT', `/projects/${name}/`, body));
  if (cancel) {
    onCancel();
    return;
  }
  const json = await response.json();
  // WORKAROUND: Umpire is not ready as soon as it should be,
  // wait for 1 second to prevent the request from failing.
  // TODO(b/65393817): remove the timeout after the issue has been solved.
  setTimeout(() => {
    dispatch({
      type: ActionTypes.UPDATE_PROJECT,
      project: {
        name,
        umpireVersion: json['umpireVersion'],
        isUmpireRecent: json['isUmpireRecent'],
        umpireReady: json['umpireEnabled'],
      },
    });
  }, 1000);
};

const deleteProject = (name) => async (dispatch) => {
  const {cancel} = await dispatch(TaskActions.runTask(
      `Delete project "${name}"`, 'DELETE', `/projects/${name}/`, {}));
  if (!cancel) {
    await dispatch(fetchProjects());
  }
};

const receiveProjects = (projects) => ({
  type: ActionTypes.RECEIVE_PROJECTS,
  projects,
});

// TODO(littlecvr): similar to fetchBundles, refactor code if possible
const fetchProjects = () => async (dispatch) => {
  const response = await authorizedFetch('/projects.json', {});
  const json = await response.json();
  dispatch(receiveProjects(json));
};

const switchProject = (nextProject) => (dispatch, getState) => dispatch({
  type: ActionTypes.SWITCH_PROJECT,
  prevProject: getState().getIn(['dome', 'project']),
  nextProject,
});

const switchApp = (nextApp) => (dispatch, getState) => dispatch({
  type: ActionTypes.SWITCH_APP,
  prevApp: getState().getIn(['dome', 'app']),
  nextApp,
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
    payload,
  };
  if (!visible) {
    dispatch(action);
  } else {
    Promise.resolve()
        .then(() => dispatch(closeForm(formName)))
        .then(() => dispatch(action));
  }
};

const closeForm = (formName) => ({
  type: ActionTypes.CLOSE_FORM,
  formName,
});

export default {
  authorizedFetch,
  tryLogin, logout, testAuthToken,
  recieveConfig, updateConfig, fetchConfig, initializeConfig,
  enableTFTP, disableTFTP,
  setError, showErrorDialog, hideErrorDialog, setAndShowErrorDialog,
  createProject, updateProject, deleteProject, fetchProjects, switchProject,
  switchApp,
  openForm, closeForm,
};
