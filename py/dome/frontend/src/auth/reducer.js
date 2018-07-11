// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {combineReducers} from 'redux';

import actionTypes from './actionTypes';

export default combineReducers({
  isLoggedIn: (state = false, action) => {
    switch (action.type) {
      case actionTypes.LOGIN_SUCCEED:
        return true;

      case actionTypes.LOGIN_FAILED:
      case actionTypes.LOGOUT:
        return false;

      default:
        return state;
    }
  },
});
