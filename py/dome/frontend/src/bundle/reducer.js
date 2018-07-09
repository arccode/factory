// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';

import actionTypes from './actionTypes';

const INITIAL_STATE = Immutable.fromJS({
  entries: [],

  // Controls whether a bundle card is expanded or not. The key is the name of
  // the bundle, value is a boolean indicating whether it's expanded or not.
  expanded: {},
});

export default (state = INITIAL_STATE, action) => {
  switch (action.type) {
    case actionTypes.ADD_BUNDLE:
      return state.withMutations((s) => {
        s.setIn(['expanded', action.bundle.name], false);
        s.set('entries', s.get('entries').unshift(
            Immutable.fromJS(action.bundle),
        ));
      });

    case actionTypes.DELETE_BUNDLE:
      return state.withMutations((s) => {
        s.deleteIn(['expanded', action.name]);
        s.deleteIn(['entries', s.get('entries').findIndex(
            (b) => b.get('name') === action.name,
        )]);
      });

    case actionTypes.RECEIVE_BUNDLES:
    case actionTypes.REORDER_BUNDLES:
      return state.withMutations((s) => {
        s.set('entries', Immutable.fromJS(action.bundles));

        // build expanded map
        const oldExpandedMap = s.get('expanded').toJS();
        const newExpandedMap = action.bundles.reduce((expandedMap, bundle) => {
          // if a bundle already exists in the old list, we must keep its value
          // (or bundle cards would all collapse)
          let expanded = false;
          if (oldExpandedMap.hasOwnProperty(bundle.name)) {
            expanded = oldExpandedMap[bundle.name];
          }
          return Object.assign(expandedMap, {[bundle.name]: expanded});
        }, {});
        s.set('expanded', Immutable.fromJS(newExpandedMap));
      });

    case actionTypes.UPDATE_BUNDLE:
      return state.set('entries', state.get('entries').map((bundle) => {
        if (bundle.get('name') === action.name) {
          return Immutable.fromJS(action.bundle);
        }
        return bundle;
      }));

    case actionTypes.EXPAND_BUNDLE:
      return state.setIn(['expanded', action.name], true);

    case actionTypes.COLLAPSE_BUNDLE:
      return state.setIn(['expanded', action.name], false);

    default:
      return state;
  }
};
