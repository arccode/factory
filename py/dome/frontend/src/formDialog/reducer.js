// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';

import actionTypes from './actionTypes';

const INITIAL_STATE = Immutable.fromJS({
  // default app is the project selection page.
  visibility: {
  },
  payload: {
  },
});

export default (state = INITIAL_STATE, action) => {
  switch (action.type) {
    case actionTypes.OPEN_FORM:
      return state.withMutations((s) => {
        s.setIn(['visibility', action.formName], true);
        s.mergeIn(['payload', action.formName], action.payload);
      });

    case actionTypes.CLOSE_FORM:
      return state.setIn(['visibility', action.formName], false);

    default:
      return state;
  }
};
