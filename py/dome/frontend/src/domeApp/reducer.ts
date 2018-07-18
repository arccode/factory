// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {combineReducers} from 'redux';
import {ActionType, getType} from 'typesafe-actions';

import {basicActions as actions} from './actions';
import {AppName} from './types';

export interface DomeAppState {
  currentApp: AppName;
}

type DomeAppAction = ActionType<typeof actions>;

export default combineReducers<DomeAppState, DomeAppAction>({
  currentApp: (state = 'PROJECTS_APP', action) => {
    switch (action.type) {
      case getType(actions.switchApp):
        return action.payload.nextApp;

      default:
        return state;
    }
  },
});
