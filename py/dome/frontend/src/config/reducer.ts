// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {combineReducers} from 'redux';
import {ActionType, getType} from 'typesafe-actions';

import {basicActions as actions} from './actions';
import {Config} from './types';

export interface ConfigState {
  updating: boolean;
  config: Config;
}

type ConfigAction = ActionType<typeof actions>;

export default combineReducers<ConfigState, ConfigAction>({
  updating: (state = false, action: ConfigAction) => {
    switch (action.type) {
      case getType(actions.startUpdatingConfig):
        return true;

      case getType(actions.finishUpdatingConfig):
        return false;

      default:
        return state;
    }
  },
  config: (state = {tftpEnabled: false, mcastEnabled: false},
    action: ConfigAction) => {
    switch (action.type) {
      case getType(actions.receiveConfig):
        return action.payload.config;

      default:
        return state;
    }
  },
});
