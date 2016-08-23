// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';

import ActionTypes from '../constants/ActionTypes';
import AppNames from '../constants/AppNames';

const INITIAL_STATE = Immutable.fromJS({
  boards: [],
  currentBoard: '',
  currentApp: AppNames.BUNDLES_APP  // default app is bundle manager
});

export default function domeReducer(state = INITIAL_STATE, action) {
  switch (action.type) {
    case ActionTypes.RECEIVE_BOARDS:
      return state.set('boards', Immutable.fromJS(action.boards));

    case ActionTypes.SWITCH_BOARD:
      return state.set('currentBoard', action.nextBoard);

    case ActionTypes.SWITCH_APP:
      return state.set('currentApp', action.nextApp);

    default:
      return state;
  }
};
