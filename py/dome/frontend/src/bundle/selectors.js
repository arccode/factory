// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createSelector} from 'reselect';

import {NAME} from './constants';

export const localState = (state) => state[NAME];

export const getBundles = (state) => localState(state).entries;
export const getExpandedMap = (state) => localState(state).expanded;

const getPropBundleName = (state, props) => props.bundle.name;
export const getBundleExpanded = createSelector(
    [getExpandedMap, getPropBundleName],
    (expanded, name) => expanded[name]);
