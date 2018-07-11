// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';

import actionTypes from './actionTypes';

const INITIAL_STATE = {
  entries: [],

  // Controls whether a bundle card is expanded or not. The key is the name of
  // the bundle, value is a boolean indicating whether it's expanded or not.
  expanded: {},
};

export default produce((draft, action) => {
  switch (action.type) {
    case actionTypes.ADD_BUNDLE:
      draft.expanded[action.bundle.name] = false;
      draft.entries.unshift(action.bundle);
      return;

    case actionTypes.DELETE_BUNDLE: {
      delete draft.expanded[action.name];
      const bundleIndex = draft.entries.findIndex(
          (b) => b.name === action.name,
      );
      if (bundleIndex > -1) {
        draft.entries.splice(bundleIndex, 1);
      }
      return;
    }

    case actionTypes.RECEIVE_BUNDLES:
    case actionTypes.REORDER_BUNDLES: {
      draft.entries = action.bundles;
      // build expanded map
      const oldExpandedMap = draft.expanded;
      const newExpandedMap = action.bundles.reduce((expandedMap, bundle) => {
        // if a bundle already exists in the old list, we must keep its value
        // (or bundle cards would all collapse)
        let expanded = false;
        if (oldExpandedMap.hasOwnProperty(bundle.name)) {
          expanded = oldExpandedMap[bundle.name];
        }
        return {...expandedMap, [bundle.name]: expanded};
      }, {});
      draft.expanded = newExpandedMap;
      return;
    }

    case actionTypes.UPDATE_BUNDLE: {
      const bundleIndex = draft.entries.findIndex(
          (b) => b.name === action.name,
      );
      if (bundleIndex > -1) {
        draft.entries[bundleIndex] = action.bundle;
      }
      return;
    }

    case actionTypes.EXPAND_BUNDLE:
      draft.expanded[action.name] = true;
      return;

    case actionTypes.COLLAPSE_BUNDLE:
      draft.expanded[action.name] = false;
      return;
  }
}, INITIAL_STATE);
