// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createSelector} from 'reselect';

import {RootState} from '@app/types';

import {displayedState} from '@common/optimistic_update';

import {NAME} from './constants';
import {BundleState} from './reducer';
import {Bundle, DeletedResources} from './types';

export const localState = (state: RootState): BundleState =>
  displayedState(state)[NAME];

export const getBundles =
  (state: RootState): Bundle[] => localState(state).entries;
export const getBundleNames = createSelector(getBundles, (bundles) => (
  bundles.map((bundle) => bundle.name)));
export const getExpandedMap =
  (state: RootState): {[name: string]: boolean} => localState(state).expanded;
export const getDeletedResources =
  (state: RootState): (DeletedResources | null) =>
      localState(state).deletedResources;
