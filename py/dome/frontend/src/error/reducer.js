// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {combineReducers} from 'redux';

import actionTypes from './actionTypes';

export default combineReducers({
  show: (state = false, action) => {
    switch (action.type) {
      case actionTypes.SHOW_ERROR_DIALOG:
        return true;

      case actionTypes.HIDE_ERROR_DIALOG:
        return false;

      default:
        return state;
    }
  },
  message: (state = '', action) => {
    switch (action.type) {
      case actionTypes.SET_ERROR_MESSAGE:
        return action.message;

      default:
        return state;
    }
  },
});
