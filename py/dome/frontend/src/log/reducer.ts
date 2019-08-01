// Copyright 2019 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {combineReducers} from 'redux';
import {ActionType, getType} from 'typesafe-actions';

import {basicActions as actions} from './actions';

export interface LogState {
  defaultDownloadDate: string;
}

type LogAction = ActionType<typeof actions>;

export default combineReducers<LogState, LogAction>({
  defaultDownloadDate: (state = '', action) => {
    switch (action.type) {
      case getType(actions.setDefaultDownloadDate): {
        const {defaultDownloadDate} = action.payload;
        return defaultDownloadDate;
      }

      default:
        return state;
    }
  },
});
