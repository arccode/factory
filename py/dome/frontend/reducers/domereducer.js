// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';

import ActionTypes from '../constants/ActionTypes';
import AppNames from '../constants/AppNames';
import TaskStates from '../constants/TaskStates';

const INITIAL_STATE = Immutable.fromJS({
  boards: {},
  currentBoard: '',
  currentApp: AppNames.BOARDS_APP,  // default app is the board selection page
  formVisibility: {
  },
  formPayload: {
  },
  tasks: {}
});

export default function domeReducer(state = INITIAL_STATE, action) {
  switch (action.type) {
    case ActionTypes.ADD_BOARD:
      return state.setIn(['boards', action.board.name],
          Immutable.fromJS(action.board));

    case ActionTypes.DELETE_BOARD:
      return state.deleteIn(['boards', action.boardName]);

    case ActionTypes.RECEIVE_BOARDS:
      return state.set('boards', Immutable.Map(action.boards.map(
          b => [b['name'], Immutable.fromJS(b).merge({
            umpireReady: b['umpireEnabled']
          })]
      )));

    case ActionTypes.UPDATE_BOARD:
      return state.mergeIn(['boards', action.board.name],
          Immutable.fromJS(action.board));

    case ActionTypes.SWITCH_BOARD:
      return state.withMutations(s => {
        s.set('currentBoard', action.nextBoard);
        // switch to dashboard after switching board by default
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
