// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';

import ActionTypes from '../constants/ActionTypes';
import TaskStates from '../constants/TaskStates';

const INITIAL_STATE = Immutable.Map({
  tasks: Immutable.OrderedMap(),
});

export default function taskReducer(state = INITIAL_STATE, action) {
  switch (action.type) {
    case ActionTypes.CREATE_TASK:
      return state.setIn(['tasks', action.taskID], Immutable.fromJS({
        state: TaskStates.WAITING,
        description: action.description,
        method: action.method,
        url: action.url,
        contentType: action.contentType,
      }));

    case ActionTypes.CHANGE_TASK_STATE:
      return state.setIn(
          ['tasks', action.taskID, 'state'], action.state);

    case ActionTypes.DISMISS_TASK:
      return state.deleteIn(['tasks', action.taskID]);

    default:
      return state;
  }
}
