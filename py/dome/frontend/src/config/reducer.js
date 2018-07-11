// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {combineReducers} from 'redux';

import actionTypes from './actionTypes';

export default combineReducers({
  updating: (state = false, action) => {
    switch (action.type) {
      case actionTypes.START_UPDATING_CONFIG:
        return true;

      case actionTypes.FINISH_UPDATING_CONFIG:
        return false;

      default:
        return state;
    }
  },
  TFTPEnabled: (state = false, action) => {
    switch (action.type) {
      case actionTypes.RECEIVE_CONFIG:
        return action.config.tftpEnabled;

      default:
        return state;
    }
  },
});
