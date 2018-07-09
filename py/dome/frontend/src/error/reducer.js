// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';

import actionTypes from './actionTypes';

const INITIAL_STATE = Immutable.fromJS({
  show: false,
  message: '',
});

export default (state = INITIAL_STATE, action) => {
  switch (action.type) {
    case actionTypes.SET_ERROR_MESSAGE:
      return state.set('message', action.message);

    case actionTypes.SHOW_ERROR_DIALOG:
      return state.set('show', true);

    case actionTypes.HIDE_ERROR_DIALOG:
      return state.set('show', false);

    default:
      return state;
  }
};
