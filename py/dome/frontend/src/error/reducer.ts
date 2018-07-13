// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {combineReducers} from 'redux';
import {ActionType, getType} from 'typesafe-actions';

import {basicActions as actions} from './actions';

export interface ErrorState {
  show: boolean;
  message: string;
}

type ErrorAction = ActionType<typeof actions>;

export default combineReducers<ErrorState, ErrorAction>({
  show: (state = false, action) => {
    switch (action.type) {
      case getType(actions.showErrorDialog):
        return true;

      case getType(actions.hideErrorDialog):
        return false;

      default:
        return state;
    }
  },
  message: (state = '', action) => {
    switch (action.type) {
      case getType(actions.setError):
        return action.payload.message;

      default:
        return state;
    }
  },
});
