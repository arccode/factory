// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';

import ActionTypes from '../constants/ActionTypes';

const initialState = Immutable.fromJS({
  entries: [],
  isFetchingEntries: false,
  formVisibility: {
  },
  formPayload: {
  }
});

export default function bundlesReducer(state = initialState, action) {
  switch (action.type) {
    case ActionTypes.REQUEST_BUNDLES:
      return state.set('isFetchingEntries', true);

    case ActionTypes.RECEIVE_BUNDLES:
      return state.withMutations((s) => {
        s.set('isFetchingEntries', false);
        s.set('entries', Immutable.fromJS(action.bundles));
      });

    case ActionTypes.OPEN_FORM:
      return state.withMutations((s) => {
        s.setIn(['formVisibility', action.formName], true);
        s.mergeIn(['formPayload', action.formName], action.payload);
      });

    case ActionTypes.CLOSE_FORM:
      return state.setIn(['formVisibility', action.formName], false);

    default:
      return state;
  }
};
