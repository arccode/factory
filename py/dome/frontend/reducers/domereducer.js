// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';

import ActionTypes from '../constants/ActionTypes';
import AppNames from '../constants/AppNames';
import TaskStates from '../constants/TaskStates';

const INITIAL_STATE = Immutable.fromJS({
  isLoggedIn: false,
  projects: {},
  currentProject: '',
  currentApp: AppNames.PROJECTS_APP,  // default app is the project selection
                                      // page
  errorDialog: {
    show: false,
    message: '',
  },
  formVisibility: {
  },
  formPayload: {
  },
  tasks: {},
  config: {
    updating: false,
    TFTPEnabled: false
  }
});

export default function domeReducer(state = INITIAL_STATE, action) {
  switch (action.type) {
    case ActionTypes.LOGIN_SUCCEED:
      return state.set('isLoggedIn', true);

    case ActionTypes.LOGIN_FAILED:
      return state.set('isLoggedIn', false);

    case ActionTypes.LOGOUT:
      return state.set('isLoggedIn', false);

    case ActionTypes.RECIEVE_CONFIG:
      return state.setIn(['config', 'TFTPEnabled'],
          action.config.tftpEnabled);

    case ActionTypes.START_UPDATING_CONFIG:
      return state.setIn(['config', 'updating'], true);

    case ActionTypes.FINISH_UPDATING_CONFIG:
      return state.setIn(['config', 'updating'], false);

    case ActionTypes.SET_ERROR_MESSAGE:
      return state.setIn(['errorDialog', 'message'], action.message);

    case ActionTypes.SHOW_ERROR_DIALOG:
      return state.setIn(['errorDialog', 'show'], true);

    case ActionTypes.HIDE_ERROR_DIALOG:
      return state.setIn(['errorDialog', 'show'], false);

    case ActionTypes.ADD_PROJECT:
      return state.setIn(['projects', action.project.name],
          Immutable.fromJS(action.project));

    case ActionTypes.DELETE_PROJECT:
      return state.deleteIn(['projects', action.projectName]);

    case ActionTypes.RECEIVE_PROJECTS:
      return state.set('projects', Immutable.Map(action.projects.map(
          b => [b['name'], Immutable.fromJS(b).merge({
            umpireReady: b['umpireEnabled']
          })]
      )));

    case ActionTypes.UPDATE_PROJECT:
      return state.mergeIn(['projects', action.project.name],
          Immutable.fromJS(action.project));

    case ActionTypes.SWITCH_PROJECT:
      return state.withMutations(s => {
        s.set('currentProject', action.nextProject);
        // switch to dashboard after switching project by default
        s.set('currentApp', AppNames.DASHBOARD_APP);
      });

    case ActionTypes.SWITCH_APP:
      return state.set('currentApp', action.nextApp);

    case ActionTypes.OPEN_FORM:
      return state.withMutations((s) => {
        s.setIn(['formVisibility', action.formName], true);
        s.mergeIn(['formPayload', action.formName], action.payload);
      });

    case ActionTypes.CLOSE_FORM:
      return state.setIn(['formVisibility', action.formName], false);

    case ActionTypes.CREATE_TASK:
      return state.mergeIn(['tasks'], {
        [String(action.taskID)]: {
          state: TaskStates.WAITING,
          description: action.description,
          method: action.method,
          url: action.url,
          contentType: action.contentType
        }
      });

    case ActionTypes.CHANGE_TASK_STATE:
      return state.setIn(
          ['tasks', String(action.taskID), 'state'], action.state);

    case ActionTypes.REMOVE_TASK:
      return state.deleteIn(['tasks', String(action.taskID)]);

    default:
      return state;
  }
}
