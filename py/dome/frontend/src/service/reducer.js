// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';
import {combineReducers} from 'redux';

import actionTypes from './actionTypes';

export default combineReducers({
  schemata: (state = {}, action) => {
    switch (action.type) {
      case actionTypes.RECEIVE_SERVICE_SCHEMATA:
        return action.schemata;

      default:
        return state;
    }
  },
  services: produce((draft, action) => {
    switch (action.type) {
      case actionTypes.RECEIVE_SERVICES:
        return action.services;

      case actionTypes.UPDATE_SERVICE:
        draft[action.name] = action.config;
        return;
    }
  }, {}),
});
