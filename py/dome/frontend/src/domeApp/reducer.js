// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {combineReducers} from 'redux';

import actionTypes from './actionTypes';
import {AppNames} from './constants';

export default combineReducers({
  currentApp: (state = AppNames.PROJECTS_APP, action) => {
    switch (action.type) {
      case actionTypes.SWITCH_APP:
        return action.nextApp;

      default:
        return state;
    }
  },
});
