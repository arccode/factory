// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';

import actionTypes from './actionTypes';

const INITIAL_STATE = Immutable.fromJS({
  isLoggedIn: false,
});

export default (state = INITIAL_STATE, action) => {
  switch (action.type) {
    case actionTypes.LOGIN_SUCCEED:
      return state.set('isLoggedIn', true);

    case actionTypes.LOGIN_FAILED:
    case actionTypes.LOGOUT:
      return state.set('isLoggedIn', false);

    default:
      return state;
  }
};
