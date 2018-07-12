// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {combineReducers} from 'redux';
import {ActionType, getType} from 'typesafe-actions';

import {basicActions as actions} from './actions';

export interface AuthState {
  isLoggedIn: boolean;
}

type AuthAction = ActionType<typeof actions>;

export default combineReducers<AuthState, AuthAction>({
  isLoggedIn: (state = false, action) => {
    switch (action.type) {
      case getType(actions.loginSucceed):
        return true;

      case getType(actions.loginFailed):
      case getType(actions.logout):
        return false;

      default:
        return state;
    }
  },
});
