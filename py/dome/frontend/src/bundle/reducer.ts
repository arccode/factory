// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';
import {ActionType, getType} from 'typesafe-actions';

import {basicActions as actions} from './actions';
import {Bundle, DeletedResources} from './types';

export interface BundleState {
  entries: Bundle[];
  // Controls whether a bundle card is expanded or not. The key is the name of
  // the bundle, value is a boolean indicating whether it's expanded or not.
  expanded: {[name: string]: boolean};
  deletedResources: DeletedResources | null;
}

type BundleAction = ActionType<typeof actions>;

const INITIAL_STATE = {
  entries: [],
  expanded: {},
  deletedResources: null,
};

export default produce<BundleState, BundleAction>((draft, action) => {
  switch (action.type) {
    case getType(actions.addBundle): {
      const {bundle} = action.payload;
      draft.expanded[bundle.name] = false;
      draft.entries.unshift(bundle);
      return;
    }

    case getType(actions.deleteBundleImpl): {
      const {name} = action.payload;
      delete draft.expanded[name];
      const bundleIndex = draft.entries.findIndex((b) => b.name === name);
      if (bundleIndex > -1) {
        draft.entries.splice(bundleIndex, 1);
      }
      return;
    }

    case getType(actions.receiveBundles):
    case getType(actions.reorderBundlesImpl): {
      const {bundles} = action.payload;
      draft.entries = bundles;
      // build expanded map
      const oldExpandedMap = draft.expanded;
      const newExpandedMap = bundles.reduce((expandedMap, bundle) => {
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

    case getType(actions.updateBundle): {
      const {name, bundle} = action.payload;
      const bundleIndex = draft.entries.findIndex((b) => b.name === name);
      if (bundleIndex > -1) {
        draft.entries[bundleIndex] = bundle;
      }
      return;
    }

    case getType(actions.expandBundle):
      draft.expanded[action.payload.name] = true;
      return;

    case getType(actions.collapseBundle):
      draft.expanded[action.payload.name] = false;
      return;

    case getType(actions.receiveDeletedResources):
      draft.deletedResources = action.payload.resources;
      return;

    case getType(actions.closeGarbageCollectionSnackbar):
      draft.deletedResources = null;
      return;

    default:
      return;
  }
}, INITIAL_STATE);
