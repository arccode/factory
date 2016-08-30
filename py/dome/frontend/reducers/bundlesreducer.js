// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';

import ActionTypes from '../constants/ActionTypes';

const INITIAL_STATE = Immutable.fromJS({
  entries: []
});

export default function bundlesReducer(state = INITIAL_STATE, action) {
  switch (action.type) {
    case ActionTypes.RECEIVE_BUNDLES:
      return state.set('entries', Immutable.fromJS(action.bundles));

    default:
      return state;
  }
}
