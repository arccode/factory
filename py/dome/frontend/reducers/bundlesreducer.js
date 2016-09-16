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
    case ActionTypes.ADD_BUNDLE:
      return state.set('entries', state.get('entries').unshift(
          Immutable.fromJS(action.bundle)
      ));

    case ActionTypes.DELETE_BUNDLE:
      return state.deleteIn(['entries', state.get('entries').findIndex(
          b => b.get('name') == action.name
      )]);

    case ActionTypes.RECEIVE_BUNDLES:
    case ActionTypes.REORDER_BUNDLES:
      return state.set('entries', Immutable.fromJS(action.bundles));

    case ActionTypes.UPDATE_BUNDLE:
      return state.set('entries', state.get('entries').map(bundle => {
        if (bundle.get('name') == action.name) {
          return Immutable.fromJS(action.bundle);
        }
        return bundle;
      }));

    default:
      return state;
  }
}
