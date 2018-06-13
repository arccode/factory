// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createSelector} from 'reselect';

import {NAME} from './constants';

export const localState = (state) => state.get(NAME);

export const getBundles = (state) => localState(state).get('entries');
export const getExpandedMap = (state) => localState(state).get('expanded');

const getPropBundleName = (state, props) => props.bundle.get('name');
export const getBundleExpanded = createSelector(
    [getExpandedMap, getPropBundleName],
    (expanded, name) => expanded.get(name));
